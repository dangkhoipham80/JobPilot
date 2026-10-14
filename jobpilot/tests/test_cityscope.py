"""``crawl.city`` — holding ITviec, TopCV and VietnamWorks to one city.

Two things are pinned here, and the second is the one that matters on the day a
board changes. The URL each board is asked with, in that board's own form. And
the check on what comes back: a city parameter a site stops honouring is not
rejected, it is ignored, and the search answers 200 with the whole country — so
a card that names another city is left out whatever the URL did.
"""

from __future__ import annotations

import logging

import pytest

from jobpilot.config import Config, CrawlCfg, SourceCfg
from jobpilot.crawler.cityscope import CityScopedScraper
from jobpilot.crawler.itviec import ITViecScraper
from jobpilot.crawler.ratelimit import RateLimiter
from jobpilot.crawler.topcv import TopCVScraper
from jobpilot.crawler.types import RawJob, SearchHit
from jobpilot.crawler.vietnam import is_elsewhere, named_cities, scope_city
from jobpilot.crawler.vietnamworks import VietnamWorksScraper

HCM, HANOI, DANANG = "Hồ Chí Minh", "Hà Nội", "Đà Nẵng"


# --------------------------------------------------------------------------- #
# reading the setting and the card label
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("text", "city"),
    [
        ("Ho Chi Minh", HCM),
        ("hcm", HCM),
        ("Saigon", HCM),
        ("TP. Hồ Chí Minh", HCM),
        ("Hanoi", HANOI),
        ("da nang", DANANG),
        # not one city
        ("", None),
        (None, None),
        ("Remote", None),  # in the city table because boards print it; not a city
        ("Vietnam", None),
        ("Ho Chi Minh, Ha Noi", None),  # the setting is one city
        ("Atlantis", None),
    ],
)
def test_scope_city(text, city):
    assert scope_city(text) == city


@pytest.mark.parametrize(
    ("label", "cities"),
    [
        ("Hồ Chí Minh", {HCM}),
        ("Ho Chi Minh - Ha Noi", {HCM, HANOI}),  # ITviec
        ("Hà Nội & Ninh Bình", {HANOI, "Ninh Bình"}),  # TopCV
        ("Hà Nội, Hồ Chí Minh", {HANOI, HCM}),  # VietnamWorks
        ("Khánh Hòa (mới) & Hồ Chí Minh", {"Khánh Hòa", HCM}),
        ("Ho Chi Minh City, Vietnam", {HCM}),  # the country is decoration
        ("Remote", {"Remote"}),
        # Unknown, not "the part that could be read": two more places it does
        # not name, a country that is not in the table, nothing at all.
        ("Hà Nội & 2 nơi khác", None),
        ("Hà Nội +2", None),
        ("Hà Nội …", None),
        ("Nhật Bản", None),
        ("", None),
        (None, None),
    ],
)
def test_named_cities(label, cities):
    assert named_cities(label) == (frozenset(cities) if cities else None)


@pytest.mark.parametrize(
    ("label", "elsewhere"),
    [
        ("Hà Nội", True),
        ("Hà Nội & Ninh Bình", True),
        ("Hồ Chí Minh", False),
        ("Hà Nội, Hồ Chí Minh", False),
        # Every doubt keeps the posting.
        (None, False),
        ("Hà Nội & 2 nơi khác", False),  # one of the two may be ours
        ("Remote", False),  # can be done from the city searched
        ("Nhật Bản", False),
    ],
)
def test_is_elsewhere_only_when_the_label_is_known_to_name_other_cities(label, elsewhere):
    assert is_elsewhere(label, HCM) is elsewhere


# --------------------------------------------------------------------------- #
# the URL, in each board's own form
# --------------------------------------------------------------------------- #
def test_no_city_leaves_every_search_url_as_it_was():
    assert ITViecScraper().search_url("ai engineer") == "https://itviec.com/it-jobs?query=ai+engineer"
    assert ITViecScraper(city="").search_url("java", 2) == "https://itviec.com/it-jobs?query=java&page=2"
    assert TopCVScraper(city=None).search_url("java") == "https://www.topcv.vn/tim-viec-lam-java"
    assert VietnamWorksScraper(city="  ").search_url("java") == (
        "https://www.vietnamworks.com/viec-lam?q=java"
    )


