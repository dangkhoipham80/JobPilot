"""The shared listing-page walk in ``BaseScraper.search``.

One fetch used to be the whole crawl, so ``jobs_per_site`` above a site's page
size quietly came back short — VietnamWorks lazy-loads ~9-20 cards and the rest
are skeletons awaiting a scroll. Paging fixes that, but it introduces its own
failure: a board that *accepts* ``?page=2`` and ignores it answers 200 with page
1 again. These tests pin both halves — that we page, and that we notice when
paging does nothing.
"""

from __future__ import annotations

import logging

import pytest

from jobpilot.crawler.base import BaseScraper
from jobpilot.crawler.ratelimit import RateLimiter
from jobpilot.crawler.types import RawJob, SearchHit


class PagedScraper(BaseScraper):
    """A board with ``per_page`` jobs per page and ``total`` jobs in all."""

    source = "paged"

    def __init__(self, *, total: int = 25, per_page: int = 10, honours_page: bool = True, **kw):
        kw.setdefault("rate_limiter", RateLimiter(0, 0))
        super().__init__(**kw)
        self.total = total
        self.per_page = per_page
        self.honours_page = honours_page
        self.fetched: list[str] = []
        self.fetcher = self._fetch_page

    def _fetch_page(self, url: str) -> str:
        self.fetched.append(url)
        page = int(url.rsplit("=", 1)[1])
        if not self.honours_page:
            page = 1  # the whole point: the parameter is accepted and ignored
        start = (page - 1) * self.per_page
        ids = range(start, min(start + self.per_page, self.total))
        return ",".join(str(i) for i in ids)

    def search_url(self, query: str, page: int = 1) -> str:
        return f"https://board.test/jobs?q={query}&page={page}"

    def parse_search(self, text: str) -> list[SearchHit]:
        return [
            SearchHit(native_id=i, url=f"https://board.test/j/{i}") for i in text.split(",") if i
        ]

    def parse_detail(self, text: str, hit: SearchHit) -> RawJob:
        return RawJob(source=self.source, native_id=hit.native_id, url=hit.url, title=hit.native_id)


def test_paging_reaches_a_limit_no_single_page_could():
    """The bug this phase fixes: 25 wanted, 10 per page."""
    scraper = PagedScraper(total=100, per_page=10)
    hits = scraper.search("java", limit=25)
    assert len(hits) == 30  # three pages fetched; crawl() trims to 25
    assert len(scraper.fetched) == 3


def test_one_page_is_enough_when_it_already_has_the_limit():
    """A 50-card board must not be paged for the sake of it."""
    scraper = PagedScraper(total=100, per_page=50)
    scraper.search("java", limit=10)
    assert len(scraper.fetched) == 1


def test_max_pages_is_a_hard_ceiling():
    scraper = PagedScraper(total=1000, per_page=10, max_pages=2)
    assert len(scraper.search("java", limit=500)) == 20
    assert len(scraper.fetched) == 2


def test_running_off_the_end_stops_quietly():
    scraper = PagedScraper(total=15, per_page=10)
    assert len(scraper.search("java", limit=100)) == 15
    # page 3 is empty and ends the walk; nothing beyond it is requested.
    assert len(scraper.fetched) == 3


def test_a_site_that_ignores_the_page_parameter_is_caught_and_reported(caplog):
    """Without cross-page dedup this collects the same 10 jobs five times and
    reports a successful deep sweep — the TopCV ``?keyword=`` failure again."""
    scraper = PagedScraper(total=100, per_page=10, honours_page=False)
    with caplog.at_level(logging.WARNING):
        hits = scraper.search("java", limit=50)

    assert len(hits) == 10  # not 50, and not 10 duplicated five times
    assert len({h.native_id for h in hits}) == 10
    assert len(scraper.fetched) == 2  # page 2 proved the point; no page 3
    assert any("ignoring the page parameter" in r.getMessage() for r in caplog.records)


def test_a_source_with_no_page_two_is_not_asked_twice():
    """Returning page 1's URL (or "") is how a single-page source opts out."""

    class SinglePage(PagedScraper):
        def search_url(self, query: str, page: int = 1) -> str:
            return "https://board.test/jobs?q=x&page=1"

    scraper = SinglePage(total=100, per_page=10)
    scraper.search("java", limit=50)
    assert len(scraper.fetched) == 1


def test_page_one_failure_fails_the_site_but_a_later_page_does_not():
    """Page 1 dying means the site is down — the pipeline isolates it. Page 3
    dying must not throw away a good page 1."""

    class FlakyLater(PagedScraper):
        def _fetch_page(self, url: str) -> str:
            if url.endswith("page=2"):
                raise RuntimeError("cloudflare")
            return super()._fetch_page(url)

    scraper = FlakyLater(total=100, per_page=10)
    assert len(scraper.search("java", limit=50)) == 10

    class FlakyFirst(PagedScraper):
        def _fetch_page(self, url: str) -> str:
            raise RuntimeError("cloudflare")

    with pytest.raises(RuntimeError, match="cloudflare"):
        FlakyFirst().search("java", limit=10)


