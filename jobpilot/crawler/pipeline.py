"""Crawl orchestration: run scrapers → filter → normalize → persist → record Run.

Each site is isolated: a scraper that throws (Cloudflare, DOM change, robots)
is logged, marked failed in its :class:`SiteReport`, and the crawl continues
(PLAN §5.1 "graceful per-site fail"). One ``runs`` row captures the whole batch
for the dashboard's Runs page.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from jobpilot.config import Config
from jobpilot.crawler.base import BaseScraper
from jobpilot.crawler.normalize import normalize, title_excluded, vn_now
from jobpilot.crawler.persist import CrawlStats, persist_jobs
from jobpilot.store.models import Run

log = logging.getLogger(__name__)


@dataclass
class SiteReport:
    source: str
    ok: bool
    stats: CrawlStats
    error: str | None = None


@dataclass
class RunReport:
    run_id: int | None
    sites: list[SiteReport] = field(default_factory=list)
    #: The keywords this run searched for, in the order they ran.
    queries: list[str] = field(default_factory=list)
    #: keyword -> totals across every site, so a run can say which search
    #: actually found something.
    by_query: dict[str, CrawlStats] = field(default_factory=dict)

    @property
    def totals(self) -> CrawlStats:
        total = CrawlStats()
        for s in self.sites:
            total.merge(s.stats)
        return total


#: Keywords one run may carry. Each one is a full pass over every selected
#: site, rate limit included, so this bounds a run to minutes rather than an
#: afternoon — and catches a paste of a whole JD into the search box.
MAX_QUERIES = 8

_QUERY_SEP = re.compile(r"[,;\n]")


def split_queries(text: str | None) -> list[str]:
    """``"java, spring boot; backend"`` -> ``["java", "spring boot", "backend"]``.

    Commas (and semicolons, newlines) separate *searches*; spaces stay inside
    one, because a board treats "spring boot" as one phrase and it should be.
    Duplicates are dropped case-insensitively, first spelling wins.
    """
    seen: set[str] = set()
    out: list[str] = []
    for part in _QUERY_SEP.split(text or ""):
        q = " ".join(part.split())
        if q and q.casefold() not in seen:
            seen.add(q.casefold())
            out.append(q)
    return out


def default_queries(cfg: Config) -> list[str]:
    """What a crawl searches for when nobody typed anything — the scheduled run.

    ``crawl.queries`` when set (one search each). Otherwise the old single
    query built from the first stacks, kept so a config written before the list
    existed crawls exactly as it did.
    """
    if cfg.crawl.queries:
        return split_queries(", ".join(cfg.crawl.queries))
    stacks = cfg.crawl.stacks[:3]
    return [" ".join(stacks) if stacks else "backend developer"]


def default_query(cfg: Config) -> str:
    """:func:`default_queries` as the one string a search box shows."""
    return ", ".join(default_queries(cfg))


def _crawl_site(
    scraper: BaseScraper,
    cfg: Config,
    session: Session,
    query: str,
    now: datetime,
    dedup_days: int,
    run_id: int | None = None,
    limit_override: int | None = None,
) -> SiteReport:
    limit = limit_override or cfg.crawl.jobs_per_site
    raws = scraper.crawl(query, limit=limit)

    kept = []
    filtered = 0
    for raw in raws:
        nj = normalize(raw, cfg, now)
        excluded = title_excluded(raw.title, cfg.crawl.exclude_keywords)
        no_stack = scraper.stack_gated and bool(cfg.crawl.stacks) and nj.match_score <= 0.0
        if excluded or no_stack:
            filtered += 1
            continue
        kept.append(nj)

    stats = persist_jobs(session, kept, dedup_days=dedup_days, now=now, run_id=run_id)
    # Hits the scraper left out by title before spending the limit on them
    # (`BaseScraper.search`). Counted in both, so the two numbers keep the
    # meaning they had when this loop did all the filtering: `fetched` is every
    # posting the crawl looked at, `filtered` is every one of those a rule
    # dropped. Leaving them out would show the same board as "10 found, 0
    # filtered" the day after it showed "10 found, 6 filtered".
    early = scraper.titles_dropped
    stats.fetched = len(raws) + early
    stats.filtered = filtered + early
    log.info(
        "[%s] fetched=%d inserted=%d updated=%d dup=%d kept-for-jd=%d filtered=%d fresh=%d",
        scraper.source,
        stats.fetched,
        stats.inserted,
        stats.updated,
        stats.duplicates,
        stats.superseded,
        stats.filtered,
        stats.fresh,
    )
    return SiteReport(source=scraper.source, ok=True, stats=stats)


def run_crawl(
    scrapers: list[BaseScraper],
    cfg: Config,
    session: Session,
    *,
    query: str | None = None,
    now: datetime | None = None,
    dedup_days: int | None = None,
    record_run: bool = True,
    limit: int | None = None,
    on_progress: Callable[[str], None] | None = None,
    sources: list[str] | None = None,
) -> RunReport:
    """Crawl every scraper into ``session`` and return a :class:`RunReport`.

    Commits once at the end. Individual site failures never abort the batch.

    ``query`` may carry several comma-separated keywords (:func:`split_queries`);
    each is its own search on every site, ``limit`` jobs deep *per keyword*. A
    site runs all of them before it is closed, so it keeps one browser, and its
    request gate (``BaseScraper._fetch``) spaces every request of the run —
    including the first one of the next keyword — and serves pages it already
    fetched this run from memory. A source that ignores the query
    (``query_aware = False``) runs once and is not credited to any keyword.

    ``sources`` is recorded, not applied — the caller already chose the
    scrapers. It is what lets the Runs page offer "crawl this again" with the
    same scope (``Run.stats["request"]``).

    ``limit`` overrides ``cfg.crawl.jobs_per_site`` for this run only — useful
    for a one-off deep sweep without editing the config.

    ``dedup_days`` likewise defaults to ``cfg.crawl.dedup_days``. It used to
    default to a literal 14 that no caller passed and no config file mentioned,
    so the cross-source dedup window was the one crawl rule that could not be
    changed from the Settings page — or found by looking for it.
    """
    now = now or vn_now()
    queries = split_queries(query) if query else default_queries(cfg)
    if dedup_days is None:
        dedup_days = cfg.crawl.dedup_days

    run: Run | None = None
    if record_run:
        run = Run(kind="crawl", stats={})
        session.add(run)
        session.flush()  # assign run.id

    report = RunReport(run_id=run.id if run else None, queries=queries)
    report.by_query = {q: CrawlStats() for q in queries}
    total = len(scrapers)
    multi = len(queries) > 1
    for index, scraper in enumerate(scrapers, start=1):
        merged = CrawlStats()
        errors: list[str] = []
        searches = queries if scraper.query_aware else queries[:1]
        credit = scraper.query_aware  # by_query only counts searches that used the keyword
        try:
            for qi, q in enumerate(searches, start=1):
                # Announced *before* the work, not after. A site behind a rate
                # limiter and a headless browser can take a minute on its own,
                # and the point of a progress line is to say what is happening
                # *during* that minute.
                where = f"[{index}/{total}] {scraper.source}" + (
                    f" · {q!r} ({qi}/{len(searches)})" if multi and credit else ""
                )
                if on_progress:
                    on_progress(f"{where} crawling…")
                try:
                    # A savepoint per site and keyword, on top of persist's
                    # savepoint per job. Those catch a bad row; this catches
                    # anything else that breaks the session mid-site (the dedup
                    # preload, a company lookup) and keeps it from taking the
                    # remaining searches — and the Run row — down too.
                    with session.begin_nested():
                        site = _crawl_site(
                            scraper, cfg, session, q, now, dedup_days, report.run_id, limit
                        )
                except Exception as exc:
                    log.exception("[%s] crawl failed for %r", scraper.source, q)
                    errors.append(f"{q}: {exc}" if multi and credit else str(exc))
                    # Counted, not dropped: a search that failed must not read
                    # as a search that found nothing.
                    merged.merge(CrawlStats(errors=1))
                    if credit:
                        report.by_query[q].merge(CrawlStats(errors=1))
                    if on_progress:
                        on_progress(f"{where}: failed")
                    continue
                merged.merge(site.stats)
                if credit:
                    report.by_query[q].merge(site.stats)
                if on_progress:
                    st = site.stats
                    on_progress(f"{where}: {st.fetched} found, {st.inserted} new")
        finally:
            scraper.close()
        # A site counts as failed only when every search on it failed: with one
        # keyword that is exactly the old rule, and with several, one blocked
        # search must not hide the jobs the others found. A partial failure is
        # still visible — `errors` > 0 and `error` set on a site that is `ok`,
        # which the CLI prints as PART and the Runs page shows under the row.
        failed = len(errors) == len(searches)
        report.sites.append(
            SiteReport(scraper.source, ok=not failed, stats=merged, error="; ".join(errors) or None)
        )

    if run is not None:
        # A *fresh* timestamp. This reused `now`, captured at the top of the
        # function, so every run recorded a finish before its own start and a
        # duration of roughly zero — the Runs page could never say how long a
        # crawl took, which is the one thing you want while waiting for one.
        run.finished_at = vn_now()
        run.stats = {
            # Joined for anything that reads the single-string field (the Runs
            # summary line, older dashboards); `queries` is the real list.
            "query": ", ".join(queries),
            "queries": queries,
            # Exactly what was asked, so the run can be repeated as it was.
            "request": {"queries": queries, "sources": sources, "limit": limit},
            "by_query": {q: st.as_dict() for q, st in report.by_query.items()},
            "totals": report.totals.as_dict(),
            "sites": {
                s.source: {"ok": s.ok, "error": s.error, **s.stats.as_dict()} for s in report.sites
            },
        }
    session.commit()
    return report
