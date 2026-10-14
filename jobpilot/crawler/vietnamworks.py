"""VietnamWorks scraper (PLAN §5.1 — tier-1 source).

A Next.js app, but not the way the original scaffold assumed: ``__NEXT_DATA__``
holds only the filter dropdowns, so the job list is **not** in the server
response. Jobs arrive from an XHR after hydration, which means the search page
must be fetched with the Playwright fetcher (a plain HTTP GET returns an empty
list) and read from the rendered DOM.

Two deliberate choices:

* **DOM, not the internal API.** The rendered page comes from
  ``www.vietnamworks.com``, whose ``robots.txt`` allows ``/viec-lam`` and the
  job pages. The XHR behind it (``ms.vietnamworks.com/job-search/v1.0/search``)
  is an undocumented internal endpoint on a host that serves no robots.txt at
  all; scraping the user-facing page keeps us on documented ground (principle 5)
  and keeps ``parse_search`` a pure HTML function.
* **Content-based selectors.** Every styling class here is a build hash
  (``sc-1671001a-5 cjuZti``), so class selectors would break on the next deploy.
  Cards are found by the semantic wrapper VietnamWorks keeps for its own
  analytics (``.new-job-card``/``.view_job_item``), fields by value
  (:mod:`jobpilot.crawler.vietnam`), and detail pages by their schema.org
  ``JobPosting`` block (:mod:`jobpilot.crawler.jsonld`).

``robots.txt`` disallows every apply route (``/jobs/apply-job-online/``,
``/viec-lam/nop-ho-so-truc-tuyen/``), so those are never fetched:
``apply_channel`` is ``portal`` and the user submits (principle 2).
"""

from __future__ import annotations

import re
from urllib.parse import quote_plus, urlsplit

from bs4 import BeautifulSoup, NavigableString
from bs4.element import Tag

from jobpilot.crawler.cityscope import CityScopedScraper
from jobpilot.crawler.jsonld import parse_job_posting
from jobpilot.crawler.text import clean_text, el_text, first_match, leaf_texts, strip_query
from jobpilot.crawler.types import RawJob, SearchHit
from jobpilot.crawler.vietnam import clean_city, find_city, find_posted, find_salary, is_noise

BASE_URL = "https://www.vietnamworks.com"

# Wrappers VietnamWorks keeps for its own GTM/analytics hooks. Unlike the
# `sc-*` styling classes these are named for what they are, so they survive
# restyles — and if they ever go, the `<a href="…-jv">` fallback still finds jobs.
CARD_SELECTOR = ".new-job-card, .view_job_item, .search_list"

# The block VietnamWorks renders *instead of* results — "Hiện chưa có công việc
# nào theo tiêu chí bạn tìm" — and fills with twenty suggestions "you might
# like". They are job cards in every respect except the one that matters: they
# did not match the search. Asking for the page after the last one lands here.
NO_RESULT_SELECTOR = ".noResultBlock, .wrapper-no-job"

# Job URLs end `-<id>-jv`, e.g. /solution-architect-finance-2077038-jv
_JV_ID_RE = re.compile(r"-(\d+)-jv(?:[/?#]|$)")

# JD section headings, used to find the body without touching a hashed class.
_JD_HEADINGS = re.compile(
    r"(mô tả công việc|yêu cầu công việc|yêu cầu ứng viên|phúc lợi"
    r"|job description|job requirement)",
    re.I,
)


def _card_title(anchor: Tag) -> str:
    """Title without the "Mới" badge that lives inside the same anchor.

    The markup is ``<a data-new-job="Mới"><span>Mới</span>Solution Architect</a>``,
    so the anchor's text reads "Mới Solution Architect".

    The title is assembled from the anchor's children with the badge dropped,
    rather than from its bare text nodes only. Taking just the text nodes works
    on today's markup but returns nothing the moment the title is wrapped in an
    element (``<strong>Senior Backend Developer</strong>``), and the fallback
    would then hand back the badge-prefixed text — every job titled "Mới …".
    """
    parts: list[str] = []
    for child in anchor.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag):
            text = el_text(child)
            if text and not is_noise(text):
                parts.append(text)
    title = clean_text(" ".join(parts))
    if title:
        return title
    # Last resort: the logo link mirrors the title in its `title` attribute.
    return clean_text(str(anchor.get("title") or ""))


def _leaves(root: Tag, max_len: int = 80) -> list[str]:
    """Card labels with the chrome removed.

    Dropping noise here is what keeps "Rất đông ứng viên" ("lots of applicants")
    and "+3" out of ``location``/``salary``; LinkedIn's "34 company alumni"
    landing in a location field was the same bug (CLAUDE.md).
    """
    return [t for t in leaf_texts(root, max_len=max_len) if not is_noise(t)]