def test_pages_after_the_first_are_rate_limited():
    """Paging is still N requests at somebody's site (principle 5)."""
    waits: list[int] = []
    limiter = RateLimiter(0, 0)
    limiter.wait = lambda: waits.append(1)  # type: ignore[method-assign]

    scraper = PagedScraper(total=100, per_page=10, rate_limiter=limiter)
    scraper.search("java", limit=25)
    assert len(waits) == 2  # before page 2 and page 3, not before page 1


def test_needs_detail_false_skips_the_detail_fetch():
    class FeedLike(PagedScraper):
        needs_detail = False

    scraper = FeedLike(total=5, per_page=10)
    jobs = scraper.crawl("java", limit=5)
    assert len(jobs) == 5
    assert len(scraper.fetched) == 1  # the listing only — no per-job requests


def test_needs_detail_true_still_fetches_each_job():
    scraper = PagedScraper(total=3, per_page=10)
    scraper.crawl("java", limit=3)
    assert [u for u in scraper.fetched if "/j/" in u] == [
        "https://board.test/j/0",
        "https://board.test/j/1",
        "https://board.test/j/2",
    ]


def test_a_page_with_nothing_relevant_does_not_end_the_walk():
    """A general board serves whole pages with no Java on them, and page N+1 may
    be full of it. Stopping at the first barren page silently truncates the
    crawl — seen live on Arbeitnow, whose page 3 had 100 jobs and 0 matches."""

    class OnlyPageThreeMatches(PagedScraper):
        def matches_query(self, hit: SearchHit, query: str) -> bool:
            return int(hit.native_id) >= 20

    scraper = OnlyPageThreeMatches(total=100, per_page=10, max_pages=5)
    hits = scraper.search("java", limit=5)
    assert len(scraper.fetched) == 3  # pages 1 and 2 were barren, not final
    # Page 3's matches, whole; crawl() is what trims to the limit.
    assert [h.native_id for h in hits] == [str(i) for i in range(20, 30)]


def test_repeated_ids_still_stop_the_walk_even_when_nothing_is_relevant():
    """The ignored-page-parameter check must not depend on relevance, or a site
    that loops the same irrelevant page would be re-fetched to the ceiling."""

    class NothingMatches(PagedScraper):
        def matches_query(self, hit: SearchHit, query: str) -> bool:
            return False

    scraper = NothingMatches(total=100, per_page=10, honours_page=False, max_pages=5)
    assert scraper.search("java", limit=5) == []
    assert len(scraper.fetched) == 2  # page 2 repeated page 1 → stop


def test_matches_query_filters_before_the_limit_is_counted():
    """A feed source has no server-side search, so relevance decides which hits
    fill the budget — otherwise `limit` is spent on jobs the pipeline drops."""

    class OddOnly(PagedScraper):
        def matches_query(self, hit: SearchHit, query: str) -> bool:
            return int(hit.native_id) % 2 == 1

    scraper = OddOnly(total=100, per_page=10)
    hits = scraper.search("java", limit=10)
    assert all(int(h.native_id) % 2 == 1 for h in hits)
    assert len(hits) >= 10


# --------------------------------------------------------------------------- #
# title exclusions, asked before the limit is spent
# --------------------------------------------------------------------------- #
class TitledScraper(BaseScraper):
    """A board whose listing is the given titles, ``per_page`` to a page."""

    source = "titled"

    def __init__(self, titles: list[str], *, per_page: int = 10, **kw):
        kw.setdefault("rate_limiter", RateLimiter(0, 0))
        super().__init__(**kw)
        self.titles = titles
        self.per_page = per_page
        self.fetched: list[str] = []
        self.fetcher = self._serve

    def _serve(self, url: str) -> str:
        self.fetched.append(url)
        return url

    def search_url(self, query: str, page: int = 1) -> str:
        return f"https://board.test/jobs?page={page}"

    def parse_search(self, text: str) -> list[SearchHit]:
        page = int(text.rsplit("=", 1)[1])
        start = (page - 1) * self.per_page
        return [
            SearchHit(native_id=str(i), url=f"https://board.test/j/{i}", title=title)
            for i, title in enumerate(self.titles[start : start + self.per_page], start=start)
        ]

    def parse_detail(self, text: str, hit: SearchHit) -> RawJob:
        return RawJob(source=self.source, native_id=hit.native_id, url=hit.url, title=hit.title)

    @property
    def details(self) -> list[str]:
        return [u for u in self.fetched if "/j/" in u]


#: A board that leads with the roles the user excluded: six of the first ten.
SENIOR_FIRST = ["Senior Engineer"] * 6 + ["Engineer"] * 4 + ["Engineer"] * 10