def test_itviec_scopes_through_the_path_form_because_that_is_the_one_that_pages():
    """ITviec's search box submits ``?query=…&city=…``, and that is honoured —
    for page 1. With ``&page=2`` it answered page 1 again, 20 ids of 20. The
    form its own pagination links use is the path, and that one pages."""
    s = ITViecScraper(city="hcm")
    assert s.search_url("AI  Engineer") == "https://itviec.com/it-jobs/ai-engineer/ho-chi-minh-hcm"
    assert s.search_url("ai engineer", 2) == (
        "https://itviec.com/it-jobs/ai-engineer/ho-chi-minh-hcm?page=2"
    )
    assert ITViecScraper(city="Hanoi").search_url("java") == "https://itviec.com/it-jobs/java/ha-noi"
    assert ITViecScraper(city="Da Nang").search_url("java") == "https://itviec.com/it-jobs/java/da-nang"


@pytest.mark.parametrize("query", ["c++", ".net", "node.js", "lập trình viên", "c#"])
def test_itviec_does_not_make_up_a_slug_for_a_query_that_is_not_plain_words(query):
    """Only "words, with spaces as hyphens" was checked against the site. Any
    other query keeps the search-box form, which is honoured for page 1 only —
    so every page answers with the same URL, the way a source says it has no
    page two, rather than with a ``&page=2`` that is quietly ignored."""
    s = ITViecScraper(city="hcm")
    first = s.search_url(query)
    assert first.startswith("https://itviec.com/it-jobs?query=")
    assert first.endswith("&city=ho-chi-minh-hcm")
    assert s.search_url(query, 2) == first


def test_topcv_puts_the_city_in_the_path_after_the_keyword():
    s = TopCVScraper(city="Ho Chi Minh")
    assert s.search_url("AI Engineer") == (
        "https://www.topcv.vn/tim-viec-lam-ai-engineer-tai-ho-chi-minh-kl2"
    )
    assert s.search_url("java", 2) == "https://www.topcv.vn/tim-viec-lam-java-tai-ho-chi-minh-kl2?page=2"
    assert TopCVScraper(city="Ha Noi").search_url("java").endswith("-tai-ha-noi-kl1")
    assert TopCVScraper(city="Đà Nẵng").search_url("java").endswith("-tai-da-nang-kl8")


def test_vietnamworks_passes_its_numeric_location_id():
    s = VietnamWorksScraper(city="Saigon")
    assert s.search_url("ai engineer") == "https://www.vietnamworks.com/viec-lam?q=ai+engineer&l=29"
    assert s.search_url("java", 3) == "https://www.vietnamworks.com/viec-lam?q=java&l=29&page=3"
    assert VietnamWorksScraper(city="Hanoi").search_url("java").endswith("&l=24")
    assert VietnamWorksScraper(city="Da Nang").search_url("java").endswith("&l=17")


@pytest.mark.parametrize("cls", [ITViecScraper, TopCVScraper, VietnamWorksScraper])
def test_a_city_the_board_has_no_url_form_for_is_searched_unscoped_and_said_so(cls, caplog):
    """Never a token made up by analogy with the three that were checked: a
    wrong one is either a 404 or, worse, some other listing answered with 200."""
    with caplog.at_level(logging.WARNING):
        s = cls(city="Can Tho")
    assert s.city == "Cần Thơ" and s.city_token is None
    assert s.search_url("java") == cls().search_url("java")
    assert any("no known search URL for Cần Thơ" in r.getMessage() for r in caplog.records)


def test_a_setting_that_is_not_a_city_scopes_nothing_and_says_so(caplog):
    with caplog.at_level(logging.WARNING):
        s = TopCVScraper(city="Atlantis")
    assert s.city is None and s.city_token is None
    assert any("not a Vietnamese city" in r.getMessage() for r in caplog.records)


# --------------------------------------------------------------------------- #
# the cards, whatever the URL did
# --------------------------------------------------------------------------- #
ITVIEC_PAGE = """
<div class="card-jobs-list">
  <div class="job-card" data-search--job-selection-job-slug-value="backend-example-works-201">
    <h3>Backend Engineer</h3><a href="/companies/example-works">Example Works</a>
    <div class="text-rich-grey">Da Nang - Ha Noi</div>
  </div>
  <div class="job-card" data-search--job-selection-job-slug-value="data-sample-foods-202">
    <h3>Data Engineer</h3><a href="/companies/sample-foods">Sample Foods</a>
    <div class="text-rich-grey">Ho Chi Minh - Ha Noi</div>
  </div>
  <div class="job-card" data-search--job-selection-job-slug-value="qa-example-works-203">
    <h3>QA Engineer</h3><a href="/companies/example-works">Example Works</a>
    <div class="text-rich-grey">Ha Noi</div>
  </div>
  <div class="job-card" data-search--job-selection-job-slug-value="ops-sample-foods-204">
    <h3>Platform Engineer</h3><a href="/companies/sample-foods">Sample Foods</a>
  </div>
</div>
"""


