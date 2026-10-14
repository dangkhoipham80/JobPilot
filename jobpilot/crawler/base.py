"""``BaseScraper`` — the per-site scraper contract + a shared crawl loop.

Subclasses implement three *pure* methods (``search_url``, ``parse_search``,
``parse_detail``) that never touch the network — they operate on text (HTML,
RSS or JSON), so they're unit-testable against snapshot fixtures (PLAN §5.1).
``crawl`` is the template method that wires fetching, robots, rate-limiting,
pagination and graceful per-hit failure around them.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable

from jobpilot.crawler.jsonld import find_job_posting, org_logo
from jobpilot.crawler.normalize import title_excluded
from jobpilot.crawler.ratelimit import RateLimiter
from jobpilot.crawler.robots import RobotsPolicy
from jobpilot.crawler.types import RawJob, SearchHit

log = logging.getLogger(__name__)

Fetcher = Callable[[str], str]

#: How many listing pages one site may be asked for in a single crawl. A guard
#: against walking a board forever, not a target: the loop stops as soon as it
#: has ``limit`` hits, which for a 50-card page is page 1.
DEFAULT_MAX_PAGES = 5


class RobotsDisallowed(RuntimeError):
    """A URL is disallowed by the site's robots.txt."""


#: Ceiling on the per-run page memo (``BaseScraper._fetch``), in characters.
#: ~32 MB covers the default sweep (10 jobs × a few keywords) many times over.
MEMO_BUDGET_CHARS = 32 * 1024 * 1024