def test_an_excluded_title_does_not_spend_the_limit():
    """The bug: ten jobs a site, six of them thrown away after being fetched.

    The pipeline dropped "Senior …" all along, but only once the limit had been
    spent on it. Asked of the listing title instead, the ten places go to ten
    postings that are kept, the walk goes on to page 2 to find them, and no
    detail page is requested for a title that was never going to be stored.
    """
    scraper = TitledScraper(SENIOR_FIRST, exclude_keywords=["Senior", "Lead"])
    jobs = scraper.crawl("engineer", limit=10)

    assert [j.title for j in jobs] == ["Engineer"] * 10
    assert len(scraper.details) == 10
    assert not {"https://board.test/j/0", "https://board.test/j/5"} & set(scraper.details)
    assert scraper.titles_dropped == 6


def test_a_page_of_nothing_but_excluded_titles_is_not_the_end_of_the_board():
    """A page the filter empties is neither an empty page nor a repeated one:
    the site moved on, we just wanted none of it. Stopping there would leave a
    board with nine cards a page — most of them senior — short on every crawl,
    with nothing in the log but "only N hits"."""
    titles = ["Senior Engineer"] * 4 + ["Engineer"] * 4
    scraper = TitledScraper(titles, per_page=4, exclude_keywords=["Senior"])
    jobs = scraper.crawl("engineer", limit=3)

    assert [j.title for j in jobs] == ["Engineer"] * 3
    listings = [u for u in scraper.fetched if "/j/" not in u]
    assert listings == ["https://board.test/jobs?page=1", "https://board.test/jobs?page=2"]
    assert scraper.titles_dropped == 4


def test_a_scraper_built_bare_excludes_nothing():
    """Off unless configured: the pipeline's own check is then the only one,
    which is exactly how every crawl worked before."""
    scraper = TitledScraper(SENIOR_FIRST)
    jobs = scraper.crawl("engineer", limit=10)
    assert [j.title for j in jobs] == ["Senior Engineer"] * 6 + ["Engineer"] * 4
    assert scraper.titles_dropped == 0


def test_a_hit_with_no_listing_title_is_kept():
    """Unknown is not excluded. A listing that does not carry the title leaves
    the question to the detail page, where the pipeline asks it again."""
    scraper = TitledScraper(["", "Senior Engineer", "Engineer"], exclude_keywords=["Senior"])
    assert [h.native_id for h in scraper.search("engineer", limit=10)] == ["0", "2"]


def test_the_dropped_count_stops_where_the_limit_does():
    """An excluded title ranked behind the last hit kept was never in this
    crawl's window. Counting it would report a deep board as a heavily filtered
    one — on a company board, which hands over its whole listing at once, the
    number would be every senior role the company has."""
    titles = ["Engineer", "Senior Engineer", "Engineer", "Engineer", "Senior Engineer", "Lead"]
    scraper = TitledScraper(titles, exclude_keywords=["Senior", "Lead"])
    hits = scraper.search("engineer", limit=2)

    assert [h.native_id for h in hits] == ["0", "2", "3"]  # the page, whole; crawl() trims
    assert scraper.titles_dropped == 1  # the one ahead of the second kept hit

    scraper.search("engineer", limit=None)
    assert scraper.titles_dropped == 3  # no limit: the whole listing is the window


def test_a_listing_that_slides_does_not_count_an_excluded_title_twice():
    """Boards shift by a card or two between two page requests. The excluded
    hit that reappears on page 2 is the same posting, seen once."""

    class Sliding(TitledScraper):
        def parse_search(self, text: str) -> list[SearchHit]:
            page = int(text.rsplit("=", 1)[1])
            ids = {1: ["a", "b"], 2: ["b", "c"], 3: []}[page]
            names = {"a": "Engineer", "b": "Senior Engineer", "c": "Engineer"}
            return [SearchHit(native_id=i, url=f"https://board.test/j/{i}", title=names[i]) for i in ids]

    scraper = Sliding([], exclude_keywords=["Senior"])
    assert [h.native_id for h in scraper.search("engineer", limit=5)] == ["a", "c"]
    assert scraper.titles_dropped == 1


def test_a_page_of_nothing_but_excluded_titles_is_not_reported_as_a_broken_parser(caplog):
    """"0 hits — the selectors no longer match" is the wrong thing to say about
    a page that was read perfectly well and held only roles the user ruled out."""
    scraper = TitledScraper(["Senior Engineer", "Engineering Lead"], exclude_keywords=["Senior", "Lead"])
    with caplog.at_level(logging.INFO):
        assert scraper.crawl("engineer", limit=10) == []

    said = [r.getMessage() for r in caplog.records]
    assert not any("selectors no longer match" in line for line in said)
    assert any("2 hit(s)" in line and "left out by title" in line for line in said)
    assert scraper.details == []