def test_itviecs_own_parser_lets_the_scope_see_a_card_that_lists_two_cities():
    """Through the real `parse_search`, not a stand-in board. ITviec's location
    finder knows one city per label and stores nothing for "Da Nang - Ha Noi" —
    so the card that most plainly says "not here" was the one the scope could
    not read, and the day the site ignored the city in the URL it was kept."""
    scraper = ITViecScraper(
        city="hcm", rate_limiter=RateLimiter(0, 0), fetcher=lambda url: ITVIEC_PAGE, max_pages=1
    )
    by_id = {h.native_id: h for h in scraper.parse_search(ITVIEC_PAGE)}
    # What is stored is unchanged: one city or nothing.
    assert by_id["backend-example-works-201"].location is None
    assert by_id["backend-example-works-201"].extra["place_label"] == "Da Nang - Ha Noi"
    assert by_id["qa-example-works-203"].extra["place_label"] is None

    kept = [h.native_id for h in scraper.search("engineer", limit=10)]
    # Two cities, one of them ours: kept. No label at all: kept.
    assert kept == ["data-sample-foods-202", "ops-sample-foods-204"]


def test_a_page_of_other_cities_is_not_reported_as_a_broken_parser(caplog):
    """Every card read, none wanted. "The selectors no longer match" would send
    whoever reads the log to fix a parser that just did its job."""
    board = Board([("1", "Hà Nội"), ("2", "Đà Nẵng")], city="hcm")
    with caplog.at_level(logging.WARNING, logger="jobpilot.crawler.base"):
        assert board.crawl("engineer", limit=5) == []
    assert "selectors no longer match" not in caplog.text
    assert board.left_out == 2

    # ...and an empty page still is.
    empty = Board([], city="hcm")
    with caplog.at_level(logging.WARNING, logger="jobpilot.crawler.base"):
        empty.crawl("engineer", limit=5)
    assert "selectors no longer match" in caplog.text


class Board(CityScopedScraper):
    """A board that answers with the given (id, location) cards, one page."""

    source = "board"
    city_tokens = {HCM: "hcm-token"}

    def __init__(self, cards: list[tuple[str, str | None]], **kw):
        kw.setdefault("rate_limiter", RateLimiter(0, 0))
        super().__init__(**kw)
        self.cards = cards
        self.fetcher = lambda url: url

    def search_url(self, query: str, page: int = 1) -> str:
        return f"https://board.test/jobs?city={self.city_token or ''}"

    def parse_search(self, text: str) -> list[SearchHit]:
        return [
            SearchHit(native_id=i, url=f"https://board.test/j/{i}", title="Engineer", location=loc)
            for i, loc in self.cards
        ]

    def parse_detail(self, text: str, hit: SearchHit) -> RawJob:
        return RawJob(source=self.source, native_id=hit.native_id, url=hit.url, location=hit.location)


def test_a_card_that_names_another_city_is_left_out_before_the_limit():
    """Without this the scope is only as good as the URL, and a URL parameter
    fails silently. The limit goes to postings in the city either way."""
    cards = [("1", "Hà Nội"), ("2", "Hà Nội & Ninh Bình"), ("3", "Hồ Chí Minh"), ("4", "Ho Chi Minh - Ha Noi")]
    jobs = Board(cards, city="hcm").crawl("engineer", limit=2)
    assert [j.native_id for j in jobs] == ["3", "4"]


def test_a_card_that_does_not_say_where_it_is_stays():
    """No label, "… & 2 nơi khác", a country the table does not know, Remote:
    not knowing a posting is in the city is not knowing it is somewhere else."""
    cards = [("1", None), ("2", "Hà Nội & 2 nơi khác"), ("3", "Nhật Bản"), ("4", "Remote"), ("5", "Đà Nẵng")]
    hits = Board(cards, city="hcm").search("engineer", limit=10)
    assert [h.native_id for h in hits] == ["1", "2", "3", "4"]


