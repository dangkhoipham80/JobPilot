"""Resolve an employer string to a ``Company`` row, and keep jobs linked to one.

One rule, three callers — the crawler's ``persist_jobs``, ``POST``/``PATCH
/jobs``, and the backfill. They must agree, because disagreeing means the same
employer gets two rows and its HR contacts end up split across them with nothing
on screen to say so.

The identity key is ``text.normalize_company(..., strip_legal=True)``. The
display name is cosmetic and editable; the key is what a job actually links on.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from jobpilot.crawler.text import clean_text, normalize_company
from jobpilot.store.models import Company, Job

log = logging.getLogger(__name__)

#: Read off the columns rather than typed out, so a widened column cannot leave
#: a clamp behind at the old number. Both are the same width today; treating
#: them as one constant would hide it the day they aren't.
_NAME_WIDTH = Company.__table__.c.name.type.length
_KEY_WIDTH = Company.__table__.c.normalized_name.type.length


def company_key(name: str | None) -> str:
    """The fold two spellings of one employer have to share. ``""`` if unusable.

    Clamped **here**, not at the insert. The key is what every lookup selects on,
    so clamping it later would mean searching for the full fold and storing the
    truncated one: the SELECT never matches, the INSERT trips the unique
    constraint, and the re-read after that IntegrityError searches for the full
    fold again and comes back empty — ``resolve_company`` returning ``None`` for
    a company that exists. SQLite ignores VARCHAR widths, so only Postgres would
    ever have shown it.
    """
    return normalize_company(name, strip_legal=True)[:_KEY_WIDTH]


def resolve_company(db: Session, name: str | None, *, create: bool = True) -> Company | None:
    """The ``Company`` row for ``name``, creating it when there isn't one.

    Returns ``None`` for a name that folds to nothing — a blank employer, or one
    written entirely in punctuation. That is deliberately not an error: a job
    with no company name is a job with no company name, and inventing a row
    called ``""`` to hang it off would put a nameless card on /companies for
    every such posting.

    The insert runs in a SAVEPOINT so a lost race on the unique key costs a
    re-read rather than the caller's whole transaction. Two API workers pasting
    jobs at the same employer at the same moment is rare; a rolled-back crawl
    batch because of it would not be.
    """
    key = company_key(name)
    if not key:
        return None

    row = db.scalar(select(Company).where(Company.normalized_name == key))
    if row is not None or not create:
        return row

    try:
        with db.begin_nested():
            row = Company(name=_display_name(name, key), normalized_name=key)
            db.add(row)
    except IntegrityError:
        # Somebody else inserted the same key between the SELECT and the flush.
        # Their row is as good as ours would have been — the key is the identity.
        row = db.scalar(select(Company).where(Company.normalized_name == key))
    return row


def _display_name(name: str | None, key: str) -> str:
    """The spelling to show, clamped to the column that has to hold it."""
    return (clean_text(name) or key)[:_NAME_WIDTH]


def link_job(db: Session, job: Job) -> Company | None:
    """Point ``job.company_id`` at the employer its ``company`` string names.

    Called on every write path. Re-linking on an edit is the point: correcting a
    misspelled employer should move the job to the right company, and leaving
    the old link would make the fix invisible on the only page that groups by
    employer.

    A job whose name folds to nothing keeps whatever link it had. Clearing it
    would be a silent unlink triggered by an unrelated edit — the shape of bug
    that has already cost this repo two rounds of review.
    """
    company = resolve_company(db, job.company)
    if company is not None:
        job.company_id = company.id
    return company


@dataclass
class LinkResult:
    """What a bulk link pass did, in numbers a caller can print."""

    created: int = 0
    linked: int = 0
    #: Jobs whose employer string folds to nothing. Counted rather than ignored:
    #: "nothing to link" and "failed to link" look identical in a total.
    unlinkable: int = 0


def link_all_jobs(db: Session) -> LinkResult:
    """Provision a company per distinct employer and link every job to one.

    Idempotent, and safe to re-run after the fold changes — which is the repair
    path when it does. Flushes; the caller owns the commit.

    The display name of a company *this pass creates* is the spelling most of
    its jobs use, so a corpus holding "GitLab" eleven times and "gitlab" three
    times shows "GitLab". Ties go to the shortest spelling, then alphabetically,
    so two runs over the same data cannot disagree and a one-all tie between
    "Foo" and "Cong ty TNHH Foo" shows the name rather than the paperwork. Rows
    that already exist are never renamed: by then the name may have been
    corrected by hand, and a backfill that overwrites a correction is a backfill
    nobody can trust.

    **Every column is named explicitly, and no ORM entity is loaded.** Alembic's
    0011 calls this to backfill, so it runs against the schema as it stood at
    that revision. ``select(Job)`` would emit every column the *model* has today,
    which is fine right now and breaks the first time a later migration adds one:
    a fresh ``alembic upgrade head`` would fail at 0011 with UndefinedColumn, on
    a column that does not exist yet at that point in history. Naming the three
    columns this pass actually touches makes it immune to additions. (A *rename*
    of ``jobs.company`` would still break it — loudly, which is the trade the
    migration's docstring takes.)
    """
    jobs_t, companies_t = Job.__table__, Company.__table__
    rows = db.execute(
        select(jobs_t.c.id, jobs_t.c.company, jobs_t.c.company_id)
    ).all()

    by_key: dict[str, list[tuple]] = defaultdict(list)
    result = LinkResult()
    for row in rows:
        key = company_key(row.company)
        if not key:
            result.unlinkable += 1
            continue
        by_key[key].append(row)

    existing = dict(
        db.execute(
            select(companies_t.c.normalized_name, companies_t.c.id).where(
                companies_t.c.normalized_name.in_(list(by_key))
            )
        ).all()
    )

    for key, group in by_key.items():
        company_id = existing.get(key)
        if company_id is None:
            spellings = Counter(clean_text(r.company) for r in group)
            best = min(spellings.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[0]
            company_id = db.execute(
                insert(companies_t)
                .values(name=_display_name(best, key), normalized_name=key)
                .returning(companies_t.c.id)
            ).scalar_one()
            result.created += 1
        stale = [r.id for r in group if r.company_id != company_id]
        if stale:
            db.execute(
                update(jobs_t).where(jobs_t.c.id.in_(stale)).values(company_id=company_id)
            )
            result.linked += len(stale)

    db.flush()
    # The UPDATEs above are Core statements against the table, so the session's
    # identity map does not learn about them: a `Job` already loaded here would
    # keep reporting its old `company_id` for the rest of the transaction, and
    # the caller has no way to tell that from a link that did not happen.
    db.expire_all()
    log.info(
        "companies: created %d, linked %d job(s), %d unlinkable",
        result.created,
        result.linked,
        result.unlinkable,
        extra={"event": "companies_linked", **result.__dict__},
    )
    return result
