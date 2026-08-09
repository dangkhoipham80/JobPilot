"""Which source is worth crawling — outcomes sliced by where the job came from.

``apply/outcome.outcome_counts`` answers "how is the search going" for the whole
corpus. This module answers the narrower question the roadmap actually asked
(``PLAN.md §9.1`` slot 20): *given a finite evening, which board should I crawl
again?* That needs the same numbers cut by source, by channel and by level, plus
how long an answer takes and which ads keep coming back.

Four decisions worth defending, because each one has a plausible wrong version.

**Every rate is built from ``reached``, never from ``current``.** An application
that interviewed twice and was then rejected sits in ``current`` only under
``rejected``. Counting interviews that way reports the applications *stuck* in
interviews rather than the ones that *got* one — a number that falls when things
go well. This is the same rule ``outcome_counts`` defends, restated here because
this module recomputes per bucket rather than calling it.

**A rate below :data:`MIN_SAMPLE` is ``None``, and the bucket says ``sent``
instead.** Slicing is exactly what makes samples small: a corpus of eighty
applications cut five ways is five buckets of sixteen, and one lucky reply out
of three reads as "33%" next to a board with two hundred. ``outcome_counts``
only suppresses a rate when the denominator is zero, which is right for a single
whole-corpus number; it is not enough once you invite the reader to *compare*
buckets. Callers render ``n=<sent>`` where ``rate is None``.

**No answer yet is not a slow answer.** An application still waiting is left out
of the time-to-reply median entirely and counted in ``still_waiting``. Folding
it in as "so far N days" would drag the median up every day nobody writes back,
so the number would get worse precisely while nothing happened — and a silence
you have not given up on is not a data point about speed.

**A repeated posting is a signal, not a verdict.** Two openings with the same
title at the same company are ordinary; an ad reposted every three weeks for
half a year is worth a look. This module reports the shape — how many distinct
postings, over how many days — and lets a human read it. It never labels a job
"ghost", because the evidence available here cannot support that word.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from statistics import median

from jobpilot.apply.followup import SENT_RESULTS
from jobpilot.apply.inbox import fold
from jobpilot.apply.outcome import ANSWERED_BY, INTERVIEW, OFFER
from jobpilot.timeutil import VN_TZ

#: Below this many *sent applications*, a bucket reports counts and no rate.
#: Same reasoning and same number as ``llm/stats.MIN_SAMPLE`` and
#: ``analytics/market.MIN_SAMPLE`` — kept as its own name because it is a
#: different denominator (applications, not calls or ads) and the three are free
#: to diverge without dragging each other.
MIN_SAMPLE = 8

#: A group has to reach this many distinct postings before it is worth showing
#: as "reposted". Two is normal hiring; this is the point where a pattern starts.
REPEAT_MIN_POSTINGS = 3

#: How many repeat groups the endpoint returns. Any drop is declared in the
#: payload (``total_groups``) rather than silently truncated.
REPEAT_LIMIT = 20


def _aware(value: datetime | None) -> datetime | None:
    """Naive timestamps are stored local; SQLite returns them naive, Postgres aware.

    Same guard as ``outcome._aware``. Comparing the two forms raises on one
    backend and works on the other, which is the kind of difference that only
    shows up where the tests are not looking.
    """
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=VN_TZ)


@dataclass
class Bucket:
    """One row of a split: a source, a channel or a level."""

    key: str
    #: Applications that really went out. The denominator for every rate here.
    sent: int = 0
    #: Applications where a human on their side answered at all.
    answered: int = 0
    #: Applications that ever reached an interview, from the event log.
    interviewed: int = 0
    offered: int = 0
    #: ``None`` below :data:`MIN_SAMPLE` — see the module docstring.
    reply_rate: float | None = None
    interview_rate: float | None = None
    #: True when the bucket is too thin to state a rate. Callers show ``sent``.
    thin: bool = True

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Split:
    """One chart's worth of buckets, with the caveat attached."""

    rows: list[dict] = field(default_factory=list)
    #: Applications that carried a value for this dimension.
    covered: int = 0
    #: Applications considered in total.
    total: int = 0
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _rate(numerator: int, denominator: int) -> float | None:
    if not denominator:
        return None
    return round(numerator / denominator, 4)


