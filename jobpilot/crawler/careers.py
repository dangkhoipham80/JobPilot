"""Company career sites that are not Greenhouse or Lever.

Many large employers post mainly — some only — on their own careers site, so the
aggregators never carry the role. Most of those sites are still a platform
underneath, and each platform below is one adapter for every company on it:
adding a company is one entry under ``ats.<key>`` in config, as for Greenhouse.

Which companies the user reads is personal and belongs in ``config.local.yaml``
(gitignored), never in this public repo — see ``crawler/CLAUDE.md``. The tests
use invented companies for the same reason.

``robots.txt`` was checked for every endpoint here with
:class:`~jobpilot.crawler.robots.RobotsPolicy` (2026-10-14), and is checked again
on every request by ``BaseScraper._fetch``:

* **Indeed-style XML feeds** (``careerfeed``): a site's ``/jobs/xml`` export —
  every posting with its full description, in one request. A site serving such a
  feed may still disallow its *API* (one checked did: its SmartRecruiters API is
  disallowed, its own feed is not), which is why the feed is the door used.
* **Workday** (``workday``): ``/wday/cxs/<tenant>/<site>/jobs`` is the JSON
  search the careers page itself calls, and robots allows it. A POST, paged by
  ``offset``; the description comes from the per-posting endpoint.
* **Eightfold** (``eightfold``): ``/api/pcsx/search`` and
  ``/api/pcsx/position_details``, allowed by robots. The API answers 429 to a
  client without the session cookie the careers page sets, so each company is
  warmed up with one request to that page first — a browser does the same.
* **Google Careers** (``googlecareers``): the results page is server-rendered
  with the postings embedded as data (``AF_initDataCallback`` ``ds:1``), 20 per
  page. robots.txt **disallows paging** (``results?page=``), so only page 1 of
  each search is read, narrowed by ``q=``. The detail page carries no JSON-LD, so the embedded
  data is the only structured source; it is read by position, and a shape this
  parser does not recognise is an error, never a quiet zero.

Applying always happens on the employer's own site: ``apply_channel`` is
``external`` and JobPilot hands over the link (principle 2).
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import quote, urlencode, urlsplit
from xml.etree import ElementTree

from jobpilot.crawler.ats import AtsScraper
from jobpilot.crawler.feed import load_json
from jobpilot.crawler.text import clean_text
from jobpilot.crawler.types import RawJob, SearchHit
from jobpilot.crawler.vietnam import VIETNAMESE_CITIES, canonical_city

log = logging.getLogger(__name__)

_LONG_DIGITS = re.compile(r"/(\d{6,})(?:/|$)")
#: Workday's list writes "2 Locations" instead of naming them — not a place.
_N_LOCATIONS = re.compile(r"^\d+\s+locations?$", re.I)


def _remote_word(*texts: str | None) -> str | None:
    """onsite / hybrid / remote when a source states it as a field value."""
    for text in texts:
        value = clean_text(text or "").lower()
        if not value:
            continue
        if "hybrid" in value:
            return "hybrid"
        if "remote" in value:
            return "remote"
        if value in ("onsite", "on-site", "on site", "office", "in office"):
            return "onsite"
    return None


def _search_place(locations: tuple[str, ...]) -> str:
    """One place to hand a site's own search, from ``ats.locations``.

    The site's search narrows the request; ``in_scope`` still decides. A
    Vietnamese city widens to the country, because sites file local postings
    under "Vietnam" with or without the city, and ``in_scope`` narrows it back.
    """
    for term in locations:
        if term.strip().lower() in ("vietnam", "viet nam") or canonical_city(term) in VIETNAMESE_CITIES:
            return "Vietnam"
    return locations[0] if locations else ""


# --------------------------------------------------------------------------- #
# Indeed-style XML feed
# --------------------------------------------------------------------------- #
class CareerFeedScraper(AtsScraper):
    """A careers site's XML export: ``<source><job><title/><url/>…</job></source>``.

    A board token is the feed's full URL.
    """

    source = "careerfeed"

    def board_url(self, board: str) -> str:
        return board

    def parse_search(self, text: str) -> list[SearchHit]:
        root = ElementTree.fromstring(text.strip())
        if root.tag != "source":
            raise ValueError(f"expected an XML job feed <source>, got <{root.tag}>")
        # The employer's own site, for its logo (companies/logos.py).
        publisher = urlsplit(clean_text(root.findtext("publisherUrl") or "")).hostname or ""
        hits: list[SearchHit] = []
        for job in root.iter("job"):
            field = lambda name: clean_text(job.findtext(name) or "")  # noqa: E731
            url, title = field("url"), field("title")
            native_id = _feed_id(url) or field("referencenumber") or field("requisitionid")
            if not url or not title or not native_id:
                continue
            place = ", ".join(p for p in (field("city"), field("state"), field("country")) if p)
            hits.append(
                SearchHit(
                    native_id=native_id,
                    url=url,
                    title=title[:200],
                    company=field("company") or field("sourcename"),
                    location=place or None,
                    posted_raw=field("date") or None,
                    extra={
                        "tags": [t for t in (field("category"), field("jobtype")) if t],
                        "description": job.findtext("description") or "",
                        "work_mode": _remote_word(field("remotetype")),
                        "domain": publisher,
                    },
                )
            )
        return hits

    def parse_detail(self, text: str, hit: SearchHit) -> RawJob:
        return RawJob(
            source=self.source,
            native_id=hit.native_id,
            url=hit.url,
            title=hit.title,
            company=hit.company,
            location=self.location_of(hit),
            posted_raw=hit.posted_raw,
            skills=list(hit.extra.get("tags") or []),
            description_html=str(hit.extra.get("description") or ""),
            apply_channel="external",
            apply_target=hit.url,
            extra={
                "ats": "careerfeed",
                "work_mode_stated": hit.extra.get("work_mode"),
                "company_domain": hit.extra.get("domain") or None,
            },
        )


def _feed_id(url: str) -> str:
    """The posting id in the URL's path (``/jobs/744000155475389/slug/``)."""
    match = _LONG_DIGITS.search(urlsplit(url).path)
    return match.group(1) if match else ""


