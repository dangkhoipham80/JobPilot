"""Phase 3: end-to-end crawl→normalize→filter→dedup→persist→Run on SQLite.

Uses the offline ``FixtureScraper`` so the whole pipeline runs without network,
Playwright, or Postgres.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from jobpilot.config import ApplyCfg, Config, CrawlCfg, CvCfg
from jobpilot.crawler.base import BaseScraper
from jobpilot.crawler.fixture import SEARCH_URL, FixtureScraper
from jobpilot.crawler.normalize import VN_TZ
from jobpilot.crawler.pipeline import run_crawl
from jobpilot.crawler.ratelimit import RateLimiter
from jobpilot.store.models import Job, JobStatus, Run

NOW = datetime(2026, 7, 10, 12, 0, tzinfo=VN_TZ)


def _cfg() -> Config:
    return Config(
        crawl=CrawlCfg(
            jobs_per_site=10,
            fresh_hours=48,
            stacks=["Java", "Spring Boot"],
            exclude_keywords=["Senior", "Lead"],
        ),
        apply=ApplyCfg(),
        cv=CvCfg(),
    )


def _detail(title, company, *, skills="Java", posted="2 days ago", jd="Build APIs") -> str:
    tags = "".join(f'<span class="skill">{s}</span>' for s in skills.split(","))
    return (
        f"<h1>{title}</h1><div class='company'>{company}</div>"
        f"<div class='location'>HCM</div><div class='posted'>{posted}</div>"
        f"{tags}<div class='jd'><p>{jd}</p></div>"
    )


def _pages() -> dict[str, str]:
    search = (
        '<a class="job" href="j/1" data-id="1">Backend Java</a>'
        '<a class="job" href="j/2" data-id="2">Senior Java</a>'  # excluded by title
        '<a class="job" href="j/3" data-id="3">Golang Dev</a>'  # no stack match → filtered
    )
    return {
        SEARCH_URL: search,
        "j/1": _detail("Backend Engineer Java", "ACME", skills="Java,Spring Boot"),
        "j/2": _detail("Senior Java Engineer", "BigCo", skills="Java"),
        "j/3": _detail("Golang Developer", "GoCorp", skills="Go"),
    }


def _fixture(pages, *, source="fixture") -> FixtureScraper:
    # Disable rate-limit sleeping so tests are instant.
    return FixtureScraper(pages, source=source, rate_limiter=RateLimiter(0, 0))


def test_pipeline_persists_filtered_normalized_jobs(session_factory):
    with session_factory() as db:
        report = run_crawl([_fixture(_pages())], _cfg(), db, now=NOW)

    assert report.totals.fetched == 3
    assert report.totals.inserted == 1  # only the Java backend survives filters
    assert report.totals.filtered == 2  # Senior (excluded) + Golang (no stack)

    with session_factory() as db:
        job = db.get(Job, "fixture:1")
        assert job is not None
        assert job.status is JobStatus.DISCOVERED
        assert job.company == "ACME"
        assert job.level is None
        assert job.match_score == 1.0  # both stacks present
        assert job.payload["is_fresh"] is True  # posted 2 days ago, fresh_hours=48 → 48h boundary
        assert db.get(Job, "fixture:2") is None
        assert db.get(Job, "fixture:3") is None


def test_a_source_exempt_from_the_stack_gate_keeps_a_job_that_names_no_stack(session_factory):
    """A company board the user picked is not a searched board.

    The stack gate is what clears accountants out of a general board's results.
    On a hand-picked board it removed the plain "Software Engineer" role whose
    JD names no stack. Exempt sources keep such a job at match 0 — shown and
    visibly unranked — and still lose the titles the user excluded.
    """

    class _HandPicked(FixtureScraper):
        stack_gated = False

    scraper = _HandPicked(_pages(), source="picked", rate_limiter=RateLimiter(0, 0))
    with session_factory() as db:
        report = run_crawl([scraper], _cfg(), db, now=NOW)

    assert report.totals.inserted == 2
    assert report.totals.filtered == 1  # only the excluded title
    with session_factory() as db:
        golang = db.get(Job, "picked:3")
        assert golang is not None and golang.match_score == 0.0
        assert db.get(Job, "picked:2") is None, "Senior is excluded by title, gate or no gate"
        assert db.get(Job, "picked:1").match_score == 1.0


def test_run_row_recorded_with_stats(session_factory):
    with session_factory() as db:
        report = run_crawl([_fixture(_pages())], _cfg(), db, now=NOW)
        run = db.get(Run, report.run_id)
        assert run is not None
        assert run.kind == "crawl"
        assert run.finished_at is not None
        assert run.stats["totals"]["inserted"] == 1


def test_recrawl_updates_not_duplicates(session_factory):
    with session_factory() as db:
        run_crawl([_fixture(_pages())], _cfg(), db, now=NOW)
    with session_factory() as db:
        report = run_crawl([_fixture(_pages())], _cfg(), db, now=NOW)
        assert report.totals.inserted == 0
        assert report.totals.updated == 1
        assert db.query(Job).count() == 1  # no dupes


def test_cross_source_dedup_by_company_title(session_factory):
    # Same role on two "sources" → inserted once, second is a duplicate.
    pages_a = {
        SEARCH_URL: '<a class="job" href="a/1" data-id="1">x</a>',
        "a/1": _detail("Backend Engineer Java", "ACME", skills="Java,Spring Boot"),
    }
    pages_b = {
        SEARCH_URL: '<a class="job" href="b/1" data-id="9">x</a>',
        "b/1": _detail("Junior Backend Engineer Java", "ACME", skills="Java,Spring Boot"),
    }
    scrapers = [_fixture(pages_a, source="srcA"), _fixture(pages_b, source="srcB")]
    with session_factory() as db:
        report = run_crawl(scrapers, _cfg(), db, now=NOW)
        assert report.totals.inserted == 1
        assert report.totals.duplicates == 1


def test_site_failure_is_isolated(session_factory):
    class Boom(BaseScraper):
        source = "boom"

        def search_url(self, query, page=1):
            return "x"

        def parse_search(self, html):
            raise RuntimeError("cloudflare")

        def parse_detail(self, html, hit):  # pragma: no cover
            raise AssertionError

    boom = Boom(fetcher=lambda url: "<html></html>", rate_limiter=RateLimiter(0, 0))
    good = _fixture(_pages(), source="good")
    with session_factory() as db:
        report = run_crawl([boom, good], _cfg(), db, now=NOW)

    by_source = {s.source: s for s in report.sites}
    assert by_source["boom"].ok is False
    assert "cloudflare" in by_source["boom"].error
    assert by_source["good"].ok is True  # good site still ran
    assert report.totals.inserted == 1


def test_detail_fetch_error_skips_one_hit(session_factory):
    pages = _pages()
    del pages["j/1"]  # first detail page missing → KeyError → hit skipped
    with session_factory() as db:
        report = run_crawl([_fixture(pages)], _cfg(), db, now=NOW)
    assert report.totals.fetched == 2  # 3 hits, 1 detail fetch failed
    assert report.totals.inserted == 0  # remaining two are filtered out


@pytest.mark.parametrize("limit,expected", [(1, 1), (2, 2), (10, 3)])
def test_jobs_per_site_limit_respected(session_factory, limit, expected):
    cfg = _cfg()
    cfg.crawl.jobs_per_site = limit
    cfg.crawl.stacks = []  # disable stack filter so counts reflect the limit
    cfg.crawl.exclude_keywords = []
    with session_factory() as db:
        report = run_crawl([_fixture(_pages())], cfg, db, now=NOW)
    assert report.totals.fetched == expected


def test_zero_hits_is_warned_about_not_reported_as_a_quiet_success(caplog):
    """A parser whose selectors stopped matching returns [] and the crawl then
    "succeeds" with nothing to show — indistinguishable from a query that simply
    had no results. PLAN §10 wants that visible ("cảnh báo khi 0 job")."""
    scraper = _fixture({SEARCH_URL: "<html>redesigned, no job links</html>"})
    with caplog.at_level("WARNING"):
        assert scraper.crawl("java", limit=10) == []
    assert any("0 hits" in r.getMessage() for r in caplog.records)


def test_fewer_hits_than_requested_is_warned_about(caplog):
    """VietnamWorks lazy-loads: one fetch renders ~9-20 cards, so a limit above
    that is silently unsatisfiable from a single page."""
    with caplog.at_level("WARNING"):
        _fixture(_pages()).crawl("java", limit=10)
    assert any("wanted 10" in r.getMessage() for r in caplog.records)


def test_a_full_page_does_not_warn(caplog):
    with caplog.at_level("WARNING"):
        _fixture(_pages()).crawl("java", limit=3)
    assert not [r for r in caplog.records if "wanted" in (r.getMessage())]


def _two_java_jobs(id1: str = "1", id2: str = "2") -> dict[str, str]:
    return {
        SEARCH_URL: (
            f'<a class="job" href="j/1" data-id="{id1}">Backend Java</a>'
            f'<a class="job" href="j/2" data-id="{id2}">Java API</a>'
        ),
        "j/1": _detail("Backend Engineer Java", "ACME", skills="Java,Spring Boot"),
        "j/2": _detail("Java API Engineer", "Initech", skills="Java,Spring Boot"),
    }


def test_overlong_native_id_is_bounded_and_stays_the_same_row(session_factory):
    # The real case: an ITviec slug carrying an employer's full legal name gave a
    # 134-char id against VARCHAR(128). SQLite would store it; Postgres refused.
    long_id = "backend-developer-java-spring-boot-cong-ty-" + "truc-thuoc-tap-doan-" * 6 + "2237"
    with session_factory() as db:
        first = run_crawl([_fixture(_two_java_jobs(long_id), source="itviec")], _cfg(), db, now=NOW)
    with session_factory() as db:
        again = run_crawl([_fixture(_two_java_jobs(long_id), source="itviec")], _cfg(), db, now=NOW)
        ids = [j.id for j in db.query(Job).filter(Job.source == "itviec")]

    assert first.totals.inserted == 2
    # Deterministic: the re-crawl refreshes the bounded row rather than adding a twin.
    assert (again.totals.inserted, again.totals.updated) == (0, 2)
    assert len(ids) == 2
    assert all(len(i) <= 128 for i in ids)
    assert any(i.startswith("itviec:backend-developer-java") for i in ids if len(i) == 128)


def test_a_row_the_database_refuses_costs_only_that_row(session_factory, monkeypatch):
    # A real constraint failure at flush time, not a raised exception: on
    # Postgres this was StringDataRightTruncation, and the session it poisoned
    # failed every site crawled after it. NOT NULL on `source` is a constraint
    # SQLite does enforce, so it stands in here.
    from jobpilot.crawler import persist

    real_new_job = persist._new_job

    def refuse_one(nj, now, run_id=None):
        job = real_new_job(nj, now, run_id=run_id)
        if nj.id == "bad:1":
            job.source = None
        return job

    monkeypatch.setattr(persist, "_new_job", refuse_one)
    bad = _fixture(_two_java_jobs(), source="bad")
    good = _fixture(_pages(), source="good")
    with session_factory() as db:
        report = run_crawl([bad, good], _cfg(), db, now=NOW, dedup_days=0)

    by_source = {s.source: s for s in report.sites}
    assert by_source["bad"].ok is True
    # `rejected`, not `errors`: the site ran, it lost one row. `errors` counts
    # failed sites, and folding them together hid a site losing every row.
    assert (by_source["bad"].stats.inserted, by_source["bad"].stats.rejected) == (1, 1)
    assert by_source["bad"].stats.errors == 0
    assert by_source["good"].ok is True
    assert by_source["good"].stats.inserted == 1

    with session_factory() as db:
        assert db.get(Job, "bad:1") is None
        assert db.get(Job, "bad:2") is not None
        assert db.get(Job, "good:1") is not None
        run = db.query(Run).one()
        assert run.stats["totals"]["rejected"] == 1
        assert run.stats["sites"]["bad"]["rejected"] == 1


def test_job_id_width_matches_every_column_that_holds_a_job_id():
    from jobpilot.crawler.types import JOB_ID_WIDTH, make_job_id
    from jobpilot.store.models import Base

    widths = {
        f"{t.name}.{c.name}": c.type.length
        for t in Base.metadata.tables.values()
        for c in t.columns
        if (t.name == "jobs" and c.name == "id")
        or any(fk.column.table.name == "jobs" for fk in c.foreign_keys)
    }
    assert len(widths) >= 4
    assert set(widths.values()) == {JOB_ID_WIDTH}, widths

    assert make_job_id("topcv", "123") == "topcv:123"  # ids that fit never change
    a = make_job_id("itviec", "x" * 200 + "a")
    b = make_job_id("itviec", "x" * 200 + "b")
    assert len(a) == len(b) == JOB_ID_WIDTH
    assert a != b  # same readable head, told apart by the digest


def test_a_refused_row_does_not_shadow_or_annotate_the_job_it_matched(session_factory, monkeypatch):
    """Index and annotate only after the savepoint commits.

    The refused job has a full JD and matches an incumbent with none, so it
    would supersede it. If it reached the dedup index before its savepoint
    committed, the next copy *in the same batch* (the index is per site) would
    be filed under a row that does not exist, and the incumbent's own record
    would never show it.
    """
    from jobpilot.crawler import persist

    real_new_job = persist._new_job

    def refuse(nj, now, run_id=None):
        job = real_new_job(nj, now, run_id=run_id)
        if nj.id == "mixed:1":
            job.source = None
        return job

    title, company = "Backend Engineer Java", "ACME"
    thin = _fixture(
        {
            SEARCH_URL: '<a class="job" href="j/1" data-id="1">x</a>',
            "j/1": _detail(title, company, skills="Java,Spring Boot", jd="Short."),
        },
        source="thin",
    )
    mixed = _fixture(
        {
            SEARCH_URL: (
                '<a class="job" href="j/1" data-id="1">x</a>'
                '<a class="job" href="j/2" data-id="2">x</a>'
            ),
            "j/1": _detail(title, company, skills="Java,Spring Boot", jd="Build APIs. " * 60),
            "j/2": _detail(title, company, skills="Java,Spring Boot", jd="Short too."),
        },
        source="mixed",
    )
    monkeypatch.setattr(persist, "_new_job", refuse)
    with session_factory() as db:
        report = run_crawl([thin, mixed], _cfg(), db, now=NOW, dedup_days=14)

    by_source = {s.source: s.stats for s in report.sites}
    assert by_source["thin"].inserted == 1
    assert by_source["mixed"].rejected == 1
    assert by_source["mixed"].duplicates == 1

    with session_factory() as db:
        assert db.get(Job, "mixed:1") is None
        trace = db.get(Job, "thin:1").payload.get("dedup") or {}
        assert "superseded_by" not in trace  # the rolled-back annotation is gone
        assert [e["id"] for e in trace.get("suppressed", [])] == ["mixed:2"]


# --------------------------------------------------------------------------- #
# Several keywords in one run
# --------------------------------------------------------------------------- #


def test_keywords_split_on_commas_not_spaces():
    from jobpilot.crawler.pipeline import split_queries

    # "spring boot" is one phrase to a board, and must stay one search.
    assert split_queries(" java , Spring  Boot; JAVA\nbackend,, ") == [
        "java",
        "Spring Boot",
        "backend",
    ]
    assert split_queries("") == [] == split_queries(None)


def test_the_scheduled_crawl_searches_each_configured_keyword():
    from jobpilot.crawler.pipeline import default_queries

    cfg = _cfg()
    # No list configured: exactly the old single query, so an existing config
    # crawls as it always did.
    assert default_queries(cfg) == ["Java Spring Boot"]
    cfg.crawl.queries = ["java", "spring boot", "Java"]
    assert default_queries(cfg) == ["java", "spring boot"]


class _Recording(FixtureScraper):
    """Remembers what it was asked to search for, and how often it was closed."""

    def __init__(self, *a, fail_on=(), **k):
        super().__init__(*a, **k)
        self.searched: list[str] = []
        self.closed = 0
        self.fail_on = set(fail_on)

    def crawl(self, query="", limit=None):
        self.searched.append(query)
        if query in self.fail_on:
            raise RuntimeError("blocked — anti-bot")
        return super().crawl(query, limit=limit)

    def close(self):
        self.closed += 1
        super().close()


def test_each_keyword_is_its_own_search_on_every_site(session_factory):
    a = _Recording(_pages(), source="a", rate_limiter=RateLimiter(0, 0))
    b = _Recording(_pages(), source="b", rate_limiter=RateLimiter(0, 0))
    with session_factory() as db:
        report = run_crawl(
            [a, b], _cfg(), db, query="java, spring boot", now=NOW, dedup_days=0, sources=["a", "b"]
        )

    assert a.searched == b.searched == ["java", "spring boot"]
    # One browser per site for the whole run, not one per keyword.
    assert a.closed == b.closed == 1
    assert report.queries == ["java", "spring boot"]
    # The second search finds the same postings: refreshed, never duplicated.
    assert report.by_query["java"].inserted == 2
    assert report.by_query["spring boot"].inserted == 0
    assert report.by_query["spring boot"].updated == 2

    with session_factory() as db:
        assert db.query(Job).count() == 2
        stats = db.query(Run).one().stats
    assert stats["queries"] == ["java", "spring boot"]
    assert stats["query"] == "java, spring boot"
    assert stats["request"] == {
        "queries": ["java", "spring boot"],
        "sources": ["a", "b"],
        "limit": None,
        "places": [],
        "work_modes": [],
    }
    assert stats["by_query"]["java"]["inserted"] == 2


def test_one_blocked_keyword_does_not_hide_what_the_others_found(session_factory):
    partly = _Recording(_pages(), source="partly", fail_on={"java"}, rate_limiter=RateLimiter(0, 0))
    wholly = _Recording(
        _pages(), source="wholly", fail_on={"java", "golang"}, rate_limiter=RateLimiter(0, 0)
    )
    with session_factory() as db:
        report = run_crawl(
            [partly, wholly], _cfg(), db, query="java, golang", now=NOW, dedup_days=0
        )

    by_source = {s.source: s for s in report.sites}
    assert by_source["partly"].ok is True
    assert by_source["partly"].stats.inserted == 1
    assert "java: blocked" in by_source["partly"].error
    # Every search failed: that site did fail, exactly as with one keyword.
    assert by_source["wholly"].ok is False
    assert report.by_query["java"].errors == 2


class _Counting:
    """A fetcher that serves fixture pages and counts real requests, plus a
    sleep that records every rate-limit wait — in one ordered event log."""

    def __init__(self, pages):
        self.pages = pages
        self.events: list[str] = []

    def __call__(self, url):
        self.events.append(f"GET {url}")
        return self.pages.get(url, "")

    def sleep(self, seconds):
        self.events.append("SLEEP")


def test_every_request_after_the_first_waits_including_the_next_keywords_first(session_factory):
    """`RateLimiter` holds no state. The old waits sat before listing page 2+
    and detail pages — complete for one search per run, a gap for several:
    page 1 of the next keyword went out straight after the previous request."""
    pages = {
        "search?q=java": '<a class="job" href="j/1" data-id="1">x</a>',
        "search?q=react": '<a class="job" href="j/2" data-id="2">x</a>',
        "j/1": _detail("Backend Engineer Java", "ACME", skills="Java,Spring Boot"),
        "j/2": _detail("Java React Engineer", "Initech", skills="Java,Spring Boot"),
    }
    net = _Counting(pages)

    class PerQuery(FixtureScraper):
        def search_url(self, query, page=1):
            return f"search?q={query}" if page == 1 else ""

    scraper = PerQuery(
        {}, source="perq", fetcher=net, rate_limiter=RateLimiter(1, 1, sleep=net.sleep)
    )
    with session_factory() as db:
        run_crawl([scraper], _cfg(), db, query="java, react", now=NOW, dedup_days=0)

    gets = [e for e in net.events if e.startswith("GET")]
    assert gets == ["GET search?q=java", "GET j/1", "GET search?q=react", "GET j/2"]
    # A wait before every request but the first — the keyword seam included.
    assert net.events == [
        "GET search?q=java",
        "SLEEP",
        "GET j/1",
        "SLEEP",
        "GET search?q=react",
        "SLEEP",
        "GET j/2",
    ]


def test_a_listing_that_ignores_the_query_is_fetched_once_per_run(session_factory):
    """Feeds and ATS boards serve the same listing whatever the keyword and
    filter locally; several keywords must not multiply requests to them, and a
    detail page two keywords both found is not fetched twice."""
    one = _Counting(_two_java_jobs())
    many = _Counting(_two_java_jobs())
    for net, query in ((one, "java"), (many, "java, spring, react, backend")):
        s = FixtureScraper({}, source="feedish", fetcher=net, rate_limiter=RateLimiter(0, 0))
        with session_factory() as db:
            run_crawl([s], _cfg(), db, query=query, now=NOW, dedup_days=0)
    assert [e for e in many.events if e.startswith("GET")] == [
        e for e in one.events if e.startswith("GET")
    ]


def test_a_source_that_ignores_the_query_runs_once_and_is_credited_to_no_keyword(session_factory):
    alerts = _Recording(_pages(), source="alerts", rate_limiter=RateLimiter(0, 0))
    alerts.query_aware = False
    with session_factory() as db:
        report = run_crawl([alerts], _cfg(), db, query="java, react", now=NOW, dedup_days=0)
    assert alerts.searched == ["java"]
    assert report.sites[0].stats.inserted == 1
    # Not dumped on the first keyword, where it would look like java found it.
    assert report.by_query["java"].inserted == report.by_query["react"].inserted == 0


def test_a_partly_failed_site_still_counts_its_failure(session_factory):
    partly = _Recording(_pages(), source="partly", fail_on={"java"}, rate_limiter=RateLimiter(0, 0))
    with session_factory() as db:
        report = run_crawl([partly], _cfg(), db, query="java, golang", now=NOW, dedup_days=0)
    site = report.sites[0]
    assert site.ok is True and site.stats.errors == 1
    assert report.totals.errors == 1
    with session_factory() as db:
        assert db.query(Run).one().stats["sites"]["partly"]["errors"] == 1


def test_scheduled_keywords_are_bounded_when_saved():
    from jobpilot.config import CrawlCfg

    with pytest.raises(ValueError, match="at most 8"):
        CrawlCfg(queries=[f"k{i}" for i in range(9)])
    assert CrawlCfg(queries=["java", "Java", "react"]).queries  # duplicates do not count twice


def test_the_page_memo_is_bounded(monkeypatch):
    from jobpilot.crawler import base

    monkeypatch.setattr(base, "MEMO_BUDGET_CHARS", 10)
    net = _Counting({"a": "x" * 8, "b": "y" * 8})
    s = FixtureScraper({}, source="m", fetcher=net, rate_limiter=RateLimiter(0, 0))
    for url in ("a", "b", "a", "b"):
        s._fetch(url)
    # "a" fits and is served from memory; "b" would overflow, so it goes back
    # to the network every time — politely, but uncached.
    assert [e for e in net.events if e.startswith("GET")] == ["GET a", "GET b", "GET b"]


def test_a_title_dropped_before_the_fetch_is_still_counted_as_seen_and_filtered(session_factory):
    """The scraper now leaves an excluded title out before its detail page is
    requested. ``fetched`` and ``filtered`` must say what they said when the
    pipeline did that after the fetch: the same board, the same three postings
    looked at, the same two dropped — not "2 found, 1 filtered" from one day to
    the next. What changes is the request that is no longer made."""
    pages = _pages()
    asked: list[str] = []

    def fetch(url: str) -> str:
        asked.append(url)
        return pages[url]

    scraper = FixtureScraper(
        pages, fetcher=fetch, rate_limiter=RateLimiter(0, 0), exclude_keywords=["Senior", "Lead"]
    )
    with session_factory() as db:
        report = run_crawl([scraper], _cfg(), db, now=NOW)

    assert "j/2" not in asked  # "Senior Java": ruled out by its listing title
    assert report.totals.fetched == 3
    assert report.totals.filtered == 2
    assert report.totals.inserted == 1


def test_the_pipeline_still_excludes_a_title_only_the_detail_page_shows(session_factory):
    """The listing title is a first look, not the verdict. A card that reads
    "Java Engineer" over a posting titled "Senior Java Engineer" passes the
    scraper and is dropped here, as it always was."""
    pages = {
        SEARCH_URL: '<a class="job" href="j/1" data-id="1">Java Engineer</a>',
        "j/1": _detail("Senior Java Engineer", "ACME", skills="Java"),
    }
    scraper = FixtureScraper(pages, rate_limiter=RateLimiter(0, 0), exclude_keywords=["Senior"])
    with session_factory() as db:
        report = run_crawl([scraper], _cfg(), db, now=NOW)
    assert scraper.titles_dropped == 0
    assert (report.totals.fetched, report.totals.filtered, report.totals.inserted) == (1, 1, 0)


def test_the_exclude_list_reaches_every_scraper_the_registry_builds():
    from jobpilot.config import SourceCfg
    from jobpilot.crawler.registry import SCRAPERS, build_scrapers

    cfg = _cfg()
    cfg.sources = [SourceCfg(key=key, enabled=True) for key in SCRAPERS]
    built = build_scrapers(cfg, respect_robots=False)
    assert {s.source for s in built} == set(SCRAPERS)
    assert all(s.exclude_keywords == ("Senior", "Lead") for s in built)
