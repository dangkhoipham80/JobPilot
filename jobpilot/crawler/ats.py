"""ATS adapters — one scraper covering many company career pages (PLAN §5.1.1 tier 3).

Most companies don't build a job board; they rent one. Greenhouse and Lever each
publish a documented JSON endpoint per customer, so a single adapter reaches
every company on that platform — "thêm nguồn = thêm 1 dòng config" taken to its
conclusion: adding a *company* is one word in a list.

This is also where the good jobs are. A role usually appears on the employer's
own careers page before it reaches an aggregator, and some never leave it.

**A "page" here is a company.** The shared paging loop asks ``search_url`` for
page 1, 2, 3… and stops when the URLs run out, which is exactly "walk the
configured boards in order". Nothing about the loop needed changing; the only
override is ``max_pages``, because `crawl.max_pages` exists to stop us walking
an *unbounded* board forever and a hand-written list of companies is already
bounded by the person who wrote it.

``robots.txt`` (checked against :class:`~jobpilot.crawler.robots.RobotsPolicy`,
not by eye):

* ``boards-api.greenhouse.io`` disallows only ``/embed/`` — the board endpoint is
  fine.
* ``api.lever.co`` is ``Allow: /`` with ``Crawl-delay: 1``; the crawler's 2-5s
  limiter already exceeds that.
* **Ashby is deliberately absent.** ``api.ashbyhq.com`` serves no robots.txt at
  all (401) while its sibling ``jobs.ashbyhq.com`` disallows ``/api/``. That is
  the same shape as VietnamWorks' internal XHR host, which this project also
  declined to call — it needs an explicit decision, not a default.

Applying always happens on the employer's own form, so ``apply_channel`` is
``external``: JobPilot hands you the link and you submit (principle 2).
"""

from __future__ import annotations

import html
import logging
import re
from urllib.parse import quote

from jobpilot.crawler.feed import FeedScraper, load_json
from jobpilot.crawler.text import clean_text, fold
from jobpilot.crawler.types import RawJob, SearchHit
from jobpilot.crawler.vietnam import CITIES, canonical_city

log = logging.getLogger(__name__)

# "Ho Chi Minh City, Ho Chi Minh City, Vietnam" / "Remote - APAC" / "Berlin | Hybrid"
_PLACE_SPLIT = re.compile(r"\s*[,;/|&]\s*|\s+-\s+|\s+(?:or|and)\s+")
_VIET_NAM_RE = re.compile(r"(?<![a-z0-9])viet nam(?![a-z0-9])")
_LETTERS_ONLY = re.compile(r"[^a-z]")
# What `canonical_city` can resolve to that is a place in Vietnam. "Remote" is
# in the city table because boards print it where a city goes; it is not one.
_VIETNAMESE_CITIES = frozenset(CITIES) - {"Remote"}


def place_matches(place: str | None, term: str | None) -> bool:
    """Whether the location label ``place`` names the configured ``term``.

    Two ways to say yes, and both are needed. The term as whole words inside
    the label, accents and case folded — so "Ho Chi Minh" finds "Ho Chi Minh
    City, Vietnam" and "Vietnam" finds it too. Whole words, not a substring:
    "India" must not claim "Indianapolis", the same trap as ``"remote" in
    "remote debugging"``. And, for the spellings that share no words at all,
    the city both sides *resolve to*: "HCMC", "Saigon" and "TP. HCM" are Ho Chi
    Minh City, "Hanoi" is "Ha Noi" — :func:`canonical_city` already knows.
    """
    folded_place, folded_term = _fold_place(place), _fold_place(term)
    if not folded_place or not folded_term:
        return False
    if re.search(rf"(?<![a-z0-9]){re.escape(folded_term)}(?![a-z0-9])", folded_place):
        return True
    cities = {
        canonical_city(part)
        for part in _PLACE_SPLIT.split(clean_text(place or ""))
        # Two-letter parts are country and state codes on a worldwide board,
        # and the city table reads some of them as Vietnamese abbreviations:
        # "San Pedro Sula, HN" is Honduras, not Hà Nội. Counted in letters, so
        # neither a full stop ("HN.") nor a postcode ("HN 11101") makes a code
        # long enough to be read as a city.
        if len(_LETTERS_ONLY.sub("", fold(part))) > 2
    }
    # A label that is just a Vietnamese city is in Vietnam whether or not it
    # says so. Without this a scope of "Vietnam" dropped every posting a board
    # labels with the bare city, which is how most of them write it.
    if folded_term == "vietnam" and cities & _VIETNAMESE_CITIES:
        return True
    return canonical_city(term) in cities