# --------------------------------------------------------------------------- #
# Workday
# --------------------------------------------------------------------------- #
WORKDAY_PAGE = 20


def _workday_parts(board: str) -> tuple[str, str, str]:
    """``acme.wd5.myworkdayjobs.com/AcmeCareers`` → (host, tenant, site)."""
    host, _, site = board.strip().strip("/").partition("/")
    tenant = host.split(".", 1)[0]
    if not host.endswith("myworkdayjobs.com") or not site:
        raise ValueError(f"workday board must be '<tenant>.wdN.myworkdayjobs.com/<site>', got {board!r}")
    return host, tenant, site.split("/")[0]


class WorkdayScraper(AtsScraper):
    """A Workday careers site. Board token: ``<tenant>.wdN.myworkdayjobs.com/<site>``."""

    source = "workday"
    needs_detail = True
    pages_per_board = 5  # 100 postings per company, after the site's own place filter
    accept = "application/json"

    def _api(self, board: str) -> str:
        host, tenant, site = _workday_parts(board)
        return f"https://{host}/wday/cxs/{tenant}/{site}"

    def board_page_url(self, board: str, query: str, page: int) -> str:
        return f"{self._api(board)}/jobs" if page <= self.pages_per_board else ""

    def board_page_body(self, board: str, query: str, page: int) -> dict:
        # The place goes in the free-text search, which matches location names;
        # Workday's location *facet* needs per-tenant ids nobody can configure.
        return {
            "appliedFacets": {},
            "limit": WORKDAY_PAGE,
            "offset": (page - 1) * WORKDAY_PAGE,
            "searchText": _search_place(self.locations),
        }

    def places(self, hit: SearchHit) -> list[str]:
        label = hit.location or ""
        return [] if not label or _N_LOCATIONS.match(label) else [label]

    def parse_search(self, text: str) -> list[SearchHit]:
        data = load_json(text)
        if not isinstance(data, dict) or "jobPostings" not in data:
            raise ValueError("expected a Workday search response with jobPostings")
        base = self._api(self._board) if self._board else ""
        host = urlsplit(base).netloc
        _, _, site = _workday_parts(self._board) if self._board else ("", "", "")
        hits: list[SearchHit] = []
        for job in data.get("jobPostings") or []:
            path = clean_text(str(job.get("externalPath") or ""))
            title = clean_text(str(job.get("title") or ""))
            if not path or not title:
                continue
            hits.append(
                SearchHit(
                    # The requisition id ends the path ("..._JR2019113").
                    native_id=f"{host.split('.', 1)[0]}:{path.rsplit('_', 1)[-1]}",
                    url=f"https://{host}/en-US/{site}{path}",
                    title=title[:200],
                    company="",  # read from the posting itself in parse_detail
                    location=clean_text(str(job.get("locationsText") or "")) or None,
                    posted_raw=None,
                    extra={"api": f"{base}{path}", "tags": []},
                )
            )
        return hits

    def detail_url(self, hit: SearchHit) -> str:
        return str(hit.extra.get("api") or hit.url)

    def parse_detail(self, text: str, hit: SearchHit) -> RawJob:
        data = load_json(text)
        info = (data or {}).get("jobPostingInfo") or {}
        if not info:
            raise ValueError("Workday posting without jobPostingInfo")
        org = clean_text(str(((data or {}).get("hiringOrganization") or {}).get("name") or ""))
        places = [clean_text(str(info.get("location") or ""))] + [
            clean_text(str(p)) for p in info.get("additionalLocations") or []
        ]
        return RawJob(
            source=self.source,
            native_id=hit.native_id,
            url=clean_text(str(info.get("externalUrl") or "")) or hit.url,
            title=clean_text(str(info.get("title") or "")) or hit.title,
            company=_company_from_legal(org) or _workday_parts(self._board_of(hit))[1].title(),
            location=next(
                (p for p in places if p and any(_matches(p, t) for t in self.locations)),
                places[0] or hit.location,
            ),
            posted_raw=clean_text(str(info.get("startDate") or "")) or None,
            description_html=str(info.get("jobDescription") or ""),
            apply_channel="external",
            apply_target=clean_text(str(info.get("externalUrl") or "")) or hit.url,
            extra={
                "ats": "workday",
                "requisition_id": clean_text(str(info.get("jobReqId") or "")),
                "work_mode_stated": _remote_word(str(info.get("remoteType") or "")),
            },
        )

    @staticmethod
    def _board_of(hit: SearchHit) -> str:
        parts = urlsplit(hit.url)
        return f"{parts.netloc}/{parts.path.split('/')[2]}"


