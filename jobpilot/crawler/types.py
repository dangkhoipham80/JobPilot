"""Raw crawl data types — the un-normalized shapes scrapers emit.

A scraper's ``parse_search`` yields :class:`SearchHit` (enough to open a detail
page); ``parse_detail`` yields :class:`RawJob` (everything scraped from a job
page, still site-shaped). ``normalize.normalize`` turns a ``RawJob`` into the
canonical PLAN §3.1 Job schema.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

#: Width of ``jobs.id`` (and of every ``job_id`` column referencing it). Kept in
#: step with ``store.models.Job.id`` by a test, not by an import: this module is
#: the leaf every scraper imports, and it must not pull SQLAlchemy in behind it.
JOB_ID_WIDTH = 128


#: The id prefix of every job added by hand — and its ``source`` too, until the
#: user says where they found it. The prefix never follows the source: it is how
#: a hand-added row is told from a crawled one that shares its source name.
HAND_ID_PREFIX = "manual"


def is_hand_added(job_id: str) -> bool:
    return job_id.startswith(f"{HAND_ID_PREFIX}:")


def make_job_id(source: str, native_id: str) -> str:
    """``<source>:<native_id>``, bounded to ``JOB_ID_WIDTH``.

    ``native_id`` comes from the URL, and some boards put the employer's full
    legal name in the slug: an ITviec posting for "Công Ty Star Telecom (Unitel)
    - Trực Thuộc Tập Đoàn ... Viettel" produced a 134-character id. Postgres
    rejected the insert mid-flush, and because the session was then unusable,
    every site crawled after it failed too.

    An overlong id keeps its readable head and ends in a digest of the *whole*
    id, so it stays deterministic — the next crawl of the same posting lands on
    the same row instead of inserting a twin — and two long slugs sharing a
    prefix still get different ids. Ids that fit are returned untouched, so no
    existing row changes identity.
    """
    full = f"{source}:{native_id}"
    if len(full) <= JOB_ID_WIDTH:
        return full
    digest = hashlib.sha1(full.encode("utf-8")).hexdigest()[:12]
    return f"{full[: JOB_ID_WIDTH - len(digest) - 1]}-{digest}"


@dataclass
class SearchHit:
    """A single result on a search/listing page — enough to fetch the detail page."""

    native_id: str
    url: str
    title: str = ""
    company: str = ""
    location: str | None = None
    salary: str | None = None
    posted_raw: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class RawJob:
    """Everything a scraper pulled from a job detail page (pre-normalization)."""

    source: str
    native_id: str
    url: str
    title: str = ""
    company: str = ""
    location: str | None = None
    salary: str | None = None
    posted_raw: str | None = None  # e.g. "2 days ago", "08/07/2026", "hôm qua"
    skills: list[str] = field(default_factory=list)
    description_html: str = ""
    description_md: str = ""
    apply_channel: str | None = None  # email | portal | external
    apply_target: str | None = None  # hr@acme.com | https://apply-url
    raw_ref: str | None = None  # path to cached raw HTML (audit)
    extra: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Global dedup key: ``<source>:<native_id>`` (PLAN §3.1), width-bounded."""
        return make_job_id(self.source, self.native_id)
