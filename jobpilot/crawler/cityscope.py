"""Searching a Vietnamese board within one city (``crawl.city``).

Two halves, and the second exists because of the first.

**The URL.** Each board has its own way to ask for a city — a ``city=`` token, a
path suffix, a numeric id — and a scraper puts it in ``search_url`` when it
knows one (``city_tokens``). Without it the per-site limit is spent on the whole
country: on a board where most postings are in another city, most of what a
crawl brings back is jobs the user cannot take.

**The card.** A parameter a site stops honouring is not rejected, it is ignored:
the search answers 200 with the nationwide listing, and nothing but the content
says so (the lesson ``BaseScraper.search`` records about page parameters, and
TopCV's ``?keyword=`` before it). So the scope is also held against what each
card says: a hit whose own label names other cities, and not this one, is left
out. The URL is what makes the limit well spent; the card is what makes the
result true even on the day the URL stops working.
"""

from __future__ import annotations

import logging

from jobpilot.crawler.base import BaseScraper
from jobpilot.crawler.types import SearchHit
from jobpilot.crawler.vietnam import is_elsewhere, scope_city

log = logging.getLogger(__name__)

#: Cards a city-scoped search may show for another city before it is said out
#: loud that the site is probably ignoring the scope: more than one in ten, and
#: at least two. Measured on saved listing pages of the three boards — scoped
#: pages named another city on 0 of 127 cards, unscoped ones on 22% to 78%.
_IGNORED_SHARE = 0.10
_IGNORED_MIN = 2


class CityScopedScraper(BaseScraper):
    """A board whose search can be held to one Vietnamese city."""

    #: Canonical city (the spelling ``vietnam.canonical_city`` returns) -> the
    #: token this board puts in its own search URL. Only cities whose token was
    #: read off the board's own pages *and* checked against the cards it then
    #: returned. A city missing here is searched nationwide and kept by card
    #: label alone — never with a token made up by analogy.
    city_tokens: dict[str, str] = {}

    def __init__(self, *, city: str | None = None, **kw) -> None:
        super().__init__(**kw)
        asked = (city or "").strip()
        #: The canonical city this scraper is held to, or None for every city.
        self.city: str | None = scope_city(asked) if asked else None
        if asked and self.city is None:
            log.warning(
                "[%s] crawl.city=%r is not a Vietnamese city this crawler knows — "
                "searching every city",
                self.source,
                asked,
            )
        #: This board's URL token for ``city``; None when it has no known one.
        self.city_token: str | None = self.city_tokens.get(self.city) if self.city else None
        if self.city and self.city_token is None:
            log.warning(
                "[%s] no known search URL for %s on this board — searching every city and "
                "keeping only postings whose card does not name another one",
                self.source,
                self.city,
            )
        self._cards = 0
        self._elsewhere = 0

    def place_label(self, hit: SearchHit) -> str | None:
        """What the card says about where the job is, as written.

        ``hit.location`` unless the board had to leave that empty: a parser that
        only recognises *one* city per label stores nothing for "Da Nang - Ha
        Noi", and the scope check would then never see the one card that most
        plainly says "not here". Such a parser puts the label it could not
        reduce in ``hit.extra["place_label"]``.
        """
        return hit.location or hit.extra.get("place_label")

    def matches_query(self, hit: SearchHit, query: str) -> bool:
        """Leave out a hit whose card names other cities and not ours.

        Only what the card *says*. No label, a label that cannot be read in
        full ("… & 2 nơi khác") and "Remote" all stay: not knowing where a
        posting is, is not knowing it is somewhere else.
        """
        if self.city:
            self._cards += 1
            if is_elsewhere(self.place_label(hit), self.city):
                self._elsewhere += 1
                return False
        return super().matches_query(hit, query)

    def search(self, query: str = "", limit: int | None = None) -> list[SearchHit]:
        self._cards = self._elsewhere = self.left_out = 0
        hits = super().search(query, limit)
        # For `crawl()`: a page whose every card was another city was read, not
        # mis-parsed, and must not be reported as broken selectors.
        self.left_out = self._elsewhere
        if not self._elsewhere:
            return hits
        if (
            self.city_token
            and self._elsewhere >= _IGNORED_MIN
            and self._elsewhere > self._cards * _IGNORED_SHARE
        ):
            # The scoped URL was asked for and this is what came back. Loud,
            # because the hits kept below are still right (the cards were
            # checked) while the limit was quietly spent nationwide again.
            log.warning(
                "[%s] %d of %d card(s) on a search scoped to %s name another city — the site "
                "is probably ignoring the city in the URL; they were left out",
                self.source,
                self._elsewhere,
                self._cards,
                self.city,
            )
        else:
            log.info(
                "[%s] %d of %d card(s) name another city than %s and were left out",
                self.source,
                self._elsewhere,
                self._cards,
                self.city,
            )
        return hits