def _fold_place(text: str | None) -> str:
    """Folded label, with the country's two spellings made one.

    "Việt Nam" folds to "viet nam", which shares no whole word with "vietnam" —
    so a board writing the country the Vietnamese way would never match a
    scope written the English way, or the reverse.
    """
    return _VIET_NAM_RE.sub("vietnam", fold(clean_text(text or "")))


class AtsScraper(FeedScraper):
    """Base for board-per-company ATS APIs. Each configured board is one page."""

    #: Board tokens (the company's slug on that ATS).
    boards: tuple[str, ...] = ()

    #: Places to keep (``ats.locations``). Empty means every location. A company
    #: board is worldwide — on one checked for this, about one posting in
    #: twenty-five was in the city being searched — so without this the
    #: per-site limit is spent on another continent and the crawl still reports
    #: success.
    locations: tuple[str, ...] = ()

    def __init__(
        self,
        *,
        boards: list[str] | None = None,
        locations: list[str] | None = None,
        **kw,
    ) -> None:
        super().__init__(**kw)
        if boards is not None:
            self.boards = tuple(b.strip() for b in boards if b and b.strip())
        if locations is not None:
            self.locations = tuple(t.strip() for t in locations if t and t.strip())
        self._out_of_scope = 0
        # One page per company: the config ceiling is about unbounded boards,
        # and this list is already bounded by whoever typed it.
        self.max_pages = max(1, len(self.boards))

    def board_url(self, board: str) -> str:  # pragma: no cover - overridden
        raise NotImplementedError

    def search_url(self, query: str, page: int = 1) -> str:
        if not 1 <= page <= len(self.boards):
            return ""
        return self.board_url(self.boards[page - 1])

    def search(self, query: str = "", limit: int | None = None) -> list[SearchHit]:
        """Say "no companies configured" plainly instead of "0 hits".

        Without this the shared loop reports the generic zero-results warning,
        which reads as "the parser broke" — a misleading thing to tell someone
        whose only mistake is not having filled in a list yet.
        """
        if not self.boards:
            log.info(
                "[%s] no company boards configured — add tokens under `ats.%s` in "
                "config.yaml (the slug in the careers-page URL)",
                self.source,
                self.source,
            )
            return []
        self._out_of_scope = 0
        hits = super().search(query, limit)
        if self._out_of_scope:
            # Said out loud: a board that yields nothing because every posting
            # is elsewhere must not read like a board with no matching jobs.
            log.info(
                "[%s] %d posting(s) outside ats.locations %s left out",
                self.source,
                self._out_of_scope,
                list(self.locations),
            )
        return hits

    def match_haystack(self, hit: SearchHit) -> str:
        """Title plus the ATS's own department/team labels."""
        return f"{hit.title} {' '.join(hit.extra.get('tags') or [])}"

    @property
    def stack_gated(self) -> bool:
        """A company board held to a location is exempt from the stack gate.

        The gate clears off-topic postings out of a searched board. On a board
        the user named *and* scoped to a place, what it removed was not noise:
        checked against two real boards it dropped the plain "Software
        Engineer" roles, whose JD names no stack at all. Those are kept with a
        match score of 0 — shown, and visibly unranked — rather than never
        shown. Title exclusions still apply.

        Only when scoped. A query matches any word of a title, so against a
        whole worldwide board "ai engineer" also matches every engineer the
        company employs who does not write software, and the gate is the only
        thing that removes them — one real board kept dozens of such postings
        at score 0 without it. With no ``locations`` this is the old behaviour.
        """
        return not self.locations

    def places(self, hit: SearchHit) -> list[str]:
        """Every location *label* the posting carries — what the board wrote.

        One for most boards; overridden where a posting can list several.
        """
        return [hit.location] if hit.location else []

    def scope_hints(self, hit: SearchHit) -> list[str]:
        """Places the posting is in that its labels do not say.

        Used to decide scope and for nothing else. A hint is something this
        code worked out (a country, from a country code), not something the
        board wrote, so it is never stored as the job's location: it once was,
        and a scope of "Vietnam" then saved every local posting as located in
        "Vietnam" with no city at all.
        """
        return []

    def in_scope(self, hit: SearchHit) -> bool:
        """Whether the posting is in one of the configured ``locations``.

        A posting that carries no location label is kept, whatever the hints
        say. Not knowing which city a job is in is not the same as knowing it
        is elsewhere, and dropping it would be a silent loss of exactly the
        kind this filter exists to end.
        """
        if not self.locations:
            return True
        labels = self.places(hit)
        if not labels:
            return True
        return any(
            place_matches(p, term)
            for p in (*labels, *self.scope_hints(hit))
            for term in self.locations
        )

    def location_of(self, hit: SearchHit) -> str | None:
        """The location to store: the label that put the posting in scope.

        A posting open in several offices is listed under the first one. Kept
        for its Ho Chi Minh City office but stored as "London", it would then
        be invisible to the very city filter it was crawled for. Chosen among
        the board's own labels only; when a hint is what matched, the board's
        first label stands.
        """
        for place in self.places(hit):
            if any(place_matches(place, term) for term in self.locations):
                return place
        return hit.location

    def matches_query(self, hit: SearchHit, query: str) -> bool:
        # Location first, and here rather than after the search: `matches_query`
        # runs before `limit` is counted, so the limit is spent on postings in
        # scope instead of being used up by the ones about to be thrown away.
        if not self.in_scope(hit):
            self._out_of_scope += 1
            return False
        return super().matches_query(hit, query)