def _matches(place: str, term: str) -> bool:
    from jobpilot.crawler.ats import place_matches

    return place_matches(place, term)


#: "VN01 Acme Vietnam Company Limited" — a legal entity, prefixed by an
#: internal code. The employer is the name, not the entity.
_ENTITY_CODE = re.compile(r"^[A-Z]{2}\d{2,3}\s+")
_ENTITY_TAIL = re.compile(
    r"\s+(?:\w+\s+)?(?:company limited|co\.,? ltd\.?|limited|ltd\.?|inc\.?|llc|gmbh|pte\.? ltd\.?)$",
    re.I,
)


def _company_from_legal(name: str) -> str:
    """Strip the internal code and the legal-entity tail of a Workday org name.

    "VN01 Acme Vietnam Company Limited" → "Acme". The country word goes with
    the tail ("Vietnam Company Limited"): the same employer files every
    country's postings under its own local entity, and the Companies page should
    list them as one employer.
    """
    out = _ENTITY_CODE.sub("", clean_text(name))
    out = _ENTITY_TAIL.sub("", out)
    return out.strip()


# --------------------------------------------------------------------------- #
# Eightfold
# --------------------------------------------------------------------------- #
EIGHTFOLD_PAGE = 10


def _eightfold_parts(board: str) -> tuple[str, str]:
    """``apply.careers.acme.com/acme.com`` → (host, domain)."""
    host, _, domain = board.strip().strip("/").partition("/")
    if not host or not domain:
        raise ValueError(f"eightfold board must be '<careers host>/<domain>', got {board!r}")
    return host, domain