def test_no_city_keeps_every_card():
    cards = [("1", "Hà Nội"), ("2", "Hồ Chí Minh")]
    assert len(Board(cards).search("engineer", limit=10)) == 2


def test_a_scoped_search_that_comes_back_nationwide_is_called_out(caplog):
    """The board was asked for one city and most of its cards name another:
    the site is ignoring the parameter. The hits kept are still right — the
    cards were checked — but the limit was spent nationwide, and that must not
    pass as a normal crawl."""
    cards = [("1", "Hà Nội"), ("2", "Hà Nội"), ("3", "Đà Nẵng"), ("4", "Hồ Chí Minh")]
    with caplog.at_level(logging.INFO):
        hits = Board(cards, city="hcm").search("engineer", limit=10)

    assert [h.native_id for h in hits] == ["4"]
    warned = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("3 of 4 card(s)" in r.getMessage() and "ignoring the city" in r.getMessage() for r in warned)


@pytest.mark.parametrize(
    ("in_city", "strays"),
    [
        (3, 1),  # a quarter of a tiny page, but one card is one card
        (38, 2),  # two cards, but one in twenty
    ],
)
def test_a_stray_card_from_another_city_is_noted_not_alarmed(in_city, strays, caplog):
    """An odd card or two on an honest page is not evidence of an ignored
    parameter. Both halves of the threshold are needed: a share alone alarms on
    a four-card page, a count alone alarms on any long one."""
    cards = [(str(i), "Hồ Chí Minh") for i in range(in_city)]
    cards += [(f"x{i}", "Hà Nội") for i in range(strays)]
    with caplog.at_level(logging.INFO):
        hits = Board(cards, city="hcm").search("engineer", limit=100)

    assert len(hits) == in_city
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    said = f"{strays} of {in_city + strays} card(s) name another city"
    assert any(said in r.getMessage() for r in caplog.records)


def test_without_a_url_form_other_cities_are_expected_and_not_an_alarm(caplog):
    """The board was searched nationwide on purpose (no token for this city),
    so cards from elsewhere are what was asked for, not a broken parameter.
    They are still left out."""
    cards = [("1", "Hà Nội"), ("2", "Hà Nội"), ("3", "Cần Thơ")]
    board = Board(cards, city="Can Tho")
    with caplog.at_level(logging.INFO):
        hits = board.search("engineer", limit=10)

    assert [h.native_id for h in hits] == ["3"]
    assert not any("ignoring the city" in r.getMessage() for r in caplog.records)


# --------------------------------------------------------------------------- #
# config -> registry -> scraper
# --------------------------------------------------------------------------- #
def test_the_configured_city_reaches_the_three_boards_and_nothing_else():
    from jobpilot.crawler.registry import SCRAPERS, build_scrapers

    cfg = Config(
        crawl=CrawlCfg(city="Ho Chi Minh"),
        sources=[SourceCfg(key=key, enabled=True) for key in SCRAPERS],
    )
    built = {s.source: s for s in build_scrapers(cfg, respect_robots=False)}
    assert {k for k, s in built.items() if getattr(s, "city", None) == HCM} == {
        "itviec",
        "topcv",
        "vietnamworks",
    }
    assert built["itviec"].city_token == "ho-chi-minh-hcm"


def test_an_empty_city_is_the_default_and_scopes_nothing():
    from jobpilot.crawler.registry import build_scrapers

    cfg = Config(sources=[SourceCfg(key="topcv", enabled=True)])
    assert cfg.crawl.city == ""
    (topcv,) = build_scrapers(cfg, respect_robots=False)
    assert topcv.city is None


@pytest.mark.parametrize("city", ["Atlantis", "Remote", "Vietnam", "Ho Chi Minh, Ha Noi"])
def test_a_city_the_crawler_cannot_read_is_refused_when_it_is_saved(city):
    """Not at 08:30, as a log line under a crawl that went nationwide anyway."""
    with pytest.raises(ValueError, match="not a Vietnamese city"):
        CrawlCfg(city=city)


@pytest.mark.parametrize("city", ["", "  ", "hcm", "Hà Nội", "Can Tho"])
def test_a_city_the_crawler_can_read_is_accepted_as_typed(city):
    assert CrawlCfg(city=city).city == city.strip()