def _bucket(key: str, sent: int, answered: int, interviewed: int, offered: int) -> Bucket:
    thin = sent < MIN_SAMPLE
    return Bucket(
        key=key,
        sent=sent,
        answered=answered,
        interviewed=interviewed,
        offered=offered,
        # Suppressed rather than rounded: the caller must not be able to render
        # a percentage that the sample cannot support.
        reply_rate=None if thin else _rate(answered, sent),
        interview_rate=None if thin else _rate(interviewed, sent),
        thin=thin,
    )


def _rows(db) -> list[dict]:
    """One row per real application, carrying its dimensions and its outcomes.

    Built in two queries — the applications, then the event log — and joined in
    Python. A single query with three correlated ``COUNT(DISTINCT ...)``
    subqueries says the same thing far less legibly, and the corpus is hundreds
    of rows, not millions. Same trade-off ``analytics/market`` already makes.
    """
    from sqlalchemy import select

    from jobpilot.store.models import Application, ApplicationEvent, Job

    real = Application.result.in_(tuple(SENT_RESULTS))

    apps = db.execute(
        select(
            Application.id,
            Application.channel,
            Application.submitted_at,
            Job.source,
            Job.level,
        )
        .join(Job, Job.id == Application.job_id)
        .where(real)
    ).all()

    # Which stages each application ever reached, and when it was first answered.
    reached: dict[int, set[str]] = defaultdict(set)
    first_answer: dict[int, datetime] = {}
    events = db.execute(
        select(
            ApplicationEvent.application_id,
            ApplicationEvent.event_type,
            ApplicationEvent.occurred_at,
        )
        .join(Application, Application.id == ApplicationEvent.application_id)
        .where(real)
        .where(ApplicationEvent.is_retracted.is_(False))
    ).all()
    for app_id, event_type, occurred_at in events:
        reached[app_id].add(event_type)
        if event_type in ANSWERED_BY:
            when = _aware(occurred_at)
            if when is not None and (app_id not in first_answer or when < first_answer[app_id]):
                first_answer[app_id] = when

    out = []
    for app_id, channel, submitted_at, source, level in apps:
        stages = reached.get(app_id, set())
        out.append(
            {
                "id": app_id,
                "source": source,
                "channel": channel,
                "level": level,
                "submitted_at": _aware(submitted_at),
                # An interview *is* a reply even when nobody typed "replied"
                # first — see ``outcome_counts``, same reasoning.
                "answered": bool(stages & ANSWERED_BY),
                "interviewed": INTERVIEW in stages,
                "offered": OFFER in stages,
                "first_answer_at": first_answer.get(app_id),
            }
        )
    return out


def _split(rows: list[dict], dimension: str, unknown: str) -> Split:
    """Group ``rows`` by one dimension and turn each group into a :class:`Bucket`."""
    groups: dict[str, list[dict]] = defaultdict(list)
    covered = 0
    for row in rows:
        value = row.get(dimension)
        if value:
            covered += 1
            groups[str(value)].append(row)
        else:
            # Kept as its own bucket rather than dropped: "we don't know the
            # level" is a fact about the corpus, and hiding it would make the
            # buckets sum to less than the total with no explanation.
            groups[unknown].append(row)

    buckets = [
        _bucket(
            key,
            sent=len(members),
            answered=sum(1 for m in members if m["answered"]),
            interviewed=sum(1 for m in members if m["interviewed"]),
            offered=sum(1 for m in members if m["offered"]),
        )
        for key, members in groups.items()
    ]
    # Most-sent first, then by key so equal counts do not reorder between calls.
    buckets.sort(key=lambda b: (-b.sent, b.key))

    total = len(rows)
    note = ""
    if total == 0:
        note = "No application has been sent yet."
    elif all(b.thin for b in buckets):
        note = (
            f"Every {dimension} has fewer than {MIN_SAMPLE} sent applications — "
            "counts only, no rates."
        )
    return Split(rows=[b.as_dict() for b in buckets], covered=covered, total=total, note=note)