# --------------------------------------------------------------------------- #
# Greenhouse
# --------------------------------------------------------------------------- #
GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseScraper(AtsScraper):
    source = "greenhouse"

    def board_url(self, board: str) -> str:
        # `content=true` returns the full description inline, which is what makes
        # this a one-request-per-company source instead of one-per-job.
        return f"{GREENHOUSE_API}/{quote(board)}/jobs?content=true"

    def parse_search(self, text: str) -> list[SearchHit]:
        data = load_json(text)
        if not isinstance(data, dict):
            raise ValueError(f"expected a Greenhouse board object, got {type(data).__name__}")

        hits: list[SearchHit] = []
        for job in data.get("jobs") or []:
            native_id = clean_text(str(job.get("id") or ""))
            url = clean_text(str(job.get("absolute_url") or ""))
            title = clean_text(str(job.get("title") or ""))
            if not native_id or not url or not title:
                continue
            hits.append(
                SearchHit(
                    native_id=native_id,
                    url=url,
                    title=title[:200],
                    company=clean_text(str(job.get("company_name") or "")),
                    location=clean_text(str((job.get("location") or {}).get("name") or "")) or None,
                    # `first_published` is when the role opened; `updated_at` moves
                    # every time a recruiter edits a typo and would make an old
                    # posting look brand new.
                    posted_raw=clean_text(
                        str(job.get("first_published") or job.get("updated_at") or "")
                    )
                    or None,
                    extra={"tags": _greenhouse_tags(job), "job": job},
                )
            )
        return hits

    def parse_detail(self, text: str, hit: SearchHit) -> RawJob:
        job = dict(hit.extra.get("job") or {})
        return RawJob(
            source=self.source,
            native_id=hit.native_id,
            url=hit.url,
            title=hit.title,
            company=hit.company,
            location=self.location_of(hit),
            salary=None,  # Greenhouse boards don't publish one.
            posted_raw=hit.posted_raw,
            skills=list(hit.extra.get("tags") or [])[:20],
            # The API double-encodes: `content` arrives as "&lt;div&gt;…", so
            # storing it raw shows the reader literal tags instead of the JD.
            description_html=html.unescape(str(job.get("content") or "")),
            apply_channel="external",
            apply_target=hit.url,
            extra={"ats": "greenhouse", "requisition_id": str(job.get("requisition_id") or "")},
        )


def _greenhouse_tags(job: dict) -> list[str]:
    """Department and office names — the only categorisation the board carries."""
    out: list[str] = []
    for key in ("departments", "offices"):
        for item in job.get(key) or []:
            name = clean_text(str((item or {}).get("name") or ""))
            if name and name not in out:
                out.append(name)
    return out


# --------------------------------------------------------------------------- #
# Lever
# --------------------------------------------------------------------------- #
LEVER_API = "https://api.lever.co/v0/postings"
# hostedUrl is https://jobs.lever.co/<company>/<uuid>
_LEVER_COMPANY_RE = re.compile(r"jobs\.lever\.co/([^/]+)/")


