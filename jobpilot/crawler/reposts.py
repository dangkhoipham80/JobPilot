"""Collapse re-listings of one posting so the Jobs list shows the newest.

The dedup layer in ``persist.py`` stops a second copy *inside* its window
(``crawl.dedup_days``, measured from the last sighting). A board that takes a
posting down and lists it again a month later under a new id is outside that
window by construction, so the new id is inserted — correctly: it is the live
one, with the current JD and the link that still works. What was wrong is that
the old copies stayed on the list beside it. Measured on the live data
2026-10-14: 42 groups, 90 rows, e.g. one ITviec role listed three times in three
months under three ids with the same title and a near-identical JD.

So nothing is suppressed here. Every copy keeps its row (it may be shortlisted or
applied to), and each row in a group points at the group's newest member through
``jobs.latest_id``; the newest has ``latest_id = NULL``. The list hides rows that
point elsewhere unless the user has already acted on them.

**Which postings are one posting is not decided here.** It is the rule the
dedup layer already uses (``persist._same_posting``): the same dedup key, and on
the same board the same listed title — level word and parenthetical included —
because one board listing two titles has said they are two postings. A second
rule here would drift from that one; ``crawler/CLAUDE.md`` records what two
parallel normalisers cost this repo once already.

**Newest = last seen**, then first crawled, then id. ``last_seen_at`` is bumped
on every re-crawl, so a posting still live on its board stays the head of its
group even when an older copy is also still listed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, defer

from jobpilot.crawler.text import dedup_key, title_level
from jobpilot.store.models import Job


def _aware(when: datetime | None) -> datetime:
    """Comparable timestamps. A row loaded from SQLite comes back naive while a
    row created in this session is aware; Postgres returns aware for both."""
    if when is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _newest_key(job: Job) -> tuple:
    return (_aware(job.last_seen_at), _aware(job.crawled_at), job.id)


def group_of(session: Session, job: Job) -> list[Job]:
    """``job`` and every other row that is the same posting as it.

    Candidates share the employer row: ``company_id`` is indexed, and two
    postings at different employers are never one posting. A job with no
    employer link is a group of one.
    """
    if job.company_id is None:
        return [job]
    from jobpilot.crawler.persist import _same_posting, _Seen

    key = dedup_key(job.company, job.title)
    level = title_level(job.title)
    group = [job]
    others = session.scalars(
        select(Job)
        .where(Job.company_id == job.company_id, Job.id != job.id)
        .options(defer(Job.payload))
    )
    for other in others:
        if dedup_key(other.company, other.title) != key:
            continue
        seen = _Seen(job=other, level=title_level(other.title))
        if _same_posting(seen, level, job.source, job.title):
            group.append(other)
    return group


def relink(session: Session, job: Job) -> int:
    """Point every member of ``job``'s group at its newest member.

    Returns how many rows changed. Idempotent: a second call changes nothing.
    """
    return _point_at_newest(group_of(session, job))


def _point_at_newest(group: list[Job]) -> int:
    head = max(group, key=_newest_key)
    changed = 0
    for member in group:
        target = None if member is head else head.id
        if member.latest_id != target:
            member.latest_id = target
            changed += 1
    return changed


@dataclass
class RelinkResult:
    groups: int = 0  # groups with more than one member
    hidden: int = 0  # rows that now point at a newer copy
    changed: int = 0


def relink_all(session: Session) -> RelinkResult:
    """Recompute every group — the backfill for rows crawled before this existed."""
    result = RelinkResult()
    done: set[str] = set()
    jobs = session.scalars(select(Job).options(defer(Job.payload)).order_by(Job.id)).all()
    for job in jobs:
        if job.id in done:
            continue
        group = group_of(session, job)
        done.update(m.id for m in group)
        if len(group) > 1:
            result.groups += 1
        result.changed += _point_at_newest(group)
    session.flush()
    result.hidden = sum(1 for j in jobs if j.latest_id is not None)
    return result