def time_to_first_reply(rows: list[dict]) -> dict:
    """How long an answer takes, in days, over the applications that got one.

    Median rather than mean: one company that replied after eight months would
    otherwise move the headline number more than the twenty that replied in a
    week.

    ``still_waiting`` is reported next to it and is never folded in — see the
    module docstring.
    """
    waits: list[float] = []
    still_waiting = 0
    undated = 0
    for row in rows:
        sent_at, answer_at = row["submitted_at"], row["first_answer_at"]
        if sent_at is None:
            # Sent, but we do not know when. Not a zero-day reply.
            undated += 1
            continue
        if answer_at is None:
            still_waiting += 1
            continue
        waits.append(round((answer_at - sent_at).total_seconds() / 86400, 2))

    return {
        "answered": len(waits),
        "still_waiting": still_waiting,
        "undated": undated,
        "median_days": round(median(waits), 2) if waits else None,
        "fastest_days": min(waits) if waits else None,
        "slowest_days": max(waits) if waits else None,
        # Same suppression rule as the buckets: a median of two numbers is two
        # numbers, and presenting it as a typical wait invites a wrong decision.
        "thin": len(waits) < MIN_SAMPLE,
    }


def repeat_postings(db, *, limit: int = REPEAT_LIMIT) -> dict:
    """Ads that keep coming back, grouped by company + title.

    Grouped on the **folded** company and title (``inbox.fold``) so that
    ``"Công ty TNHH X"`` and ``"CONG TY TNHH X"`` are one employer rather than
    two — the same normalisation the market facets needed for city names.

    Dedup by ``id`` already collapses the *same* ad re-crawled; what reaches
    here is genuinely distinct postings, which is why a repeat is interesting at
    all. Reported as a shape, never as a verdict.
    """
    from sqlalchemy import select

    from jobpilot.store.models import Job

    jobs = db.execute(select(Job.id, Job.company, Job.title, Job.source, Job.posted_at)).all()

    groups: dict[tuple[str, str], list[tuple]] = defaultdict(list)
    for job_id, company, title, source, posted_at in jobs:
        key = (fold(company or ""), fold(title or ""))
        if not key[0] or not key[1]:
            # No company or no title is not a repeat of anything.
            continue
        groups[key].append((job_id, company, title, source, _aware(posted_at)))

    found = []
    for (_company_key, _title_key), members in groups.items():
        if len(members) < REPEAT_MIN_POSTINGS:
            continue
        dates = sorted(d for *_, d in members if d is not None)
        found.append(
            {
                "company": members[0][1],
                "title": members[0][2],
                "postings": len(members),
                "sources": sorted({m[3] for m in members}),
                "first_posted": dates[0].date().isoformat() if dates else None,
                "last_posted": dates[-1].date().isoformat() if dates else None,
                # None, not 0, when the postings carry no dates: an undated
                # spread is unknown, and 0 would read as "all on the same day".
                "span_days": (dates[-1] - dates[0]).days if len(dates) >= 2 else None,
                "undated_postings": sum(1 for *_, d in members if d is None),
            }
        )

    found.sort(key=lambda g: (-g["postings"], g["company"], g["title"]))
    return {
        "rows": found[:limit],
        # Declared, not silent: a caller that shows 20 of 57 groups has to be
        # able to say so.
        "total_groups": len(found),
        "shown": min(len(found), limit),
        "min_postings": REPEAT_MIN_POSTINGS,
    }


def outcome_analytics(db) -> dict:
    """Everything the dashboard section needs, in one pass over the rows."""
    rows = _rows(db)
    return {
        "min_sample": MIN_SAMPLE,
        "total_sent": len(rows),
        "by_source": _split(rows, "source", "unknown").as_dict(),
        "by_channel": _split(rows, "channel", "unknown").as_dict(),
        "by_level": _split(rows, "level", "unknown").as_dict(),
        "timing": time_to_first_reply(rows),
        "repeats": repeat_postings(db),
    }
