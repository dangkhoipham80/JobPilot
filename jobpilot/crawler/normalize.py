"""RawJob → canonical Job (PLAN §3.1) + filtering/scoring helpers.

Pure functions (no DB, no network). ``normalize`` produces a
:class:`NormalizedJob` carrying both the relational columns and the full JSONB
``payload``; ``persist.persist_jobs`` writes it. Timestamps use a fixed +07:00
offset (Asia/Ho_Chi_Minh, no DST) to avoid a tzdata dependency on Windows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from jobpilot.config import Config
from jobpilot.crawler.quality import Quality, flags_for, stack_coverage
from jobpilot.crawler.text import clean_text, dedup_key, html_to_markdown, title_level
from jobpilot.crawler.types import RawJob
from jobpilot.timeutil import VN_TZ, as_aware, vn_now  # re-exported for callers/tests

__all__ = [
    "VN_TZ",
    "vn_now",
    "parse_posted_at",
    "infer_level",
    "LEVELS",
    "COLUMN_WIDTHS",
    "fit_column",
    "Enrichment",
    "enrich",
    "stack_match_score",
    "title_excluded",
    "NormalizedJob",
    "normalize",
]


# --------------------------------------------------------------------------- #
# posted_at parsing
# --------------------------------------------------------------------------- #
_REL_EN = re.compile(r"(\d+)\s*(minute|hour|day|week|month)s?\s*ago")
_REL_VI = re.compile(r"(\d+)\s*(phút|giờ|ngày|tuần|tháng)\s*trước")
_UNIT_DAYS = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30}
_UNIT_SECONDS = {"minute": 60, "hour": 3600}
_VI_UNIT = {"phút": "minute", "giờ": "hour", "ngày": "day", "tuần": "week", "tháng": "month"}
_ABS_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y")
# Unix seconds: 1e9 is 2001, 1e11 is the year 5138 — wide enough for any real
# posting, narrow enough that a stray number is not mistaken for a timestamp.
_EPOCH_RE = re.compile(r"\d{9,11}")


def _delta_from(value: int, unit: str) -> timedelta:
    if unit in _UNIT_SECONDS:
        return timedelta(seconds=value * _UNIT_SECONDS[unit])
    return timedelta(days=value * _UNIT_DAYS[unit])


def parse_posted_at(raw: str | None, now: datetime | None = None) -> datetime | None:
    """Parse a site's posted-date string into a tz-aware datetime, or ``None``.

    Handles English/Vietnamese relative ("3 days ago", "2 giờ trước", "hôm
    qua") and absolute (dd/mm/yyyy, yyyy-mm-dd, ISO) forms.
    """
    if not raw:
        return None
    now = now or vn_now()
    s = clean_text(raw).lower()

    if any(k in s for k in ("just now", "vừa", "hôm nay", "today")):
        return now
    if any(k in s for k in ("hôm qua", "yesterday")):
        return now - timedelta(days=1)

    m = _REL_EN.search(s)
    if m:
        return now - _delta_from(int(m.group(1)), m.group(2))
    m = _REL_VI.search(s)
    if m:
        return now - _delta_from(int(m.group(1)), _VI_UNIT[m.group(2)])

    # Unix seconds, as JSON job APIs publish them. Bounded to 9-11 digits on
    # purpose: an unbounded int() would read a bare year ("2026") as an epoch
    # and date the job to January 1970, which is worse than not knowing.
    if _EPOCH_RE.fullmatch(s):
        return datetime.fromtimestamp(int(s), tz=VN_TZ)

    # ISO first (may carry its own tz), then day-first formats.
    try:
        dt = datetime.fromisoformat(s.replace("z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=VN_TZ)
    except ValueError:
        pass
    # RFC-822/2822 — what every RSS feed publishes ("Wed, 22 Jul 2026 07:00:51
    # +0000"). Without this a feed source lands with posted_at=None, which is not
    # a harmless gap: the job can never be flagged fresh (<48h), it drops out of
    # the dashboard's by-day chart, and freshness is the whole point of a feed.
    try:
        return parsedate_to_datetime(clean_text(raw))
    except (TypeError, ValueError):
        pass
    for fmt in _ABS_FORMATS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=VN_TZ)
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------- #
# level inference + matching
# --------------------------------------------------------------------------- #
# Seniority words, matched as whole words and in priority order (intern and
# fresher before senior, so "Senior mentor for interns" is not an internship).
#
# Whole words, not substrings: "intern" appears inside "internal" and
# "international", which every third JD says — that quietly filed Stripe's
# "Backend Engineer, AI Security" as an *internship*, and "leadership skills"
# made mid-level roles senior. Wrong data that looks right is the worst kind:
# it flows straight into the dashboard's level chart and the level filter.
#
# And bare "intern" counts only in the *title*: it is an ordinary word in prose
# ("we confer internally", German "beraten wir uns intern") but never an
# accident in a job title. "Internship"/"thực tập" are unambiguous anywhere.
_BARE_INTERN_RE = re.compile(r"\binterns?\b", re.I)
_LEVEL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("intern", r"\b(?:internships?|thực tập)\b"),
    ("fresher", r"\bfreshers?\b"),
    ("junior", r"\bjuniors?\b"),
    ("senior", r"\b(?:senior|lead|principal|staff)\b|trưởng nhóm"),
    ("middle", r"\b(?:middle|mid-level|mid level)\b"),
)
_LEVEL_RES = tuple((level, re.compile(pat, re.I)) for level, pat in _LEVEL_PATTERNS)

#: Every value ``infer_level`` can return. Exported because a second component
#: now writes this column — ``intake`` lets a model name the level it read off a
#: posting — and a model answering "mid-senior" would create a bucket of one
#: that the Jobs filter and the Market level chart never select. Derived from the
#: patterns rather than typed out again: the two drifting apart is precisely the
#: failure this constant exists to prevent.
LEVELS: frozenset[str] = frozenset(level for level, _pattern in _LEVEL_PATTERNS)


def infer_level(title: str, description: str = "") -> str | None:
    """Best-effort seniority from title/JD (intern/fresher checked before senior)."""
    if _BARE_INTERN_RE.search(title or ""):
        return "intern"
    text = f"{title} {description}"
    for level, pattern in _LEVEL_RES:
        if pattern.search(text):
            return level
    return None


def stack_match_score(haystack: str, stacks: list[str]) -> float:
    """Fraction of configured stacks mentioned in ``haystack`` (0..1)."""
    if not stacks:
        return 0.0
    hay = haystack.lower()
    hits = sum(1 for s in stacks if s.lower() in hay)
    return round(hits / len(stacks), 3)


def title_excluded(title: str, exclude_keywords: list[str]) -> bool:
    """True if the *title* contains any exclude keyword (case-insensitive).

    Matched against the title only — matching full JD over-excludes (a Java role
    may list ".NET" as a nice-to-have). Seniority exclusions (Senior/Lead) live
    here too via ``config.crawl.exclude_keywords``.
    """
    t = (title or "").lower()
    return any(kw.lower() in t for kw in exclude_keywords)


# --------------------------------------------------------------------------- #
# normalization
# --------------------------------------------------------------------------- #
#: Width of each ``jobs`` column that holds a free-text field, so callers clamp
#: to the same numbers the model declares rather than to a copy of them.
COLUMN_WIDTHS: dict[str, int] = {
    "title": 256,
    "company": 256,
    "location": 256,
    "salary": 128,
    # Narrow, and reachable: `POST /jobs` takes `level` straight from a request
    # body. Small enough to look harmless and therefore the one most likely to
    # be left out of a clamp — which it was, until a review pointed out that
    # `{"level": "s"*200}` passes on SQLite and raises StringDataRightTruncation
    # mid-flush on Postgres.
    "level": 32,
}


def fit_column(field: str, value: str | None) -> str | None:
    """Clean ``value`` and clamp it to ``field``'s column width, preserving ``None``.

    ``None`` must stay ``None`` — for ``salary`` it is the meaningful "not
    disclosed", and returning ``""`` would read as a published empty salary.

    Public, and taking the field *name*, because the crawler is no longer the
    only writer of these columns: ``POST /jobs`` accepts values a model read off
    a pasted posting, and a model told to copy a salary label verbatim will
    happily copy a whole sentence. On Postgres an overlong value raises
    ``StringDataRightTruncation`` — a 500 with no indication of which field was
    at fault, after the user has already paid for one model call.
    """
    if value is None:
        return None
    return clean_text(value)[: COLUMN_WIDTHS[field]]


@dataclass
class NormalizedJob:
    id: str
    source: str
    url: str
    title: str
    company: str
    location: str | None
    salary: str | None
    level: str | None
    posted_at: datetime | None
    apply_channel: str | None
    apply_target: str | None
    match_score: float
    fresh: bool
    dedup_key: str
    #: Seniority as stated in the *title*, or ``None``. Travels beside
    #: ``dedup_key`` (which strips it) so ``persist`` can tell "Senior Backend
    #: Engineer" from "Intern Backend Engineer" without splitting the far more
    #: common case where one board simply omits the word. Not ``level`` above:
    #: that one also reads the JD, and a JD saying "we hire senior engineers"
    #: must not be allowed to decide that two postings are different postings.
    dedup_level: str | None
    payload: dict = field(default_factory=dict)


def normalize(raw: RawJob, cfg: Config, now: datetime | None = None) -> NormalizedJob:
    """Turn a scraped :class:`RawJob` into a persistable :class:`NormalizedJob`."""
    now = now or vn_now()
    desc_md = raw.description_md or html_to_markdown(raw.description_html)
    level = infer_level(raw.title, desc_md)
    posted_at = parse_posted_at(raw.posted_raw, now)
    fresh = bool(posted_at and (now - posted_at) <= timedelta(hours=cfg.crawl.fresh_hours))
    haystack = " ".join([raw.title, " ".join(raw.skills), desc_md])
    score = stack_match_score(haystack, cfg.crawl.stacks)
    # The same arithmetic the score comes from, reported instead of hidden: a
    # bare 0.25 is a verdict with no reasons attached.
    matched, missing = stack_coverage(haystack, cfg.crawl.stacks)
    quality = Quality(
        matched=matched,
        missing=missing,
        flags=flags_for(
            description_md=desc_md,
            posted_at=posted_at,
            needs_jd=bool(raw.extra.get("needs_jd")),
            now=now,
            stale_days=cfg.crawl.stale_days,
        ),
    )

    payload = {
        # Scraper-specific extras first, so a stray key can never shadow a
        # canonical PLAN §3.1 field. This is how flags like `needs_jd` survive.
        **raw.extra,
        "id": raw.id,
        "source": raw.source,
        "url": raw.url,
        "title": clean_text(raw.title),
        "company": clean_text(raw.company),
        "location": raw.location,
        "salary": raw.salary,
        "posted_at": posted_at.isoformat() if posted_at else None,
        "level": level,
        "skills": raw.skills,
        # Derived fields for analytics. Each sits *beside* the raw value rather
        # than replacing it: the raw string is what the board actually said, and
        # a derivation that turns out wrong should be re-runnable against it.
        **derived_facets(raw.salary, raw.skills, raw.location, desc_md),
        "description_md": desc_md,
        "apply_channel": raw.apply_channel,
        "apply_target": raw.apply_target,
        "raw_html_ref": raw.raw_ref,
        "crawled_at": now.isoformat(),
        "match_score": score,
        "is_fresh": fresh,
        "quality": quality.as_dict(),
    }
    return NormalizedJob(
        id=raw.id,
        source=raw.source,
        url=raw.url,
        # Clamped to the `jobs` column widths. A scraper that grabs too much is a
        # scraper bug, but on Postgres an overlong value raises
        # StringDataRightTruncation mid-flush and rolls back the *whole* crawl —
        # one bad field costing every job in the batch. Truncating keeps the
        # damage local and visible (payload still holds the full text), which is
        # the graceful-per-site-failure rule applied per field. SQLite ignores
        # these widths, so only a real Postgres run ever surfaces it.
        title=fit_column("title", raw.title),
        company=fit_column("company", raw.company),
        location=fit_column("location", raw.location),
        salary=fit_column("salary", raw.salary),
        level=level,
        posted_at=posted_at,
        apply_channel=raw.apply_channel,
        apply_target=raw.apply_target,
        match_score=score,
        fresh=fresh,
        dedup_key=dedup_key(raw.company, raw.title),
        dedup_level=title_level(raw.title),
        payload=payload,
    )


#: "Remote" written the ways boards write it. Deliberately anchored on word
#: boundaries: `"remote" in text` matched "remote debugging" in a JD, which is
#: the substring trap CLAUDE.md already records paying for once.
_REMOTE_RE = re.compile(r"\b(remote|work from home|wfh|anywhere)\b", re.I)

#: How a job is worked, in the three words postings actually use. ``None`` is a
#: fourth state and the most common one — most ads never say — so this is
#: deliberately not an enum with an "unknown" member: not stated is absence of
#: an answer, not a kind of answer (the ``undated`` vs ``stale`` rule again).
WORK_MODES: tuple[str, ...] = ("onsite", "hybrid", "remote")

#: Hybrid first: "hybrid (2 days onsite)" is hybrid, and a first-match scan that
#: tried onsite first would call it onsite. Vietnamese ads say "tại văn phòng"
#: for onsite and "từ xa" for remote.
#
# The remote branch reuses `_REMOTE_RE` rather than restating it. Measured on the
# live corpus: eight jobs listed "Anywhere in the World", which `_REMOTE_RE`
# knows and a hand-written twin did not — so `is_remote` said true while
# `work_mode` said nothing, on the same row, about the same question. Two fields
# derived from one label must not be able to disagree about it.
_WORK_MODE_RES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("hybrid", re.compile(r"\bhybrid\b|\bkết hợp\b", re.I)),
    ("remote", re.compile(rf"{_REMOTE_RE.pattern}|\btừ xa\b|\btại nhà\b", re.I)),
    ("onsite", re.compile(r"\bon-?site\b|\btại văn phòng\b|\btại công ty\b", re.I)),
)


def parse_work_mode(*texts: str | None) -> str | None:
    """onsite / hybrid / remote, from the first text that says so.

    Scanned over the *location label* and the posting's own words about where
    the work happens — never over a whole JD. A description that mentions
    "remote-first culture" in a perks list is not stating this job's
    arrangement, and the substring trap this repo already paid for once
    ("remote" inside "remote debugging") is the same trap one level up.
    """
    for text in texts:
        if not text:
            continue
        for mode, pattern in _WORK_MODE_RES:
            if pattern.search(text):
                return mode
    return None


def derived_facets(
    salary_raw: str | None,
    skills_raw: list[str] | None,
    location_raw: str | None,
    description_md: str = "",
) -> dict:
    """Analytics-ready fields derived from what the scraper found.

    Split out of ``normalize`` so ``cli backfill`` can re-run exactly this on
    rows crawled before these fields existed — the same shape
    ``crawler/quality.backfill`` uses, and for the same reason: a derivation
    that only runs at crawl time silently splits the database into rows that
    have it and rows that never will.
    """
    from jobpilot.crawler.salary import parse as parse_salary_range
    from jobpilot.crawler.skills import canonicalise
    from jobpilot.crawler.vietnam import canonical_city, looks_like_city

    money = parse_salary_range(salary_raw)
    location = clean_text(location_raw)
    # Only the location field decides "remote" — not the JD. A description that
    # mentions remote work in a perk list is not a remote job.
    remote = bool(location and _REMOTE_RE.search(location))
    return {
        "salary_range": money.as_dict() if money else None,
        "skills_canonical": canonicalise(skills_raw),
        "city": canonical_city(location) if location and looks_like_city(location) else None,
        "is_remote": remote,
        # Read off the location label, which is where boards put it: LinkedIn
        # writes "Ho Chi Minh City, Vietnam (Hybrid)" on every posting it
        # announces. Derived here rather than only at intake so crawled jobs
        # carry it too — and so `backfill --force` can fill it in for the ones
        # already stored. Finer than `is_remote`, which cannot tell hybrid from
        # on-site; both are kept because `is_remote` is what /market filters on.
        "work_mode": parse_work_mode(location),
    }


@dataclass(frozen=True)
class Enrichment:
    """Everything ``normalize`` derives, for a job that never went through it."""

    level: str | None
    match_score: float
    payload: dict


def enrich(
    *,
    cfg: Config,
    title: str,
    location: str | None = None,
    salary: str | None = None,
    level: str | None = None,
    skills: list[str] | None = None,
    description_md: str = "",
    posted_at: datetime | None = None,
    needs_jd: bool = False,
    now: datetime | None = None,
) -> Enrichment:
    """The derivations ``normalize`` runs, for a job assembled by hand.

    A job added through ``POST /jobs`` never meets a scraper, so until this
    existed it arrived with ``match_score`` 0.0, no quality flags and none of the
    analytics facets — it was on the Jobs page and invisible to the Market page,
    scored below every crawled job in a list sorted by relevance, and carried no
    explanation of why. Not a wrong answer so much as a job the rest of the app
    could not see properly, which is the harder kind of bug to notice.

    Takes plain values rather than a ``RawJob`` because the caller has an API
    body, and returns them rather than mutating a row because the same
    derivations have to be available to a caller who has not decided to save
    anything yet. ``normalize`` keeps its own copy of these calls: it holds the
    scraper's extra context (``posted_raw``, HTML, ``raw_ref``) and folding both
    into one function would mean inventing a shared input type that neither
    caller naturally has.
    """
    now = now or vn_now()
    # `normalize` gets `posted_at` fresh out of its own parser and always aware.
    # This one gets it off a row the caller just loaded, and SQLite hands
    # timestamps back naive where Postgres hands them back aware — so the
    # comparison inside `flags_for` raises on one backend and not the other.
    # Normalising here rather than at the call sites keeps that from being a
    # thing each new caller has to rediscover.
    posted_at = as_aware(posted_at)
    # Clamped here rather than at each caller: this is the one place `Job.level`
    # is decided for both the crawler and the API, and a caller-side clamp is a
    # clamp the next caller forgets. `infer_level` only ever returns short known
    # words, so this is really about the value a request body supplied.
    level = fit_column("level", level) or infer_level(title, description_md)
    haystack = " ".join([title, " ".join(skills or []), description_md])
    score = stack_match_score(haystack, cfg.crawl.stacks)
    matched, missing = stack_coverage(haystack, cfg.crawl.stacks)
    quality = Quality(
        matched=matched,
        missing=missing,
        flags=flags_for(
            description_md=description_md,
            posted_at=posted_at,
            needs_jd=needs_jd,
            now=now,
            stale_days=cfg.crawl.stale_days,
        ),
    )
    fresh = bool(posted_at and (now - posted_at) <= timedelta(hours=cfg.crawl.fresh_hours))
    return Enrichment(
        level=level,
        match_score=score,
        payload={
            **derived_facets(salary, skills, location, description_md),
            "match_score": score,
            "quality": quality.as_dict(),
            "is_fresh": fresh,
        },
    )


def backfill_facets(session, *, force: bool = False) -> int:
    """Add the derived analytics fields to jobs crawled before they existed.

    Same contract as ``crawler.quality.backfill``: idempotent, returns rows
    touched. Skips rows that already carry the fields unless ``force`` — which
    exists because a *parser* fix (a salary shape it used to miss) needs to
    re-run over rows that already have a ``None`` answer on file.
    """
    from sqlalchemy import select

    from jobpilot.store.models import Job

    touched = 0
    for job in session.scalars(select(Job)):
        payload = dict(job.payload or {})
        if not force and "skills_canonical" in payload:
            continue
        payload.update(
            derived_facets(
                # From the **columns**, with payload only as a fallback. Those
                # two payload keys are written by `normalize()` and by nothing
                # else — a job added through `POST /jobs` never had them — so
                # reading payload first meant this function handed
                # `derived_facets(None, ..., None)` every hand-added job and
                # nulled its city, salary_range, is_remote and work_mode. Not a
                # crash: a silent wipe, performed by the very command the docs
                # say you *must* run after a parser fix. The columns are the one
                # source both paths write.
                job.salary or payload.get("salary"),
                payload.get("skills"),
                job.location or payload.get("location"),
                payload.get("description_md", ""),
            )
        )
        job.payload = payload
        touched += 1
    session.commit()
    return touched