class BaseScraper(ABC):
    source: str = "base"

    #: Whether a job must name one of ``crawl.stacks`` to be kept. True for a
    #: board that is *searched*: a general board answers "developer" with CNC
    #: machinists and "ai" with marketing roles, and the stack list is the only
    #: thing in the pipeline that removes them. False for a source its user
    #: assembled by hand *and* held to a place — see
    #: :attr:`jobpilot.crawler.ats.AtsScraper.stack_gated`.
    stack_gated: bool = True

    #: False when the listing already carries the whole job, so there is no
    #: detail page worth fetching. Official feeds ship the full description
    #: inline; requesting each job page again would be N pointless requests.
    needs_detail: bool = True

    def __init__(
        self,
        *,
        fetcher: Fetcher | None = None,
        rate_limiter: RateLimiter | None = None,
        robots: RobotsPolicy | None = None,
        max_pages: int | None = None,
        exclude_keywords: list[str] | None = None,
    ) -> None:
        self.fetcher = fetcher
        self.rate = rate_limiter or RateLimiter()
        self.robots = robots
        self.max_pages = max_pages if max_pages is not None else DEFAULT_MAX_PAGES
        #: ``crawl.exclude_keywords``, applied to a listing title *before* the
        #: hit counts toward ``limit`` (see :meth:`search`). Empty — the default
        #: for a scraper built bare — leaves every hit in and the pipeline's own
        #: check as the only one, which is how it worked before.
        self.exclude_keywords = tuple(exclude_keywords or ())
        #: Hits the most recent :meth:`search` left out by title, counted up to
        #: the point where ``limit`` was met. The pipeline adds them to the
        #: run's ``fetched`` and ``filtered``: they were seen and they were
        #: filtered, only earlier than the rest and without a detail request.
        self.titles_dropped = 0
        #: Hits the most recent :meth:`search` left out *on purpose* for a reason
        #: of the scraper's own (a card that names another city). Only read to
        #: tell "the page was read and nothing on it was wanted" apart from "the
        #: parser found nothing" — see :meth:`crawl`.
        self.left_out = 0
        self._owned_fetcher = None  # lazily created default, closed by close()
        # Per-run request state, reset by close(). See _fetch.
        self._requested = False
        self._memo: dict[str, str] = {}
        self._memo_chars = 0

    # -- pure, per-site (implement these) ---------------------------------- #
    @abstractmethod
    def search_url(self, query: str, page: int = 1) -> str:
        """URL of listing page ``page`` (1-based) for ``query``.

        Return the *same* URL as page 1 (or ``""``) when the source has no
        further pages — that is how a single-page source opts out of paging, and
        :meth:`search` stops without spending a request to find out.
        """

    @abstractmethod
    def parse_search(self, text: str) -> list[SearchHit]:
        """Extract listing hits from a search page's body."""

    @abstractmethod
    def parse_detail(self, text: str, hit: SearchHit) -> RawJob:
        """Extract a full :class:`RawJob` from a detail page's body."""

    # -- optional per-site hooks ------------------------------------------- #
    def matches_query(self, hit: SearchHit, query: str) -> bool:
        """Whether ``hit`` answers ``query``. True unless a source says otherwise.

        Search-backed sources have already applied the query server-side, so the
        default is to trust them. Feed-backed sources, which serve a fixed
        listing no matter what you ask for, override this — see
        :class:`jobpilot.crawler.feed.FeedScraper`.
        """
        return True

    def rank_hits(self, hits: list[SearchHit], query: str) -> list[SearchHit]:
        """Order one page's hits best-first. Unchanged unless a source says otherwise.

        A search-backed source already ranked its own results and knows more
        about relevance than we do. Feed-backed sources hand back a whole board
        in publication order, where ``limit`` would otherwise be spent on
        whatever happens to sit at the top — see
        :class:`jobpilot.crawler.feed.FeedScraper`.
        """
        return hits

    def title_dropped(self, hit: SearchHit) -> bool:
        """Whether the listing title alone rules ``hit`` out.

        The pipeline's rule (``normalize.title_excluded``), asked one step
        earlier. A hit whose listing carries no title is kept — an empty title
        contains no keyword: not knowing what a posting is called is not
        knowing it is excluded, and its detail page will say.
        """
        return title_excluded(hit.title, self.exclude_keywords)

    def default_fetcher(self) -> Fetcher:
        """The fetcher to use when none was injected. Browser by default."""
        from jobpilot.crawler.fetch import PlaywrightFetcher

        return PlaywrightFetcher()

    #: Whether ``crawl(query)`` depends on the query at all. A source that
    #: ignores it (LinkedIn alerts: whatever LinkedIn emailed you) runs once per
    #: run however many keywords were given, and is not credited to any one
    #: keyword — every job would otherwise land on the first and show as
    #: "updated" under the rest.
    query_aware: bool = True

    # -- fetching ----------------------------------------------------------- #
    def _resolve_fetcher(self) -> Fetcher:
        if self.fetcher is not None:
            return self.fetcher
        if self._owned_fetcher is None:
            self._owned_fetcher = self.default_fetcher()
        return self._owned_fetcher

    def _fetch(self, url: str) -> str:
        """The one door every request to the site goes through.

        Rate limiting lives here rather than at the call sites: it waits before
        *every* request except the first of the run. It used to wait only before
        listing page 2+ and before detail pages, which was complete while a run
        made one search per site — and left a gap as soon as a run made several:
        page 1 of the next keyword went out straight after the last request of
        the previous one. ``RateLimiter`` holds no state, so the gate has to.

        A URL already fetched this run is answered from memory: no request, so
        no wait. That is what keeps several keywords from multiplying traffic on
        sources whose listing does not depend on the query (feeds, ATS boards —
        they filter locally) and from re-fetching the detail page of a posting
        two keywords both found. Failures are not remembered.
        """
        if url in self._memo:
            return self._memo[url]
        if self.robots is not None and not self.robots.allowed(url):
            raise RobotsDisallowed(url)
        if self._requested:
            self.rate.wait()
        self._requested = True
        html = self._resolve_fetcher()(url)
        # Bounded: a deep sweep (limit 200 × 8 keywords) of full Playwright
        # pages would otherwise hold hundreds of MB until the site closes. Past
        # the budget a repeat goes back to the network — still behind the wait
        # above, so politeness holds; only the saving stops.
        if self._memo_chars + len(html) <= MEMO_BUDGET_CHARS:
            self._memo[url] = html
            self._memo_chars += len(html)
        return html

    def close(self) -> None:
        if self._owned_fetcher is not None:
            close = getattr(self._owned_fetcher, "close", None)
            if callable(close):
                close()
            self._owned_fetcher = None
        self._requested = False
        self._memo.clear()
        self._memo_chars = 0

    # -- search: walk listing pages until we have enough -------------------- #
    def search(self, query: str = "", limit: int | None = None) -> list[SearchHit]:
        """Collect hits across listing pages, newest page first.

        Stops at the first of: ``limit`` hits collected, ``max_pages`` reached,
        a page with no hits, a page whose hits were all seen already, or a page
        URL identical to one already fetched.

        A hit whose title matches ``exclude_keywords`` is left out *here*, so it
        neither counts toward ``limit`` nor costs a detail request. The pipeline
        dropped those same titles anyway, but only after the limit had been
        spent on them: at ten jobs a site, a board that leads with senior roles
        gave most of its ten places to postings that were then thrown away, and
        the ones cut to make room were the ones wanted. Paging goes on past
        them, up to ``max_pages``.

        That "all seen already" check is the load-bearing one. A board that
        *accepts* ``?page=2`` and ignores it answers 200 with page 1 again, and
        without cross-page dedup the crawl would happily collect the same ten
        jobs five times and report a successful deep sweep. It is the same class
        of failure as TopCV silently dropping ``?keyword=`` (CLAUDE.md): the
        parameter is not rejected, it simply does nothing, so only the *content*
        can tell you the difference.
        """
        hits: list[SearchHit] = []
        kept_ids: set[str] = set()  # what we are returning
        dropped_ids: set[str] = set()  # relevant, but ruled out by title
        seen_ids: set[str] = set()  # everything the site has shown us, relevant or not
        seen_urls: set[str] = set()
        self.titles_dropped = 0

        for page in range(1, max(1, self.max_pages) + 1):
            url = self.search_url(query, page)
            if not url or url in seen_urls:
                break  # the source has no distinct URL for this page
            seen_urls.add(url)

            try:
                page_hits = self.parse_search(self._fetch(url))
            except Exception as exc:
                if page == 1:
                    raise  # the site itself failed — let the pipeline isolate it
                # Later pages are a bonus. Keep what we already have rather than
                # throwing away a good page 1 because page 3 timed out. The
                # reason is logged, not swallowed: "blocked — anti-bot" and
                # "timed out" call for different responses from whoever reads it.
                log.warning(
                    "[%s] page %d failed (%s), keeping %d hit(s)", self.source, page, exc, len(hits)
                )
                break

            page_ids = {h.native_id for h in page_hits if h.native_id}
            relevant = [
                h
                for h in page_hits
                if h.native_id
                and h.native_id not in kept_ids
                and h.native_id not in dropped_ids
                and self.matches_query(h, query)
            ]
            excluded = [h for h in relevant if self.title_dropped(h)]
            gone = {h.native_id for h in excluded}
            new = [h for h in relevant if h.native_id not in gone]
            log.info(
                "[%s] page %d: %d hit(s), %d new+relevant, %d more left out by title",
                self.source,
                page,
                len(page_hits),
                len(new),
                len(excluded),
            )

            if not page_ids:
                if page > 1:
                    log.info("[%s] page %d is empty — end of results", self.source, page)
                break
            # Whether the *site* moved on is a separate question from whether we
            # wanted any of it. A general job board legitimately serves a whole
            # page with no Java on it, and page N+1 may be full of it — stopping
            # there would silently truncate the crawl. Only a page that repeats
            # ids we have already been shown proves the page parameter did
            # nothing, and that is the one worth abandoning.
            if page_ids <= seen_ids:
                log.warning(
                    "[%s] page %d repeated results already seen — the site is ignoring the "
                    "page parameter; stopping at %d hit(s)",
                    self.source,
                    page,
                    len(hits),
                )
                break

            seen_ids |= page_ids
            kept_ids.update(h.native_id for h in new)
            dropped_ids |= gone
            # Walked in the order `limit` is spent, so the count stops where the
            # limit does: an excluded hit ranked behind the last one kept was
            # never in this crawl's window, and counting it would make a deep
            # board look like a heavily filtered one.
            for hit in self.rank_hits(relevant, query):
                if hit.native_id in dropped_ids:
                    if limit is None or len(hits) < limit:
                        self.titles_dropped += 1
                else:
                    hits.append(hit)
            if limit is not None and len(hits) >= limit:
                break

        return hits

    # -- crawl loop (template method) -------------------------------------- #
    def crawl(self, query: str = "", limit: int | None = None) -> list[RawJob]:
        """Search, then fetch+parse up to ``limit`` detail pages.

        A search-page failure aborts this site (propagates to the pipeline,
        which isolates it). A single detail-page failure is logged and skipped
        so one bad posting never sinks the batch.
        """
        hits = self.search(query, limit)
        # A parser whose selectors stopped matching returns [] and the crawl then
        # reports success with nothing to show — the exact failure PLAN §10 calls
        # out ("cảnh báo khi 0 job"). It is indistinguishable from a genuinely
        # empty result set, so say so loudly instead of logging it as normal.
        # Not when hits were left out by title or by the scraper's own scope:
        # the parser demonstrably read the page, and "the selectors no longer
        # match" would send whoever reads the log to fix a parser that works.
        if not hits and not self.titles_dropped and not self.left_out:
            log.warning(
                "[%s] search parsed to 0 hits for query=%r — either the query "
                "has no results or the selectors no longer match the site",
                self.source,
                query,
            )
        elif limit is not None and len(hits) < limit:
            log.warning(
                "[%s] only %d hit(s) for query=%r, wanted %d — the source ran out of "
                "pages, or has fewer matching jobs than you asked for",
                self.source,
                len(hits),
                query,
                limit,
            )
        if self.titles_dropped:
            # Said out loud for the same reason the limit cut below is: these
            # are postings the crawl saw and did not bring in, and "why is that
            # job not here" has to be answerable from the log.
            log.info(
                "[%s] %d hit(s) for query=%r left out by title (crawl.exclude_keywords) "
                "before the limit — no detail page fetched for them",
                self.source,
                self.titles_dropped,
                query,
            )
        if limit is not None:
            if len(hits) > limit:
                # Not a warning — the limit did what it was asked — but it has
                # to be findable: on a source that hands over its whole listing
                # at once (a company board) these are postings the next crawl
                # will cut again, in the same order, and never bring in.
                # "At least": a paged board stopped walking once it had enough,
                # so this is the rest of the last page, not everything unseen.
                log.info(
                    "[%s] at least %d matching hit(s) for query=%r were cut by the limit of %d",
                    self.source,
                    len(hits) - limit,
                    query,
                    limit,
                )
            hits = hits[:limit]
        log.info("[%s] %d hit(s) for query=%r", self.source, len(hits), query)

        results: list[RawJob] = []
        for hit in hits:
            try:
                detail = ""
                if self.needs_detail:
                    detail = self._fetch(hit.url)
                raw = self.parse_detail(detail, hit)
                # The employer's logo, wherever the detail page carries the
                # JSON-LD posting — one place for every board, not one per
                # scraper. Used for the company row (companies/logos.py).
                # Substring first: parsing a 1.6 MB TopCV page a second time just
                # to learn it has no JSON-LD would double the crawl's CPU.
                if "ld+json" in detail and not raw.extra.get("company_logo"):
                    logo = org_logo(find_job_posting(detail))
                    if logo:
                        raw.extra["company_logo"] = logo
                results.append(raw)
            except Exception as exc:
                log.warning("[%s] skip %s: %s", self.source, hit.url, exc)
                continue
        return results