class EightfoldScraper(AtsScraper):
    """An Eightfold careers site. Board token: ``<careers host>/<company domain>``."""

    source = "eightfold"
    needs_detail = True
    pages_per_board = 5
    accept = "application/json"

    def warmup(self, board: str) -> None:
        # The API answers 429 without the session cookie the careers page sets;
        # HttpFetcher keeps cookies for the run, as a browser would.
        host, _ = _eightfold_parts(board)
        self._fetch(f"https://{host}/careers")

    def board_page_url(self, board: str, query: str, page: int) -> str:
        if page > self.pages_per_board:
            return ""
        host, domain = _eightfold_parts(board)
        params = {
            "domain": domain,
            "query": "",
            "location": _search_place(self.locations),
            "start": (page - 1) * EIGHTFOLD_PAGE,
        }
        return f"https://{host}/api/pcsx/search?{urlencode(params)}"

    def places(self, hit: SearchHit) -> list[str]:
        return list(hit.extra.get("places") or [])

    def parse_search(self, text: str) -> list[SearchHit]:
        data = load_json(text)
        body = (data or {}).get("data") if isinstance(data, dict) else None
        if not isinstance(body, dict) or "positions" not in body:
            raise ValueError("expected an Eightfold search response with data.positions")
        host, domain = _eightfold_parts(self._board) if self._board else ("", "")
        hits: list[SearchHit] = []
        for job in body.get("positions") or []:
            pid = clean_text(str(job.get("id") or ""))
            title = clean_text(str(job.get("name") or ""))
            if not pid or not title:
                continue
            places = [clean_text(str(p)) for p in job.get("locations") or [] if p]
            hits.append(
                SearchHit(
                    native_id=pid,
                    url=f"https://{host}/careers/job/{quote(pid)}",
                    title=title[:200],
                    company=domain.split(".")[0].title(),
                    location=places[0] if places else None,
                    posted_raw=clean_text(str(job.get("postedTs") or "")) or None,
                    extra={
                        "places": places,
                        "tags": [clean_text(str(job.get("department") or ""))],
                        "work_mode": _remote_word(str(job.get("workLocationOption") or "")),
                        "api": (
                            f"https://{host}/api/pcsx/position_details?"
                            + urlencode({"position_id": pid, "domain": domain, "hl": "en"})
                        ),
                    },
                )
            )
        return hits

    def detail_url(self, hit: SearchHit) -> str:
        return str(hit.extra.get("api") or hit.url)

    @staticmethod
    def _board_of(hit: SearchHit) -> str:
        """``host/domain`` again, from the detail API URL the hit carries."""
        from urllib.parse import parse_qs

        api = urlsplit(str(hit.extra.get("api") or ""))
        domain = (parse_qs(api.query).get("domain") or [""])[0]
        return f"{api.netloc}/{domain}" if api.netloc and domain else "x/"

    def parse_detail(self, text: str, hit: SearchHit) -> RawJob:
        data = load_json(text)
        info = (data or {}).get("data") if isinstance(data, dict) else None
        if not isinstance(info, dict):
            raise ValueError("Eightfold position without data")
        return RawJob(
            source=self.source,
            native_id=hit.native_id,
            url=clean_text(str(info.get("publicUrl") or "")) or hit.url,
            title=clean_text(str(info.get("name") or "")) or hit.title,
            company=hit.company,
            location=self.location_of(hit),
            posted_raw=hit.posted_raw,
            skills=[t for t in hit.extra.get("tags") or [] if t],
            description_html=str(info.get("jobDescription") or ""),
            apply_channel="external",
            apply_target=clean_text(str(info.get("publicUrl") or "")) or hit.url,
            extra={
                "ats": "eightfold",
                "company_domain": _eightfold_parts(self._board_of(hit))[1],
                "work_mode_stated": _remote_word(str(info.get("workLocationOption") or ""))
                or hit.extra.get("work_mode"),
            },
        )


