"""Job listing, detail, and early-funnel actions (shortlist / skip)."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urlsplit
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, defer

from jobpilot.api.deps import get_db, require_token
from jobpilot.api.paging import LimitParam, OffsetParam, page_list, page_query
from jobpilot.api.schemas import JobDetailOut, JobIn, JobOut, JobPatch, Page, RepostOut
# Imported from where the dispatcher defines them, so "email" cannot come to
# mean one thing at the endpoint that sets the channel and another at the code
# that reads it.
from jobpilot.apply.dispatcher import EMAIL
from jobpilot.apply.email import recipient_of
from jobpilot.companies.service import link_job
# Imported by name, not as a module: `jobpilot.crawler` re-exports a *function*
# called `normalize`, so `from jobpilot.crawler import normalize` binds that and
# any attribute access on it fails at runtime rather than at import.
from jobpilot.crawler.normalize import (
    COLUMN_WIDTHS,
    Enrichment,
    enrich,
    fit_column,
)
from jobpilot.crawler.persist import STATED_TARGET, target_is_stated
from jobpilot.crawler.quality import crawl_passes
from jobpilot.crawler.text import normalize_company, normalize_title
from jobpilot.crawler.types import HAND_ID_PREFIX, is_hand_added, make_job_id
from jobpilot.api.ws import manager
from jobpilot.config import get_config
from jobpilot.store.models import Job, JobStatus
from jobpilot.timeutil import vn_now

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_token)])


_SLUG_UNSAFE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _SLUG_UNSAFE.sub("-", text.lower()).strip("-")[:80] or "job"


#: Where Facebook keeps the identity of a post: in the query for a photo viewer,
#: a permalink.php or a notification link, in the path for everything else.
_FACEBOOK_QUERY = ("fbid", "story_fbid", "multi_permalinks")
_FACEBOOK_PATH = re.compile(r"/(?:posts|permalink|videos|share/p)/([\w.-]+)")

#: Hosts whose addresses name a place — a group, a feed — rather than a posting
#: unless one of the patterns above says otherwise.
_SOCIAL_HOSTS = ("facebook.com", "fb.com", "fb.me", "zalo.me")


#: A scheme at the very start. Not ``"://" in url``: a schemeless address can
#: carry another address in its query (``facebook.com/l.php?u=https://…``).
_HAS_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)


def _on(host: str, *domains: str) -> bool:
    return any(host == d or host.endswith(f".{d}") for d in domains)


def _native_id(url: str) -> tuple[str, bool]:
    """A stable id from a posting URL, and whether it names *one posting*.

    Only a LinkedIn job number is strong: it belongs to exactly one posting, so
    re-pasting that address lands on its row whatever the form now says. It is
    read from ``/jobs/view/<n>`` and from ``currentJobId=<n>``, which is what
    the address bar shows while browsing search results.

    Everything else is a guess that ``create_job`` checks against the row it
    finds. A Facebook post number names one *post* — and a recruiter's post
    lists several roles. A last path segment names less still:
    ``https://acme.example/careers`` is every job ACME has.

    A social address with no post in it yields nothing at all. Its last segment
    is the *group* (``/groups/<id>/?multi_permalinks=…`` once the query is cut
    off, ``zalo.me/g/<id>``), or the word ``photo``, or ``permalink.php`` — the
    same for every posting ever made there.
    """
    url = url.strip()
    if not url:
        return "", False
    # Copied without its scheme, an address has no host for `urlsplit` to find,
    # and every rule below that asks "is this Facebook" would answer no.
    if not _HAS_SCHEME.match(url):
        url = f"https://{url.lstrip('/')}"
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        return "", False
    query = parse_qs(parts.query)

    if _on(host, "linkedin.com"):
        viewed = re.search(r"/(?:comm/)?jobs/view/(\d+)", parts.path)
        number = viewed.group(1) if viewed else (query.get("currentJobId") or [""])[0].strip()
        # ASCII digits only: `str.isdigit` also says yes to "٣٤" and "12²".
        if re.fullmatch(r"[0-9]+", number):
            return f"linkedin-{number}", True
    if _on(host, "facebook.com", "fb.com", "fb.me"):
        in_path = _FACEBOOK_PATH.search(parts.path)
        # `multi_permalinks` can list several; the first is the one linked.
        candidates = [(query.get(key) or [""])[0].split(",")[0] for key in _FACEBOOK_QUERY]
        candidates.append(in_path.group(1) if in_path else "")
        for value in candidates:
            # Through the slug first: a value that is all punctuation is not an id.
            post = _SLUG_UNSAFE.sub("-", value.lower()).strip("-")
            if post:
                return f"facebook-{post[:80]}", False
    if _on(host, *_SOCIAL_HOSTS):
        return "", False
    return _slug(parts.path.rstrip("/").rsplit("/", 1)[-1] or host), False


def _as_listed(company: str | None, title: str | None) -> str:
    """Company and title as one posting states them — level and parenthetical kept.

    The strict comparison, not ``dedup_key``: that one forgives "Junior" and
    "(Java)" because two *boards* word one role differently. Here both sides
    came through the same form about the same address, so "Junior Backend
    Engineer" and "Senior Backend Engineer" are two jobs — the same reasoning
    ``persist._same_posting`` applies to two listings on one board.
    """

    def part(raw: str | None, normalised: str) -> str:
        # The normalisers keep Latin letters and digits, so a title written
        # wholly in another script comes out empty — and two empty strings are
        # equal. Where nothing survived, the text itself is compared.
        return normalised or " ".join((raw or "").casefold().split())

    return "|".join(
        (
            part(company, normalize_company(company)),
            part(title, normalize_title(title, strip_level=False, keep_parens=True)),
        )
    )


def _fallback_id(company: str, title: str, *, crowded: bool) -> str:
    """The id of a job no address identifies: a slug of its company and title.

    ``crowded`` is for the case the slug cannot tell two jobs apart — it keeps
    80 characters of Latin letters and digits, so a long legal name fills it
    before the title starts, and a title in another script adds nothing. Then a
    digest of the *exact* company and title is appended: the same job pasted
    again still finds its row, and no id that already exists changes.
    """
    slug = _slug(f"{company}-{title}")
    if not crowded:
        return slug
    digest = hashlib.sha1(f"{company}|{title}".casefold().encode("utf-8")).hexdigest()[:10]
    return f"{slug[:69]}-{digest}"


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


def _note_stated_target(job: Job, payload: dict, body_fields: dict) -> None:
    """Record that a person, not a scraper, chose where this application goes —
    and make the channel follow the address they chose.

    Two halves, because the first alone does nothing useful.

    **The flag.** ``persist._refresh`` reads it and stops overwriting the
    columns on the next crawl of that source; without it, picking an HR
    contact's address held until the nightly crawl and then silently reverted to
    the board's own URL — days later, with nothing on screen to show a decision
    had been undone.

    **The channel.** Every scraper in the repo hard-codes ``apply_channel`` to
    ``portal`` or ``external``; none of them ever emits ``email``, and
    ``dispatcher.resolve_channel`` trusts the declared column first. So on a
    crawled job — which is nearly every job — setting an HR address left the
    channel at ``external``, and applying produced a *handoff*: "open the link
    and submit it yourself", with ``hr@example.com`` as the link, and
    ``--open-portal`` steering a browser at it. No email was ever built. The
    hand-added case worked only by accident, because a job typed in by hand has
    no declared channel for ``resolve_channel`` to prefer.

    Promotion is deliberately one-directional: an address that parses as email
    switches the channel to ``email``, and anything else leaves the column
    alone. A board that said "portal" knows more about its own URLs than a guess
    made here does, and this only needs to fix the case it just created.

    Both stored/derived rather than inferred at read time so the database itself
    is true: the Applications board, Slack and the CLI all read ``channel``, and
    a rule that lived only inside ``resolve_channel`` would leave them showing
    the wrong one.
    """
    if "apply_target" not in body_fields:
        return
    payload["apply_target_source"] = STATED_TARGET
    if "apply_channel" not in body_fields and recipient_of(body_fields["apply_target"]):
        job.apply_channel = EMAIL


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
    match_min: float | None = Query(None, ge=0, le=1, description="match score at or above"),
    match_below: float | None = Query(None, ge=0, le=1, description="match score strictly below"),
    order: str = Query("crawled", pattern="^(posted|crawled|match)$"),
    reposts: bool = Query(
        False, description="include older listings of a re-listed posting (hidden by default)"
    ),
    limit: int = LimitParam(),
    offset: int = OffsetParam(),
) -> dict:
    stmt = select(Job)
    if not reposts:
        # One row per posting: an older listing of a re-listed role is hidden —
        # unless the user has acted on it. A shortlisted or applied-to copy is
        # their work, and the list is where they find it (crawler/reposts.py).
        stmt = stmt.where(
            or_(
                Job.latest_id.is_(None),
                Job.status.not_in([JobStatus.DISCOVERED, JobStatus.SKIPPED]),
            )
        )
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
    # A half-open band, [match_min, match_below): adjacent bands then share no
    # job and miss none, which two inclusive ends cannot do for a score that
    # sits exactly on the boundary — and with four configured stacks every
    # crawled score does (0.25, 0.5, 0.75, 1.0).
    if match_min is not None and match_below is not None and match_min >= match_below:
        # Refused rather than answered with an empty page: "no jobs in that
        # band" and "that is not a band" must not look the same.
        raise HTTPException(status_code=422, detail="match_min must be lower than match_below")
    if match_min is not None:
        stmt = stmt.where(Job.match_score >= match_min)
    if match_below is not None:
        stmt = stmt.where(Job.match_score < match_below)

    # Three orderings, because they answer three questions:
    #
    #   crawled (default)  what turned up most recently, best match first.
    #                      Grouped by crawl *day* — the same `date(crawled_at)`
    #                      the dashboard's by-day chart counts — and ranked by
    #                      match inside it. By exact timestamp the match score
    #                      would only ever break ties, and the morning crawl's
    #                      best job would sit under the evening crawl's worst.
    #   match              the best matches of everything, whenever found.
    #   posted             freshest posting first, by the board's own date;
    #                      postings with no date go after the dated ones.
    #
    # `Job.id` last is what makes each order total. `posted_at` is null for a
    # LinkedIn alert and identical across a whole crawl batch, and match scores
    # come in a handful of values, so without a unique tie-break the database
    # is free to order the ties differently between the page-1 and page-2
    # queries — and then a job shows up twice while another is never shown.
    #
    # Skipped jobs go last under every ordering. A job you passed on has had
    # its turn, and left in place it keeps holding a row among the ones still
    # waiting for a decision. It is the *first* key rather than a re-sort of
    # each page, so it holds across pages: page 1 is never padded with rows
    # you already dismissed. Filtering to one status makes it a constant.
    skipped_last = case((Job.status == JobStatus.SKIPPED, 1), else_=0)
    if order == "posted":
        # NULLS LAST, spelled out. Postgres sorts NULL *first* under DESC, so
        # "newest postings first" opened with the postings that have no date at
        # all; SQLite sorts it last, so no test ever saw it. Undated is not new.
        keys = (Job.posted_at.desc().nulls_last(), Job.crawled_at.desc())
    elif order == "match":
        keys = (Job.match_score.desc(), Job.crawled_at.desc())
    else:
        keys = (func.date(Job.crawled_at).desc(), Job.match_score.desc(), Job.crawled_at.desc())
    stmt = stmt.order_by(skipped_last, *keys, Job.id.desc())
    rows, total = page_query(db, stmt, limit, offset)
    # One grouped query for the page, not one per row.
    ids = [r.id for r in rows]
    counts = dict(
        db.execute(
            select(Job.latest_id, func.count()).where(Job.latest_id.in_(ids)).group_by(Job.latest_id)
        ).all()
    ) if ids else {}
    items = []
    for r in rows:
        out = JobOut.model_validate(r)
        out.reposts = counts.get(r.id, 0)
        items.append(out)
    return page_list(items, total, limit, offset)


@router.post("", response_model=JobDetailOut, status_code=201)
async def create_job(body: JobIn, db: Session = Depends(get_db)) -> JobDetailOut:
    """Add a job by hand.

    The escape hatch for postings no crawler can reach — LinkedIn above all,
    whose robots.txt disallows automated access to job pages, and anything
    posted in a Facebook or Zalo group. Paste the JD and the rest of the
    pipeline treats it like any other job.

    ``source`` is where the user says they found it (``manual`` when they do
    not). The id stays ``manual:<native>`` whatever the source: it is what makes
    re-pasting a posting land on its own row, and it is how the app tells a
    hand-added job from a crawled one that happens to share its source name.
    """
    if not body.title.strip() or not body.company.strip():
        raise HTTPException(status_code=422, detail="title and company are required")

    now = vn_now()
    # Stable id from the URL when there is one, so pasting the same posting
    # twice updates it instead of creating a duplicate.
    native, strong = _native_id(body.url)
    job = db.get(Job, make_job_id(HAND_ID_PREFIX, native)) if native else None
    if (
        job is not None
        and not strong
        and _as_listed(job.company, job.title) != _as_listed(body.company, body.title)
    ):
        # The address led to a row that is some other job: it named a page (a
        # careers index, a board's search) or a post that lists several roles,
        # rather than one posting. Writing this job over that one would hand its
        # status, its tailored CV and its application to a different job — and
        # answer 201. A second row is the cheap mistake; that is the expensive
        # one. The price: retitle a job whose address is not a LinkedIn job
        # number, paste it again, and it becomes a second row.
        native, job = "", None
    if not native:
        # Where every address that named no single posting ends up, so the same
        # question is asked here: is the row under this id the job being saved?
        native = _fallback_id(body.company, body.title, crowded=False)
        job = db.get(Job, make_job_id(HAND_ID_PREFIX, native))
        if job is not None and _as_listed(job.company, job.title) != _as_listed(
            body.company, body.title
        ):
            native = _fallback_id(body.company, body.title, crowded=True)
            job = db.get(Job, make_job_id(HAND_ID_PREFIX, native))
    job_id = make_job_id(HAND_ID_PREFIX, native)

    if job is None:
        job = Job(id=job_id, source=body.source or HAND_ID_PREFIX, crawled_at=now)
        db.add(job)
    elif body.source is not None:
        job.source = body.source

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
    # This endpoint upserts, so it can land on a row where somebody has already
    # chosen where to apply — paste the same posting again and the URL fallback
    # below would quietly undo that choice while the payload still claimed a
    # person had made it. The flag and the column have to agree, and the person
    # wins. Only an explicit `apply_target` in *this* body overrules them.
    if body.apply_target:
        job.apply_channel = body.apply_channel
        job.apply_target = body.apply_target
        _note_stated_target(job, payload, {"apply_target": body.apply_target})
    elif not target_is_stated(payload):
        job.apply_channel = body.apply_channel
        job.apply_target = body.url or None
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
    # Resolve the employer to a `companies` row, exactly as the crawler does.
    # Before the flush, so a job pasted for an employer nobody has seen yet gets
    # its company created in the same transaction rather than on some later pass.
    link_job(db, job)
    job.payload = _merged_payload(
        {
            **payload,
            "skills": body.skills,
            "description_md": body.description_md,
            # Both kept. The buckets are a reading *of* the raw text and the raw
            # text stays the evidence, so storing only the buckets would throw
            # away the thing every guardrail downstream checks against.
            **({"sections": body.sections.model_dump()} if body.sections else {}),
            # `normalize()` writes this for a crawled job and `/market` counts
            # sources from the payload, not the column. Without it every job
            # added by hand was one bar labelled "?".
            "source": job.source,
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
    if "source" in patch and not is_hand_added(job.id):
        raise HTTPException(
            status_code=422,
            detail="this job was crawled, so its source is where it was crawled from; "
            "only a job added by hand has one to choose",
        )

    payload = dict(job.payload or {})
    # Before the pops below, which mutate `patch` — it has to see the body as
    # the caller sent it. It only touches `apply_channel` when the caller did
    # not, so the setattr loop further down cannot undo it either way.
    _note_stated_target(job, payload, patch)
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
    # Re-linked after the edit for the same reason the signals are re-derived:
    # correcting a misspelled employer is one of the things this endpoint is
    # for, and leaving the old link would make the fix invisible on the only
    # page that groups by employer.
    link_job(db, job)
    job.payload = {**_merged_payload(payload, signals, body.work_mode), "source": job.source}

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
    # A job added by hand was never in any crawl pass, whatever board the user
    # filed it under: its `last_seen_at` is the moment it was pasted. Measuring
    # it against LinkedIn's passes would flag it "not seen lately — possibly
    # taken down" two alert emails later. Never looked for is not gone.
    passes = [] if is_hand_added(job.id) else crawl_passes(db, [job.source]).get(job.source, [])
    out = JobDetailOut.from_job(job, passes)
    out.copies = [RepostOut.model_validate(c) for c in _copies(db, job)]
    out.reposts = sum(1 for c in out.copies if c.id != job.latest_id)
    return out


def _copies(db: Session, job: Job) -> list[Job]:
    """The other listings of this posting: everything sharing its newest copy."""
    head = job.latest_id or job.id
    stmt = (
        select(Job)
        .where(or_(Job.id == head, Job.latest_id == head), Job.id != job.id)
        .options(defer(Job.payload))
        .order_by(Job.last_seen_at.desc(), Job.id.desc())
    )
    return list(db.scalars(stmt))


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
