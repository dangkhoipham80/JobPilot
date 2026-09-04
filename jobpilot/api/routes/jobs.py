"""Job listing, detail, and early-funnel actions (shortlist / skip)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from jobpilot.api.deps import get_db, require_token
from jobpilot.api.paging import LimitParam, OffsetParam, page_list, page_query
from jobpilot.api.schemas import JobDetailOut, JobIn, JobOut, JobPatch, Page
# Imported by name, not as a module: `jobpilot.crawler` re-exports a *function*
# called `normalize`, so `from jobpilot.crawler import normalize` binds that and
# any attribute access on it fails at runtime rather than at import.
from jobpilot.crawler.normalize import (
    COLUMN_WIDTHS,
    Enrichment,
    enrich,
    fit_column,
)
from jobpilot.crawler.quality import crawl_passes
from jobpilot.api.ws import manager
from jobpilot.config import get_config
from jobpilot.store.models import Job, JobStatus
from jobpilot.timeutil import vn_now

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_token)])

_SLUG_UNSAFE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _SLUG_UNSAFE.sub("-", text.lower()).strip("-")[:80] or "job"


def _native_id(url: str) -> str:
    """A stable id from a posting URL. LinkedIn ids are the useful case:
    /jobs/view/4012345678 -> linkedin-4012345678, so re-pasting updates."""
    if not url:
        return ""
    linkedin = re.search(r"linkedin\.com/(?:comm/)?jobs/view/(\d+)", url, re.I)
    if linkedin:
        return f"linkedin-{linkedin.group(1)}"
    return _slug(url.split("?")[0].rstrip("/").rsplit("/", 1)[-1])


# Statuses from which a user may still shortlist/skip (before the tailor stage).
_EARLY = {JobStatus.DISCOVERED, JobStatus.SHORTLISTED, JobStatus.SKIPPED}


def _forget_readings(payload: dict, *, keep_sections: bool = False) -> None:
    """Drop what a model concluded about a description that has since changed.

    Two things in ``payload`` are readings *of* ``description_md`` rather than
    facts about the job: ``sections`` (the posting's lines, bucketed) and
    ``fit`` (how the CV answers them). Rewrite the description and both become
    statements about a posting that no longer exists — and neither says so.
    The buckets are the worse of the two, because they are presented as the ad's
    own words: a reader would see "Required: Java" quoted beside a description
    that now asks for Python, with a toggle implying the two are the same text.

    Dropped, not kept and flagged. "Nobody has read this one yet" is true, and
    the button to read it is on the same screen; "here is a reading of a
    different posting" is a lie with a toggle in front of it. The quality flags
    and analytics facets are *not* dropped here — they are recomputed from the
    new text a few lines later, which is the better answer where it is available.
    """
    if not keep_sections:
        payload.pop("sections", None)
    payload.pop("fit", None)


def _merged_payload(payload: dict, signals: Enrichment, stated: str | None) -> dict:
    """Fold the re-derived facets into a job's payload, one rule for both writers.

    The rule is about ``work_mode`` and only ``work_mode``: whoever *stated* it
    wins, and the value read off the location label is the fallback. A model
    that read "Hybrid (2 days in office)" out of the body knows more than a
    regex over "Ho Chi Minh City" does, and a user who typed it knows more than
    both.

    A shared helper because the two endpoints had two orderings and therefore
    two behaviours: ``create_job`` put the stated value after the derived facets
    and kept it, ``patch_job`` spread ``signals.payload`` last and silently
    dropped it — so editing the description of a remote job through the Job
    description card erased its work mode for good. Neither test caught it,
    because each endpoint was only ever tested against its own ordering.
    """
    derived = dict(signals.payload)
    fallback = derived.pop("work_mode", None)
    return {**payload, **derived, "work_mode": stated or payload.get("work_mode") or fallback}


def _apply_signals(job: Job, signals: Enrichment) -> None:
    """Write the crawler's derivations onto a job edited through the API.

    ``match_score`` is the one field held back once a job has been tailored.
    Two different measurements share that column: before a tailor round it is
    ``stack_match_score`` — how much of your configured stack the posting
    mentions — and ``tailor_job`` then replaces it with the plan's requirement
    coverage, which is a far better answer because a model read both sides. A
    later edit re-running the cheap one would silently downgrade the number the
    Jobs list sorts by, and nothing on screen distinguishes the two.

    The payload copy is always refreshed, so ``quality`` and the analytics facets
    still follow the text they describe.
    """
    job.level = signals.level
    # `status is None` is a row that has not been flushed yet: the column default
    # is applied by the database, not by the constructor, so a job being created
    # right now has no status to compare. Reading that as "not early" left every
    # hand-added job scoring 0.0 — the exact bug this function exists to fix.
    if job.status is None or job.status in _EARLY:
        job.match_score = signals.match_score


@router.get("", response_model=Page[JobOut])
def list_jobs(
    db: Session = Depends(get_db),
    source: str | None = None,
    status: JobStatus | None = None,
    level: str | None = None,
    q: str | None = Query(None, description="search title/company"),
    fresh: bool = False,
    run_id: int | None = Query(None, description="only jobs discovered by this crawl"),
    crawled_after: datetime | None = Query(None, description="crawled at or after this time"),
    order: str = Query("posted", pattern="^(posted|crawled)$"),
    limit: int = LimitParam(),
    offset: int = OffsetParam(),
) -> dict:
    stmt = select(Job)
    if source:
        stmt = stmt.where(Job.source == source)
    if status:
        stmt = stmt.where(Job.status == status)
    if level:
        stmt = stmt.where(Job.level == level)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Job.title.ilike(like), Job.company.ilike(like)))
    if fresh:
        cutoff = vn_now() - timedelta(hours=get_config().crawl.fresh_hours)
        stmt = stmt.where(Job.posted_at >= cutoff)
    if run_id is not None:
        stmt = stmt.where(Job.run_id == run_id)
    if crawled_after is not None:
        stmt = stmt.where(Job.crawled_at >= crawled_after)

    # Default: freshest posting first. "crawled" answers a different question —
    # what did the agent turn up most recently — so it is a separate ordering
    # rather than a tweak of the same one.
    #
    # `Job.id` last is what makes the order total. `posted_at` is null for a
    # LinkedIn alert and identical across a whole crawl batch, so without a
    # unique tie-break the database is free to order the ties differently
    # between the page-1 and page-2 queries — and then a job shows up twice
    # while another is never shown.
    key = Job.crawled_at if order == "crawled" else Job.posted_at
    stmt = stmt.order_by(key.desc(), Job.crawled_at.desc(), Job.id.desc())
    rows, total = page_query(db, stmt, limit, offset)
    return page_list([JobOut.model_validate(r) for r in rows], total, limit, offset)


@router.post("", response_model=JobDetailOut, status_code=201)
async def create_job(body: JobIn, db: Session = Depends(get_db)) -> JobDetailOut:
    """Add a job by hand (source ``manual``).

    The escape hatch for postings no crawler can reach — LinkedIn above all,
    whose robots.txt disallows automated access to job pages. Paste the JD and
    the rest of the pipeline treats it like any other job.
    """
    if not body.title.strip() or not body.company.strip():
        raise HTTPException(status_code=422, detail="title and company are required")

    now = vn_now()
    # Stable id from the URL when there is one, so pasting the same posting
    # twice updates it instead of creating a duplicate.
    native = _native_id(body.url) or _slug(f"{body.company}-{body.title}")
    job_id = f"manual:{native}"

    job = db.get(Job, job_id)
    if job is None:
        job = Job(id=job_id, source="manual", crawled_at=now)
        db.add(job)

    # This endpoint upserts — re-pasting the same posting updates it — so a
    # second paste with different text lands on a row still carrying the first
    # paste's buckets and fit report. Same staleness as the PATCH path, same
    # answer.
    payload = dict(job.payload or {})
    if body.description_md != payload.get("description_md", ""):
        _forget_readings(payload, keep_sections=body.sections is not None)

    job.url = body.url
    # Clamped to the column widths, exactly as the crawler clamps a scraped job.
    # Not belt-and-braces: `POST /jobs/intake` fills this form from a model that
    # was told to copy a salary label *verbatim*, and a posting that words its
    # pay as a sentence produces a 148-character "salary". Postgres answers an
    # overlong value with StringDataRightTruncation mid-flush — a 500 that names
    # no field, after the user has already paid for the model call that filled
    # the form in. SQLite ignores these widths, so only a real Postgres run ever
    # shows it.
    job.title = fit_column("title", body.title.strip())
    job.company = fit_column("company", body.company.strip())
    job.location = fit_column("location", body.location)
    job.salary = fit_column("salary", body.salary)
    job.apply_channel = body.apply_channel
    job.apply_target = body.apply_target or body.url or None
    job.posted_at = job.posted_at or now

    # The same derivations a crawled job gets. Without them a hand-added job
    # arrived with match_score 0.0, no quality flags and none of the analytics
    # facets: present on the Jobs page, invisible to /market, and sorted below
    # every crawled job in a list ordered by relevance — with nothing on screen
    # to explain why. `enrich` is the crawler's own arithmetic, called here
    # rather than reimplemented, so "thin JD" and "20 - 30 triệu" mean exactly
    # what they mean everywhere else.
    signals = enrich(
        cfg=get_config(),
        title=job.title,
        location=job.location,
        salary=job.salary,
        level=body.level,
        skills=body.skills,
        description_md=body.description_md,
        posted_at=job.posted_at,
        now=now,
    )
    _apply_signals(job, signals)
    job.payload = _merged_payload(
        {
            **payload,
            "skills": body.skills,
            "description_md": body.description_md,
            # Both kept. The buckets are a reading *of* the raw text and the raw
            # text stays the evidence, so storing only the buckets would throw
            # away the thing every guardrail downstream checks against.
            **({"sections": body.sections.model_dump()} if body.sections else {}),
        },
        signals,
        body.work_mode,
    )
    db.commit()
    db.refresh(job)
    await manager.broadcast({"type": "job_updated", "id": job.id, "status": job.status.value})
    return JobDetailOut.from_job(job)


@router.patch("/{job_id:path}", response_model=JobDetailOut)
async def patch_job(job_id: str, body: JobPatch, db: Session = Depends(get_db)) -> JobDetailOut:
    """Edit a job — mainly to paste in a description the source didn't carry.

    LinkedIn alert emails announce a job but not its text, so this is how a
    job goes from "found" to "tailorable".
    """
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    patch = body.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(status_code=422, detail="nothing to change")

    payload = dict(job.payload or {})
    rewrote_jd = "description_md" in patch and patch["description_md"] != payload.get(
        "description_md"
    )
    for field in ("description_md", "skills", "work_mode"):
        if field in patch:
            payload[field] = patch.pop(field)
    if "sections" in patch:
        sections = patch.pop("sections")
        payload["sections"] = sections.model_dump() if hasattr(sections, "model_dump") else sections
    if rewrote_jd:
        _forget_readings(payload, keep_sections="sections" in body.model_dump(exclude_none=True))
    # A pasted description means the job no longer needs one.
    if "description_md" in (body.model_dump(exclude_none=True)):
        payload.pop("needs_jd", None)

    for field, value in patch.items():
        # Same clamp as `create_job`, and for the same reason — this endpoint
        # takes the same fields from the same form.
        setattr(job, field, fit_column(field, value) if field in COLUMN_WIDTHS else value)

    # Re-derive after the edit, not before: pasting a description into a
    # LinkedIn alert is the whole point of this endpoint, and it turns a job
    # flagged `no_jd` with match_score 0.0 into one the tailor can actually work
    # from. Leaving the old signals in place would keep the job reading as
    # untailorable on every screen that shows a flag, right after the user fixed
    # the thing the flag was about.
    signals = enrich(
        cfg=get_config(),
        title=job.title,
        location=job.location,
        salary=job.salary,
        level=job.level,
        skills=payload.get("skills") or [],
        description_md=payload.get("description_md") or "",
        posted_at=job.posted_at,
        needs_jd=bool(payload.get("needs_jd")),
    )
    _apply_signals(job, signals)
    job.payload = _merged_payload(payload, signals, body.work_mode)

    db.commit()
    db.refresh(job)
    await manager.broadcast({"type": "job_updated", "id": job.id, "status": job.status.value})
    return JobDetailOut.from_job(job)


@router.get("/{job_id:path}", response_model=JobDetailOut)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobDetailOut:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    # Detail view only. This is the page read before spending an LLM call and
    # half an hour on a posting, so it is where "nobody has seen this lately"
    # earns a query; the list would pay for it on every row.
    passes = crawl_passes(db, [job.source]).get(job.source, [])
    return JobDetailOut.from_job(job, passes)


async def _transition(job_id: str, target: JobStatus, db: Session) -> JobDetailOut:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status not in _EARLY:
        raise HTTPException(
            status_code=409,
            detail=f"cannot {target.value.lower()} a job in status {job.status.value}",
        )
    job.status = target
    db.commit()
    db.refresh(job)
    await manager.broadcast({"type": "job_updated", "id": job.id, "status": job.status.value})
    return JobDetailOut.from_job(job)


@router.post("/{job_id:path}/shortlist", response_model=JobDetailOut)
async def shortlist_job(job_id: str, db: Session = Depends(get_db)) -> JobDetailOut:
    return await _transition(job_id, JobStatus.SHORTLISTED, db)


@router.post("/{job_id:path}/skip", response_model=JobDetailOut)
async def skip_job(job_id: str, db: Session = Depends(get_db)) -> JobDetailOut:
    return await _transition(job_id, JobStatus.SKIPPED, db)