class LeverScraper(AtsScraper):
    source = "lever"

    def board_url(self, board: str) -> str:
        return f"{LEVER_API}/{quote(board)}?mode=json"

    def places(self, hit: SearchHit) -> list[str]:
        """``categories.location`` plus ``allLocations``.

        Lever lets one posting be open in several offices and puts only the
        first in ``location``; a role listed as "London" that is also open in
        Ho Chi Minh City would otherwise be filtered out of the very city it
        is hiring in.
        """
        categories = (hit.extra.get("job") or {}).get("categories") or {}
        out = super().places(hit)
        for place in categories.get("allLocations") or []:
            label = clean_text(str(place or ""))
            if label and label not in out:
                out.append(label)
        return out

    def scope_hints(self, hit: SearchHit) -> list[str]:
        """The country, which Lever's labels leave out.

        A label is the city alone ("Ho Chi Minh City"); the country travels
        separately as an ISO code. Without it a scope of "Vietnam" matched
        nothing on a board whose every local posting was in Vietnam. Only this
        one code is spelled out: the codes are not passed on raw, because
        "CA", "IN" and "DE" are also words and states.
        """
        country = clean_text(str((hit.extra.get("job") or {}).get("country") or ""))
        return ["Vietnam"] if country.upper() == "VN" else []

    def parse_search(self, text: str) -> list[SearchHit]:
        data = load_json(text)
        if not isinstance(data, list):
            # A wrong/expired board token answers 404 with an object, not a list.
            raise ValueError(f"expected a Lever posting array, got {type(data).__name__}")

        hits: list[SearchHit] = []
        for job in data:
            native_id = clean_text(str(job.get("id") or ""))
            url = clean_text(str(job.get("hostedUrl") or ""))
            title = clean_text(str(job.get("text") or ""))
            if not native_id or not url or not title:
                continue
            categories = job.get("categories") or {}
            hits.append(
                SearchHit(
                    native_id=native_id,
                    url=url,
                    title=title[:200],
                    # Lever's payload never names the employer — only the board
                    # does, and the board slug is in the URL of every posting.
                    company=_lever_company(url),
                    location=clean_text(str(categories.get("location") or "")) or None,
                    posted_raw=_ms_to_epoch_seconds(job.get("createdAt")),
                    extra={"tags": _lever_tags(categories), "job": job},
                )
            )
        return hits

    def parse_detail(self, text: str, hit: SearchHit) -> RawJob:
        job = dict(hit.extra.get("job") or {})
        return RawJob(
            source=self.source,
            native_id=hit.native_id,
            url=hit.url,
            title=hit.title,
            company=hit.company,
            location=self.location_of(hit),
            salary=None,
            posted_raw=hit.posted_raw,
            skills=list(hit.extra.get("tags") or [])[:20],
            description_html=_lever_description(job),
            apply_channel="external",
            apply_target=hit.url,
            extra={
                "ats": "lever",
                "workplace_type": clean_text(str(job.get("workplaceType") or "")),
            },
        )


def _lever_company(url: str) -> str:
    match = _LEVER_COMPANY_RE.search(url)
    return match.group(1).replace("-", " ").title() if match else ""


def _lever_tags(categories: dict) -> list[str]:
    out: list[str] = []
    for key in ("team", "department", "commitment"):
        value = clean_text(str(categories.get(key) or ""))
        if value and value not in out:
            out.append(value)
    return out


def _lever_description(job: dict) -> str:
    """The whole posting, not just the intro.

    Lever splits a job across ``description`` (the pitch), ``lists`` (the actual
    requirements and responsibilities) and ``additional`` (benefits). Keeping
    only ``description`` hands the tailor a company blurb with none of the
    requirements the CV has to answer — the same mistake as reading
    VietnamWorks' JSON-LD description and losing "Yêu cầu công việc".
    """
    parts = [str(job.get("description") or "")]
    for block in job.get("lists") or []:
        text = clean_text(str((block or {}).get("text") or ""))
        content = str((block or {}).get("content") or "")
        if text:
            parts.append(f"<h3>{html.escape(text)}</h3>")
        if content:
            parts.append(f"<ul>{content}</ul>")
    parts.append(str(job.get("additional") or ""))
    return "".join(p for p in parts if p)


def _ms_to_epoch_seconds(value) -> str | None:
    """Lever timestamps are milliseconds; ``parse_posted_at`` reads seconds.

    Converted here rather than by widening the epoch guard: that guard accepts
    9-11 digits precisely so a stray 13-digit number is *not* mistaken for a
    date, and loosening it to please one source would give that protection away
    for every other source.
    """
    try:
        return str(int(value) // 1000)
    except (TypeError, ValueError):
        return None