class VietnamWorksScraper(CityScopedScraper):
    source = "vietnamworks"

    #: VietnamWorks' numeric location ids, the ``l`` parameter of its search.
    city_tokens = {
        "Hồ Chí Minh": "29",
        "Hà Nội": "24",
        "Đà Nẵng": "17",
    }

    def search_url(self, query: str, page: int = 1) -> str:
        """``/viec-lam?q=…&page=N``.

        Paging is the answer to this site's lazy loading, not a bonus: one fetch
        renders only ~9 cards and the rest are skeletons awaiting a scroll,
        so ``jobs_per_site`` above that used to come back short with a warning.
        Asking for the next page keeps ``PlaywrightFetcher`` a plain
        ``(url) -> html`` function, which scrolling inside it would not.

        What paging does not do is reach the cards a page left as skeletons:
        ``page=2`` is the *next* page of results, and for a search with no next
        page it is the no-result block ``parse_search`` now ignores.

        A city is the site's numeric location id, ``&l=<id>``.
        """
        url = f"{BASE_URL}/viec-lam?q={quote_plus(query or 'java')}"
        if self.city_token:
            url += f"&l={self.city_token}"
        return url if page <= 1 else f"{url}&page={page}"

    def _native_id(self, url: str) -> str:
        m = _JV_ID_RE.search(url)
        return m.group(1) if m else urlsplit(url).path.strip("/") or url

    def parse_search(self, html: str) -> list[SearchHit]:
        """Read the result cards — and only the result cards.

        A page past the end of the results is not empty: it says no job matches
        and then lists twenty suggestions, unrelated to the query and from any
        city. Read as hits they made a search look twenty jobs deeper than it
        was, and under a city scope they were most of what page 2 returned —
        for the wrong cities (measured: the same twenty ids as page 1 of a
        search with no results at all, in another city). Dropping the
        block makes that page what it is, empty, which is how the walk in
        ``BaseScraper.search`` knows the results have ended.
        """
        soup = BeautifulSoup(html, "html.parser")
        for block in soup.select(NO_RESULT_SELECTOR):
            block.decompose()
        hits: list[SearchHit] = []
        seen: set[str] = set()

        for card in soup.select(CARD_SELECTOR):
            anchor = first_match(card, 'h2 a[href*="-jv"]', 'h3 a[href*="-jv"]', 'a[href*="-jv"]')
            if anchor is None:
                continue
            href = clean_text(str(anchor.get("href") or ""))
            if not href:
                continue
            url = strip_query(href if href.startswith("http") else f"{BASE_URL}{href}")
            native_id = self._native_id(url)
            if not native_id or native_id in seen:
                continue
            seen.add(native_id)

            leaves = _leaves(card)
            hits.append(
                SearchHit(
                    native_id=native_id,
                    url=url,
                    title=_card_title(anchor)[:200],
                    company=self._card_company(card),
                    location=find_city(leaves),
                    salary=find_salary(leaves),
                    posted_raw=find_posted(leaves),
                )
            )
        return hits

    @staticmethod
    def _card_company(card: Tag) -> str:
        """Employer name from its profile link (``/nha-tuyen-dung/<slug>``)."""
        for link in card.select('a[href*="/nha-tuyen-dung/"], a[href*="/company/"]'):
            name = el_text(link) or clean_text(str(link.get("title") or ""))
            if name and not is_noise(name):
                return name
        return ""

    def parse_detail(self, html: str, hit: SearchHit) -> RawJob:
        """JSON-LD for the facts, DOM for the full JD.

        The ``JobPosting`` block is authoritative for title/company/salary/date,
        but its ``description`` is only the responsibilities — VietnamWorks keeps
        "Yêu cầu công việc" out of it. Tailoring against responsibilities alone
        would miss the requirements the CV has to answer, so the DOM sections win
        when they are richer.
        """
        soup = BeautifulSoup(html, "html.parser")
        posting = parse_job_posting(html)

        title = (posting.title if posting else "") or el_text(soup.select_one("h1")) or hit.title
        company = (posting.company if posting else "") or hit.company or self._card_company(soup)
        location = clean_city(posting.location if posting else None) or hit.location

        dom_jd = self._jd_html(soup)
        ld_jd = posting.description_html if posting else ""
        description_html = dom_jd if len(dom_jd) > len(ld_jd) else ld_jd

        return RawJob(
            source=self.source,
            native_id=hit.native_id,
            url=hit.url,
            title=title,
            company=company,
            location=location,
            salary=(posting.salary if posting else None) or hit.salary,
            posted_raw=(posting.posted_raw if posting else None) or hit.posted_raw,
            skills=(posting.skills if posting else [])[:20],
            description_html=description_html,
            # Only RawJob.extra reaches the payload (`normalize` spreads it).
            extra=dict(hit.extra),
            # robots.txt disallows the apply endpoints → the user submits.
            apply_channel="portal",
            apply_target=hit.url,
        )

    @staticmethod
    def _jd_html(soup: BeautifulSoup) -> str:
        """Concatenate the JD blocks, located by their headings.

        Each section is a heading plus its body inside one wrapper, and the
        wrapper's class is a build hash. Matching the heading *text* and taking
        its parent gets the section without depending on that hash.
        """
        parts: list[str] = []
        for heading in soup.find_all(["h2", "h3"]):
            if not _JD_HEADINGS.search(el_text(heading)):
                continue
            block = heading.parent
            if block is None:
                continue
            chunk = str(block)
            if chunk not in parts:
                parts.append(chunk)
        return "".join(parts)
