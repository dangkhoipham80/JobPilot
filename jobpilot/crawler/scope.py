"""Where and how the user wants to work, applied to a crawl.

Two preferences, chosen on the crawl form (per run) or saved as the default in
``crawl.places`` / ``crawl.work_modes``:

* **places** — "Ho Chi Minh", "Ha Noi", "Vietnam", "Remote", a foreign city…
  They narrow the *search* where a source can be narrowed (the Vietnamese boards'
  city URL, the company boards' ``ats.locations``) and then decide which crawled
  postings are kept.
* **work_modes** — onsite / hybrid / remote.

**Not knowing is not a mismatch.** A posting with no location label, or whose
work mode nobody stated, is kept: most of this corpus never says "hybrid", and
dropping every posting that is silent about it would empty the crawl while
reporting it filtered "by preference". Only a posting that *states* something
outside the preferences is left out, and it is counted in ``filtered``.
"""

from __future__ import annotations

from dataclasses import dataclass

from jobpilot.crawler.ats import place_matches
from jobpilot.crawler.normalize import WORK_MODES, NormalizedJob
from jobpilot.crawler.vietnam import VIETNAMESE_CITIES, canonical_city

#: What "anywhere in the country" is called in a place list.
COUNTRY = "vietnam"


def _is_country(term: str) -> bool:
    return term.strip().lower() in (COUNTRY, "viet nam", "việt nam")


@dataclass(frozen=True)
class Scope:
    places: tuple[str, ...] = ()
    work_modes: tuple[str, ...] = ()

    @classmethod
    def of(cls, places: list[str] | None, work_modes: list[str] | None) -> Scope:
        clean_places = tuple(dict.fromkeys(p.strip() for p in places or [] if p and p.strip()))
        modes = tuple(m for m in dict.fromkeys(work_modes or []) if m in WORK_MODES)
        # Every mode chosen is the same as none chosen: no filter.
        if set(modes) == set(WORK_MODES):
            modes = ()
        return cls(places=clean_places, work_modes=modes)

    @property
    def empty(self) -> bool:
        return not self.places and not self.work_modes

    def board_city(self) -> str | None:
        """The one city to put in the Vietnamese boards' URL, if there is one.

        ``None`` = no place preference: keep ``crawl.city`` as configured. ``""``
        = search the whole country — several cities, or "Vietnam", or places
        abroad; the boards take one city at most, and ``keeps`` narrows after.
        """
        if not self.places:
            return None
        cities = {canonical_city(p) for p in self.places if not _is_country(p)}
        cities &= VIETNAMESE_CITIES
        if len(cities) == 1 and not any(_is_country(p) for p in self.places):
            return next(p for p in self.places if canonical_city(p) in cities)
        return ""

    def keeps(self, job: NormalizedJob) -> str | None:
        """``None`` when the posting fits; otherwise the reason it does not."""
        mode = (job.payload or {}).get("work_mode")
        if self.work_modes and mode and mode not in self.work_modes:
            return f"work mode {mode}"
        if not self.places:
            return None
        label = job.location or (job.payload or {}).get("location")
        if not label:
            return None
        if any(place_matches(label, term) for term in self.places):
            return None
        # A remote posting is not *at* a place; "Remote" in the list asks for it.
        if mode == "remote" and any(p.lower() == "remote" for p in self.places):
            return None
        return f"location {label}"