# --------------------------------------------------------------------------- #
# Google Careers
# --------------------------------------------------------------------------- #
GOOGLE_RESULTS = "https://www.google.com/about/careers/applications/jobs/results"
_DS1 = re.compile(r"AF_initDataCallback\(\{key: 'ds:1'.*?data:(.*?), sideChannel: \{\}\}\);", re.S)


class GoogleCareersScraper(AtsScraper):
    """Google's own careers site. Board token: ``google`` (there is one board)."""

    source = "googlecareers"
    #: robots.txt disallows ``results?page=`` and ``results?*&page=`` — only the
    #: first page of any search may be read. So the search is narrowed instead:
    #: the crawl's query goes in ``q=``, and its first 20 results are the ones
    #: worth having. Do not raise this; the robots check would refuse page 2.
    pages_per_board = 1

    def board_page_url(self, board: str, query: str, page: int) -> str:
        if page > 1:
            return ""
        params = {}
        if query.strip():
            params["q"] = query.strip()
        if self.locations:
            params["location"] = _search_place(self.locations)
        return f"{GOOGLE_RESULTS}?{urlencode(params)}" if params else GOOGLE_RESULTS

    def places(self, hit: SearchHit) -> list[str]:
        return list(hit.extra.get("places") or [])

    def parse_search(self, text: str) -> list[SearchHit]:
        match = _DS1.search(text)
        if not match:
            raise ValueError("Google Careers page without the ds:1 data block")
        data = json.loads(match.group(1))
        if not (isinstance(data, list) and data and isinstance(data[0], list | type(None))):
            raise ValueError("Google Careers ds:1 is not the expected [jobs, …] list")
        hits: list[SearchHit] = []
        for job in data[0] or []:
            hit = _google_hit(job)
            if hit is not None:
                hits.append(hit)
        if data[0] and not hits:
            # Rows were there and none could be read: the layout moved. Raised so
            # the crawl reports a broken parser rather than an empty board.
            raise ValueError("Google Careers rows present but none matched the known layout")
        return hits

    def parse_detail(self, text: str, hit: SearchHit) -> RawJob:
        parts = hit.extra.get("parts") or []
        return RawJob(
            source=self.source,
            native_id=hit.native_id,
            url=hit.url,
            title=hit.title,
            company=hit.company,
            location=self.location_of(hit),
            posted_raw=hit.posted_raw,
            description_html="".join(f"<div>{p}</div>" for p in parts if p),
            apply_channel="external",
            apply_target=hit.url,
            extra={"ats": "googlecareers", "company_domain": "google.com"},
        )


def _rich(value) -> str:
    """``[null, "<ul>…</ul>"]`` → the HTML string, else ""."""
    if isinstance(value, list) and len(value) > 1 and isinstance(value[1], str):
        return value[1]
    return ""


def _google_hit(job) -> SearchHit | None:
    """One row of ds:1, read by position (the layout seen 2026-10-14).

    0 id · 1 title · 3 responsibilities · 4 qualifications · 7 company ·
    9 locations ([label, …]) · 10 about the job · 12 [published epoch, nanos] ·
    19 more qualifications. Anything else in the row is ignored.
    """
    if not isinstance(job, list) or len(job) < 13:
        return None
    jid, title = job[0], job[1]
    if not isinstance(jid, str) or not jid.isdigit() or not isinstance(title, str):
        return None
    places = [
        clean_text(loc[0])
        for loc in (job[9] or [])
        if isinstance(loc, list) and loc and isinstance(loc[0], str)
    ]
    published = job[12][0] if isinstance(job[12], list) and job[12] else None
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return SearchHit(
        native_id=jid,
        url=f"{GOOGLE_RESULTS}/{jid}-{slug}",
        title=clean_text(title)[:200],
        company=clean_text(job[7]) if isinstance(job[7], str) else "Google",
        location=places[0] if places else None,
        posted_raw=str(published) if isinstance(published, int) else None,
        extra={
            "places": places,
            "tags": [],
            "parts": [
                _rich(job[10]),
                _rich(job[3]),
                _rich(job[4]),
                _rich(job[19]) if len(job) > 19 else "",
            ],
        },
    )
