"""Write normalized jobs to Postgres with dedup (PLAN §3.2).

Two dedup layers:
  1. **Primary** — ``Job.id = <source>:<native_id>`` (the PK). Re-seeing a job
     refreshes its scraped fields but never touches its ``status`` (it may
     already be shortlisted/applied).
  2. **Cross-source** — ``(company, normalized_title)``. The same role posted on
     two boards is inserted once; later sightings within ``dedup_days`` are
     skipped so the dashboard/Slack aren't spammed.

Three rules the second layer has to get right, each of which it previously got
wrong in a way that looked like success.

**The window is measured from the last sighting, not the first.** It used to
filter on ``crawled_at``, which is deliberately never bumped, so a posting
crawled daily for three weeks dropped out of its own window on day fifteen and
the other board's copy walked in. ``last_seen_at`` exists for this and is bumped
on every refresh — see the 0010 migration for why bumping ``crawled_at`` instead
would have been the wrong cheap fix.

**A level named on both sides is a real difference.** ``dedup_key`` strips
seniority words on purpose, so "Backend Engineer" from two boards is one job.
But that also collapsed *Senior*, *Junior* and *Intern* "Backend Engineer" at
one company into a single key, and two of the three were dropped without trace.
So the key stays level-free and the level travels beside it: two postings are
the same posting **unless both name a level and the levels disagree**. A
posting that says nothing about seniority still matches anything, which keeps
the original intent — a board that omits "Junior" from its title has not
announced a different job.

**One board listing two titles has said they are two postings.** The leniency
above — a silent level matches any level, a parenthetical is ignored — is an
allowance for *another* board describing the same role differently. Applied
between two postings on the *same* board it merged roles that board itself
lists separately: a role with no level in its title was dropped as a copy of
the staff-level one next to it — and the staff-level row was the survivor —
and a team-specific opening as a copy of the generic one. Within one source,
two postings are the same posting only when the board gives them the same
title, level word and parenthetical included (a re-listing under a new id).

**Nothing is dropped silently, and the copy with a JD wins.** A skipped posting
is written onto the surviving row (``payload.dedup.suppressed``) and logged with
its key, so "why is this job not in my dashboard" has an answer. And when the
incumbent has no usable JD but the newcomer does — the LinkedIn-alert case,
where the alert mail arrives first carrying a title and nothing else — the
newcomer is inserted anyway rather than thrown away. Suppressing the only copy
that the tailor can actually read is worse than one extra row.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, defer

from jobpilot.crawler.normalize import NormalizedJob, vn_now
from jobpilot.crawler.quality import THIN_JD_CHARS
from jobpilot.crawler.reposts import relink
from jobpilot.crawler.text import dedup_key, normalize_title, title_level
from jobpilot.crawler.types import COMPANY_BOARD_SOURCES, is_hand_added
from jobpilot.store.models import Job, JobStatus

log = logging.getLogger(__name__)

#: How many suppressed siblings to remember on a surviving row. A trace is for
#: answering "where did the ITviec copy go", which the last few answer; an
#: unbounded list would grow a JSONB column on every crawl forever.
TRACE_LIMIT = 10


@dataclass
class CrawlStats:
    #: Postings the crawl looked at, pre-filter: the ones scraped, plus the ones
    #: a scraper left out by title before fetching their detail page.
    fetched: int = 0
    inserted: int = 0  # new rows
    updated: int = 0  # existing id refreshed
    duplicates: int = 0  # cross-source dupes skipped
    #: Of ``inserted``: rows kept *despite* a cross-source match, because the
    #: match had no usable JD and this one does. A sub-count, not a fourth
    #: bucket — these rows are counted in ``inserted`` as well, so the buckets
    #: still add up to ``fetched`` for anything reading them that way.
    superseded: int = 0
    filtered: int = 0  # dropped by stack/exclude rules, before or after the detail page
    fresh: int = 0  # posted within crawl.fresh_hours
    #: Searches that failed. With one keyword per run that is "the site failed";
    #: with several, a site can be ok (some searches worked) and still carry
    #: errors — a partial failure, reported as such rather than as "0 found".
    errors: int = 0
    #: Rows the database refused (see the savepoint in ``persist_jobs``). Kept
    #: apart from ``errors``, which counts failed *searches*: a site that loses
    #: some rows still reports ok, and folding the two together would let one
    #: losing every row read as "ran fine, nothing new".
    rejected: int = 0

    _FIELDS = (
        "fetched",
        "inserted",
        "updated",
        "duplicates",
        "superseded",
        "filtered",
        "fresh",
        "errors",
        "rejected",
    )

    def merge(self, other: CrawlStats) -> None:
        for f in self._FIELDS:
            setattr(self, f, getattr(self, f) + getattr(other, f))

    def as_dict(self) -> dict:
        return {f: getattr(self, f) for f in self._FIELDS}


def _new_job(nj: NormalizedJob, now: datetime, run_id: int | None = None) -> Job:
    return Job(
        run_id=run_id,
        id=nj.id,
        source=nj.source,
        url=nj.url,
        title=nj.title,
        company=nj.company,
        location=nj.location,
        salary=nj.salary,
        level=nj.level,
        posted_at=nj.posted_at,
        status=JobStatus.DISCOVERED,
        match_score=nj.match_score,
        apply_channel=nj.apply_channel,
        apply_target=nj.apply_target,
        payload=nj.payload,
        # Both set explicitly rather than left to the server default, so a
        # caller passing `now` (backfills, tests) gets the timestamps it asked
        # for on both columns instead of one of each.
        crawled_at=now,
        last_seen_at=now,
    )


def _refresh(job: Job, nj: NormalizedJob, now: datetime) -> None:
    """Refresh scraped fields on re-crawl; leave ``status`` untouched."""
    job.url = nj.url
    job.title = nj.title
    job.company = nj.company
    job.location = nj.location
    job.salary = nj.salary
    job.level = nj.level
    job.posted_at = nj.posted_at
    job.match_score = nj.match_score
    # Whoever *stated* where to apply wins; the scraped values are the fallback.
    # The same rule ``api/routes/jobs._merged_payload`` applies to `work_mode`,
    # and here for a sharper reason: choosing an HR contact's address as where
    # to apply is a decision, and the next scheduled crawl of that source used
    # to overwrite it with the board's own URL — silently, days later, with the
    # decision nowhere on screen to notice was gone. A crawled job is nearly
    # every job, so without this the offer does not survive the night.
    #
    # Both columns, not just the target. `apply_channel` is what
    # ``dispatcher.resolve_channel`` reads first, so reverting it alone would be
    # the same bug wearing a different hat: the address would still say
    # hr@example.com while the channel said `external`, and applying would hand
    # you a "link" to open.
    if not target_is_stated(job.payload):
        job.apply_channel = nj.apply_channel
        job.apply_target = nj.apply_target
    job.payload = _carry_row_keys(job.payload, nj.payload)
    # The board still lists it, which is the whole meaning of this column.
    # `crawled_at` stays put — see the class docstring in store/models.
    job.last_seen_at = now


#: Payload keys that belong to the *row*, not to the scrape, and therefore have
#: to survive a refresh that replaces ``payload`` wholesale.
#:
#: ``dedup``  — which sibling postings this row stands in for.
#: ``apply_target_source`` — whether a person chose the apply target.
#:
#: A list rather than two special cases, because the failure mode is identical
#: for both and was found the same way: the value exists until the next crawl,
#: which is the same as not existing.
_ROW_OWNED_KEYS = ("dedup", "apply_target_source")

#: Written into ``payload["apply_target_source"]`` when a person set the target.
STATED_TARGET = "user"


def target_is_stated(payload: dict | None) -> bool:
    """Whether a person chose where this application goes (and how)."""
    return (payload or {}).get("apply_target_source") == STATED_TARGET


def _carry_row_keys(old: dict | None, new: dict) -> dict:
    """Keep the row's own payload keys across a refresh.

    ``_refresh`` overwrites ``payload`` wholesale with what the scraper just
    produced, and the scraper knows nothing about which sibling postings this
    row is standing in for or about a target somebody chose by hand.
    """
    carried = {k: (old or {})[k] for k in _ROW_OWNED_KEYS if (old or {}).get(k)}
    return {**new, **carried} if carried else new


def _jd_chars(payload: dict | None) -> int:
    return len(((payload or {}).get("description_md") or "").strip())


def _has_usable_jd(payload: dict | None) -> bool:
    """Whether there is enough description here for the tailor to work from.

    Reuses ``quality.THIN_JD_CHARS`` rather than picking a second threshold: the
    dashboard already calls anything under it a `thin_jd`, and a row this module
    considers rich while the quality flag calls it thin would be two answers to
    one question.
    """
    return _jd_chars(payload) >= THIN_JD_CHARS


@dataclass
class _Seen:
    """A posting already inside the dedup window, as the index sees it."""

    job: Job
    level: str | None


class _Index:
    """Postings in the window, keyed for cross-source lookup."""

    def __init__(self) -> None:
        self._by_key: dict[str, list[_Seen]] = defaultdict(list)

    def add(self, job: Job, level: str | None = None) -> None:
        key = dedup_key(job.company, job.title)
        if level is None:
            level = title_level(job.title)
        self._by_key[key].append(_Seen(job=job, level=level))

    def covering(
        self, key: str, level: str | None, *, source: str, title: str | None
    ) -> _Seen | None:
        """The posting already covering this one, or ``None``.

        ``source`` and ``title`` are the candidate's own: whether two postings
        are one depends on whether the same board listed them both — see
        :func:`_same_posting`.

        Returns the match with the **most** JD rather than the first one found:
        the only question the caller asks of it is "is my candidate richer than
        what I already have", and asking that against an arbitrary member of the
        group would insert a second copy for each thin sibling in turn.

        Reading ``payload`` is what loads the deferred column, so this costs one
        extra SELECT per matched row — including when there is only one match,
        since the caller still has to compare against it. That is per *collision*,
        not per job, which is the trade the deferred load was chosen for.
        """
        matches = [
            seen
            for seen in self._by_key.get(key, ())
            if _same_posting(seen, level, source, title)
        ]
        if not matches:
            return None
        return max(matches, key=lambda seen: _jd_chars(seen.job.payload))


def _listed(title: str | None) -> str:
    return normalize_title(title, strip_level=False, keep_parens=True)


def _same_posting(seen: _Seen, level: str | None, source: str, title: str | None) -> bool:
    """Whether a candidate sharing ``seen``'s key is the same posting as it.

    Across boards: yes, unless both name a level and the levels disagree. A
    board that leaves "Junior" out of a title has not announced another job.

    On the same board that allowance has nothing to stand on — there is no
    second house style to forgive. The board lists the two under two ids, so
    they are one posting only if it gave them the same title.
    """
    # A row added by hand is not a board's listing, even when the user filed it
    # under a board's name: it has no house style of its own and no second id
    # from that board. Held to the same-board rule, a hand-pasted posting and the
    # board's own copy of it became two jobs over a parenthesis in the title.
    if seen.job.source == source and source in COMPANY_BOARD_SOURCES:
        # An employer's own system does not re-list its postings under new ids:
        # each id is a requisition, and a shared title is several openings.
        return False
    if seen.job.source == source and not is_hand_added(seen.job.id):
        # The shared normaliser, asked to keep what it otherwise forgives: the
        # level word and the parenthetical. Case, accents, dashes and spacing
        # still do not make a title a different title.
        return _listed(seen.job.title) == _listed(title)
    return level is None or seen.level is None or seen.level == level


def _record_suppressed(winner: Job, nj: NormalizedJob, now: datetime) -> None:
    """Note on the surviving row which posting was dropped in its favour."""
    payload = dict(winner.payload or {})
    trace = dict(payload.get("dedup") or {})
    entries = [e for e in (trace.get("suppressed") or []) if e.get("id") != nj.id]
    entries.append(
        {
            "id": nj.id,
            "source": nj.source,
            "url": nj.url,
            "title": nj.title,
            "at": now.isoformat(),
        }
    )
    trace["suppressed"] = entries[-TRACE_LIMIT:]
    payload["dedup"] = trace
    # Reassigned, not mutated: JSONB change tracking does not see in-place edits.
    winner.payload = payload


#: Why a cross-source match was kept rather than skipped. One string, written to
#: both rows, so the two halves of the link cannot describe it differently.
SUPERSEDE_REASON = "the earlier posting has no usable JD"


def _record_supersedes(payload: dict, loser: Job, now: datetime) -> dict:
    """Note on the incoming row which thin posting it is standing in for."""
    trace = dict(payload.get("dedup") or {})
    trace["supersedes"] = {
        "id": loser.id,
        "source": loser.source,
        "reason": SUPERSEDE_REASON,
        "at": now.isoformat(),
    }
    return {**payload, "dedup": trace}


def _record_superseded_by(loser: Job, nj: NormalizedJob, now: datetime) -> None:
    """Note on the thin row that a fuller copy of the same role now exists.

    Deliberately *not* filed under ``suppressed``: this posting was not dropped,
    and a trace that said it was would be a lie told to whoever comes looking.
    Nothing else about the row changes — it may already be shortlisted or
    applied to, and dedup does not get to overrule that.
    """
    payload = dict(loser.payload or {})
    trace = dict(payload.get("dedup") or {})
    trace["superseded_by"] = {
        "id": nj.id,
        "source": nj.source,
        "url": nj.url,
        "reason": SUPERSEDE_REASON,
        "at": now.isoformat(),
    }
    payload["dedup"] = trace
    loser.payload = payload


def _persist_one(
    session: Session,
    nj: NormalizedJob,
    index: _Index,
    now: datetime,
    run_id: int | None,
    cross_source: bool,
) -> tuple[str, Job | None]:
    """Write one job; say what happened and which row now covers its key.

    Returns ``(kind, row)`` with ``kind`` one of ``updated`` / ``inserted`` /
    ``superseded`` / ``duplicate``. Touches no counters and no index: the caller
    runs this inside a savepoint and must only account for it once the
    savepoint has committed.
    """
    # Imported here, not at module scope, and this is not a style choice.
    # ``companies.service`` needs ``crawler.text``, and importing any submodule
    # of ``jobpilot.crawler`` runs its ``__init__``, which eagerly imports *this*
    # module — so a top-level import works only when the crawler happens to be
    # imported first, and raises ImportError when anything reaches
    # ``companies.service`` directly. Alembic's 0011 does exactly that.
    from jobpilot.companies.service import link_job

    existing = session.get(Job, nj.id)
    if existing is not None:
        _refresh(existing, nj, now)
        # Re-resolved on every refresh, not only on insert. A board that
        # corrects its own spelling of an employer should move the job onto
        # the right company row, and a job stored before this column existed
        # has to pick one up somewhere. One SELECT on a unique index, and
        # after the first crawl the employer nearly always has a row already.
        link_job(session, existing)
        # Now inside the window by definition, so it covers its own key for
        # the rest of this batch — a job that has just been re-seen must not
        # let another board's copy in behind it.
        return "updated", existing

    kind = "inserted"
    incumbent = (
        index.covering(nj.dedup_key, nj.dedup_level, source=nj.source, title=nj.title)
        if cross_source
        else None
    )
    if incumbent is not None:
        if _has_usable_jd(nj.payload) and not _has_usable_jd(incumbent.job.payload):
            # Keep both and say which is which. The incumbent may already be
            # shortlisted or applied to, so it is annotated, never deleted
            # or demoted — this module does not own anybody's decisions.
            _record_superseded_by(incumbent.job, nj, now)
            nj.payload = _record_supersedes(nj.payload, incumbent.job, now)
            log.info(
                "dedup: keeping %s despite matching %s — %s",
                nj.id,
                incumbent.job.id,
                SUPERSEDE_REASON,
                extra={
                    "event": "dedup_superseded",
                    "job_id": nj.id,
                    "covered_by": incumbent.job.id,
                    "dedup_key": nj.dedup_key,
                },
            )
            kind = "superseded"
        else:
            _record_suppressed(incumbent.job, nj, now)
            log.info(
                "dedup: skipped %s (%s) — already covered by %s (%s)",
                nj.id,
                nj.source,
                incumbent.job.id,
                incumbent.job.source,
                extra={
                    "event": "dedup_skipped",
                    "job_id": nj.id,
                    "covered_by": incumbent.job.id,
                    "dedup_key": nj.dedup_key,
                    "level": nj.dedup_level,
                },
            )
            return "duplicate", None

    job = _new_job(nj, now, run_id=run_id)
    session.add(job)
    link_job(session, job)
    return kind, job


def persist_jobs(
    session: Session,
    jobs: list[NormalizedJob],
    *,
    dedup_days: int = 14,
    now: datetime | None = None,
    run_id: int | None = None,
) -> CrawlStats:
    """Insert/refresh ``jobs``; skip cross-source dupes seen within ``dedup_days``.

    Flushes (does not commit) — the caller owns the transaction boundary.
    """
    now = now or vn_now()
    stats = CrawlStats()
    cutoff = now - timedelta(days=dedup_days)

    # Preload postings still inside the window so we don't re-add the same role.
    # `payload` is deferred: it carries the whole JD, it is only needed for the
    # handful of rows that actually collide, and loading it for every job in the
    # window would pull the entire corpus of descriptions into memory to answer
    # a question about titles.
    # ``dedup_days: 0`` means "show me every board's version", and it has to
    # switch the layer off rather than merely narrow the window to zero: rows
    # touched by *this* batch land on `now` and would go on shadowing each other.
    cross_source = dedup_days > 0

    index = _Index()
    if cross_source:
        for job in session.scalars(
            select(Job).where(Job.last_seen_at >= cutoff).options(defer(Job.payload))
        ):
            index.add(job)

    touched: list[Job] = []
    for nj in jobs:
        # One savepoint per job. Postgres enforces column widths and constraints
        # that SQLite never checks, and a violation surfaces mid-flush — which
        # without a savepoint leaves the session unusable, so one bad posting
        # used to fail its own site *and every site crawled after it*. Now it
        # costs exactly that one row, counted in `rejected`.
        try:
            with session.begin_nested():
                kind, row = _persist_one(session, nj, index, now, run_id, cross_source)
        except SQLAlchemyError as exc:
            log.warning(
                "persist: skipped %s — %s",
                nj.id,
                (str(getattr(exc, "orig", None) or exc).splitlines() or [""])[0],
                extra={"event": "persist_failed", "job_id": nj.id},
            )
            stats.rejected += 1
            continue
        # Indexed only once the savepoint has committed: a row the database
        # refused must not go on shadowing other boards' copies of the role.
        if row is not None:
            index.add(row, nj.dedup_level)
        if kind == "duplicate":
            stats.duplicates += 1
            continue
        if kind == "updated":
            stats.updated += 1
        else:
            stats.inserted += 1
            if kind == "superseded":
                stats.superseded += 1
        if nj.fresh:
            stats.fresh += 1
        if row is not None:
            touched.append(row)

    session.flush()
    # Re-listings: point every copy of a posting at its newest member, so the
    # list shows one row per posting (``crawler/reposts.py``). After the loop,
    # once per employer+title, not per row: a crawl re-sees most of a board.
    seen_groups: set[tuple] = set()
    for row in touched:
        group_key = (row.company_id, dedup_key(row.company, row.title), row.source, row.title)
        if row.company_id is None or group_key in seen_groups:
            continue
        seen_groups.add(group_key)
        relink(session, row)
    session.flush()
    return stats
