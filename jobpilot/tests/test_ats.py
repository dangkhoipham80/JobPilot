"""ATS adapters (Greenhouse / Lever), pinned against trimmed real responses.

Both payloads carry a trap that a "does it parse?" test sails straight past:
Greenhouse double-encodes the description, and Lever dates in milliseconds while
never naming the employer at all.
"""

from __future__ import annotations

import json
import logging

import pytest

from jobpilot.crawler.ats import GreenhouseScraper, LeverScraper
from jobpilot.crawler.normalize import parse_posted_at
from jobpilot.crawler.ratelimit import RateLimiter
from jobpilot.crawler.text import html_to_markdown
from jobpilot.crawler.types import SearchHit

GREENHOUSE = json.dumps(
    {
        "meta": {"total": 2},
        "jobs": [
            {
                "id": 8503792002,
                "absolute_url": "https://job-boards.greenhouse.io/gitlab/jobs/8503792002",
                "title": "Backend Engineer (Ruby)",
                "company_name": "GitLab",
                "location": {"name": "Remote, Canada"},
                "first_published": "2026-07-08T05:58:03-04:00",
                "updated_at": "2026-07-30T08:48:22-04:00",
                "requisition_id": "6263",
                "departments": [{"name": "Engineering"}],
                "offices": [{"name": "Americas"}],
                "content": "&lt;p&gt;Build &amp;amp; ship Ruby services.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;5 years&lt;/li&gt;&lt;/ul&gt;",
            },
            {
                # No absolute_url → no link to hand back. Dropped, not guessed.
                "id": 9,
                "absolute_url": "",
                "title": "Ghost role",
                "company_name": "GitLab",
            },
        ],
    }
)

LEVER = json.dumps(
    [
        {
            "id": "ac978161-6f46-4f6b-ad9e-a258e642751c",
            "text": "Backend Software Engineer",
            "hostedUrl": "https://jobs.lever.co/palantir/ac978161-6f46-4f6b-ad9e-a258e642751c",
            "applyUrl": "https://jobs.lever.co/palantir/ac978161/apply",
            "createdAt": 1783000000000,
            "workplaceType": "hybrid",
            "categories": {
                "commitment": "Full-time",
                "location": "London, United Kingdom",
                "team": "Engineering",
            },
            "description": "<div>A World-Changing Company</div>",
            "lists": [{"text": "What We Value", "content": "<li>Java, Spring Boot</li>"}],
            "additional": "<div>Life at Palantir</div>",
        }
    ]
)


# --------------------------------------------------------------------------- #
# Greenhouse
# --------------------------------------------------------------------------- #
def test_greenhouse_reads_the_board():
    hits = GreenhouseScraper(boards=["gitlab"]).parse_search(GREENHOUSE)
    assert [h.native_id for h in hits] == ["8503792002"]
    assert hits[0].title == "Backend Engineer (Ruby)"
    assert hits[0].company == "GitLab"
    assert hits[0].location == "Remote, Canada"


def test_greenhouse_description_is_unescaped():
    """The API double-encodes: `content` arrives as "&lt;p&gt;…". Stored raw, the
    reader gets literal tags where the job description should be, and the tailor
    gets markup as prose."""
    s = GreenhouseScraper(boards=["gitlab"])
    job = s.parse_detail("", s.parse_search(GREENHOUSE)[0])
    assert "<p>" in job.description_html
    assert "&lt;" not in job.description_html
    # Exactly one level of unescaping: `&amp;` is the correct encoding of a
    # literal "&" *inside* the recovered HTML, so it must survive here and
    # resolve when the JD is turned into the markdown the tailor reads.
    assert "&amp;" in job.description_html
    assert "Build & ship Ruby services." in html_to_markdown(job.description_html)
    assert "- 5 years" in html_to_markdown(job.description_html)


def test_greenhouse_prefers_first_published_over_updated_at():
    """`updated_at` moves every time a recruiter fixes a typo, which would make a
    three-month-old req look posted today — and freshness drives the 🔥 flag."""
    hit = GreenhouseScraper(boards=["gitlab"]).parse_search(GREENHOUSE)[0]
    posted = parse_posted_at(hit.posted_raw)
    assert posted is not None
    assert (posted.month, posted.day) == (7, 8)  # first_published, not updated_at


def test_greenhouse_tags_come_from_departments_and_offices():
    s = GreenhouseScraper(boards=["gitlab"])
    job = s.parse_detail("", s.parse_search(GREENHOUSE)[0])
    assert job.skills == ["Engineering", "Americas"]
    assert job.apply_channel == "external"
    assert job.extra["ats"] == "greenhouse"


def test_greenhouse_board_url_asks_for_the_description():
    """Without `content=true` this becomes one request per job instead of one
    per company, which is the whole point of the adapter."""
    assert "content=true" in GreenhouseScraper().board_url("gitlab")


# --------------------------------------------------------------------------- #
# Lever
# --------------------------------------------------------------------------- #
def test_lever_reads_an_array_not_an_object():
    hits = LeverScraper(boards=["palantir"]).parse_search(LEVER)
    assert len(hits) == 1
    assert hits[0].title == "Backend Software Engineer"


def test_lever_company_comes_from_the_url():
    """Lever's payload never names the employer — only the board does, and the
    board slug is in every posting's hostedUrl."""
    assert LeverScraper(boards=["palantir"]).parse_search(LEVER)[0].company == "Palantir"


def test_lever_millisecond_timestamps_become_real_dates():
    """createdAt is milliseconds; the epoch guard accepts 9-11 digits so a stray
    13-digit number is not mistaken for a date. Convert at the source instead of
    loosening the guard for everyone."""
    hit = LeverScraper(boards=["palantir"]).parse_search(LEVER)[0]
    posted = parse_posted_at(hit.posted_raw)
    assert posted is not None
    assert posted.year == 2026


def test_lever_description_keeps_the_requirements():
    """Lever splits a posting across description / lists / additional. Keeping
    only `description` hands the tailor a company blurb with none of the
    requirements the CV has to answer."""
    s = LeverScraper(boards=["palantir"])
    job = s.parse_detail("", s.parse_search(LEVER)[0])
    assert "A World-Changing Company" in job.description_html
    assert "Java, Spring Boot" in job.description_html  # from `lists`
    assert "What We Value" in job.description_html
    assert "Life at Palantir" in job.description_html  # from `additional`


def test_lever_rejects_the_404_object():
    """A wrong or expired board token answers with an object, not an array. That
    must fail loudly — parsed leniently it would read as "this company has no
    open roles", and the board would stay silently dead."""
    with pytest.raises(ValueError, match="array"):
        LeverScraper(boards=["nope"]).parse_search('{"code":404}')


# --------------------------------------------------------------------------- #
# the shared board-per-page contract
# --------------------------------------------------------------------------- #
def test_each_configured_company_is_one_page():
    s = GreenhouseScraper(boards=["gitlab", "elastic"])
    assert "gitlab" in s.search_url("java", 1)
    assert "elastic" in s.search_url("java", 2)
    assert s.search_url("java", 3) == ""  # out of companies → the walk stops


def test_company_count_overrides_the_page_ceiling():
    """`crawl.max_pages` exists to stop us walking an unbounded board forever. A
    hand-written list of companies is already bounded by whoever wrote it."""
    s = LeverScraper(boards=["a", "b", "c", "d", "e", "f", "g"], max_pages=2)
    assert s.max_pages == 7


def test_no_companies_configured_says_so_plainly(caplog):
    """The generic zero-hits warning reads as "the parser broke" — a misleading
    thing to tell someone whose only mistake is an empty list."""
    fetched = []
    s = GreenhouseScraper(boards=[], fetcher=lambda u: fetched.append(u) or "{}")
    with caplog.at_level(logging.INFO):
        assert s.crawl("java", limit=5) == []
    assert fetched == []  # nothing was requested
    assert any("no company boards configured" in r.getMessage() for r in caplog.records)


def test_one_request_per_company_no_detail_fetches():
    fetched: list[str] = []

    def fetch(url: str) -> str:
        fetched.append(url)
        return GREENHOUSE

    jobs = GreenhouseScraper(boards=["gitlab"], fetcher=fetch).crawl("backend", limit=5)
    assert len(fetched) == 1
    assert len(jobs) == 1


# --------------------------------------------------------------------------- #
# location scope
# --------------------------------------------------------------------------- #
def _gh(*jobs: tuple[str, str, str | None]) -> str:
    """A Greenhouse board from (id, title, location) triples."""
    return json.dumps(
        {
            "jobs": [
                {
                    "id": jid,
                    "absolute_url": f"https://job-boards.greenhouse.io/x/jobs/{jid}",
                    "title": title,
                    "company_name": "X",
                    **({"location": {"name": loc}} if loc is not None else {}),
                    "content": "",
                }
                for jid, title, loc in jobs
            ]
        }
    )


@pytest.mark.parametrize(
    ("place", "term", "expected"),
    [
        # the term as whole words inside the label
        ("Ho Chi Minh City", "Ho Chi Minh", True),
        ("Ho Chi Minh City, Ho Chi Minh City, Vietnam", "Ho Chi Minh", True),
        ("Ho Chi Minh City, Ho Chi Minh City, Vietnam", "vietnam", True),
        ("Thành phố Hồ Chí Minh", "ho chi minh", True),
        # spellings that share no words — resolved through the city both name
        ("HCMC", "Ho Chi Minh", True),
        ("Saigon", "Hồ Chí Minh", True),
        ("Ha Noi, Vietnam", "Hanoi", True),
        # the country, spelled either way on either side
        ("Hồ Chí Minh, Việt Nam", "Vietnam", True),
        ("Ho Chi Minh City, Viet Nam", "vietnam", True),
        ("Ho Chi Minh City, Vietnam", "Việt Nam", True),
        # two-letter parts are country/state codes on a worldwide board, not
        # Vietnamese abbreviations: HN here is Honduras
        ("San Pedro Sula, HN", "Hanoi", False),
        ("Tegucigalpa, HN.", "Hanoi", False),
        ("Tegucigalpa, HN 11101", "Hanoi", False),
        ("San Pedro Sula, HN-21102", "Vietnam", False),
        # a label that is only a Vietnamese city is in Vietnam without saying so
        ("Ho Chi Minh City", "Vietnam", True),
        ("Da Nang", "Việt Nam", True),
        ("Nairobi", "Vietnam", False),
        ("Remote", "Vietnam", False),
        # one label naming two cities
        ("Hanoi & Ho Chi Minh", "Ha Noi", True),
        ("Hanoi or HCMC", "Saigon", True),
        ("Vietnamese Street, Sydney", "Vietnam", False),
        # elsewhere
        ("London, United Kingdom", "Ho Chi Minh", False),
        ("Ha Noi, Vietnam", "Ho Chi Minh", False),
        # whole words, not substrings: the `"remote" in "remote debugging"` trap
        ("Indianapolis, IN", "India", False),
        ("Parisot, France", "Paris", False),
        ("", "Ho Chi Minh", False),
        ("Ho Chi Minh City", "", False),
    ],
)
def test_place_matches(place, term, expected):
    from jobpilot.crawler.ats import place_matches

    assert place_matches(place, term) is expected


def test_a_location_scope_keeps_the_limit_for_postings_in_scope(caplog):
    """Checked against a real board where about one posting in twenty-five was
    in the city searched.

    Without a scope `limit` is spent on whichever offices the board lists first
    and the crawl still reports a full, successful page. The scope is applied
    before the limit is counted, so the one posting in scope is found even
    behind three that are not and a limit of one.
    """
    board = _gh(
        ("1", "Software Engineer", "Reykjavik, Iceland"),
        ("2", "Software Engineer", "Lima, Peru"),
        ("3", "Software Engineer", "Nairobi, Kenya"),
        ("4", "Software Engineer", "Ho Chi Minh City, Ho Chi Minh City, Vietnam"),
    )
    s = GreenhouseScraper(boards=["x"], locations=["Ho Chi Minh"], fetcher=lambda u: board)
    with caplog.at_level(logging.INFO):
        jobs = s.crawl("engineer", limit=1)

    assert [j.native_id for j in jobs] == ["4"]
    # Said out loud, so a board with nothing in scope does not read as a board
    # with no matching jobs.
    assert any("3 posting(s) outside ats.locations" in r.getMessage() for r in caplog.records)


def test_what_the_limit_cut_from_a_board_is_logged(caplog):
    """A board hands over its whole listing in one response, so the postings
    past `limit` are the same ones every crawl: cut again, never brought in.
    That has to be findable in the log rather than look like a full result."""
    board = _gh(*[(str(i), "Software Engineer", "Saigon") for i in range(5)])
    s = GreenhouseScraper(boards=["x"], locations=["Ho Chi Minh"], fetcher=lambda u: board)
    with caplog.at_level(logging.INFO):
        assert len(s.crawl("engineer", limit=2)) == 2
    assert any("3 matching hit(s)" in r.getMessage() and "cut by the limit of 2" in r.getMessage() for r in caplog.records)


def test_excluded_titles_do_not_take_a_scoped_boards_places():
    """A company board hands over one fixed listing, so what the limit cuts is
    cut on every crawl. With the excluded roles listed first, the limit used to
    be spent on them and the roles behind them were never brought in."""
    board = _gh(
        ("1", "Senior Software Engineer", "Saigon"),
        ("2", "Lead Software Engineer", "Saigon"),
        ("3", "Software Engineer", "Saigon"),
        ("4", "Software Engineer, Tools", "Saigon"),
        ("5", "Senior Software Engineer", "Lima, Peru"),
    )
    s = GreenhouseScraper(
        boards=["x"],
        locations=["Ho Chi Minh"],
        exclude_keywords=["Senior", "Lead"],
        fetcher=lambda u: board,
    )
    assert [j.native_id for j in s.crawl("software engineer", limit=2)] == ["3", "4"]
    # Out of scope is not "left out by title": each posting is counted once,
    # under the first rule that removed it.
    assert s.titles_dropped == 2


def test_no_location_scope_is_every_location():
    board = _gh(("1", "Software Engineer", "Lisbon"), ("2", "Software Engineer", "Saigon"))
    for locations in (None, [], ["  "]):
        s = GreenhouseScraper(boards=["x"], locations=locations, fetcher=lambda u: board)
        assert len(s.crawl("engineer", limit=5)) == 2


def test_a_posting_that_names_no_location_is_kept():
    """Unknown is not elsewhere. Dropping it would be a silent loss — the kind
    of thing the scope exists to stop, not to add."""
    board = _gh(("1", "Software Engineer", None), ("2", "Software Engineer", "Lima"))
    s = GreenhouseScraper(boards=["x"], locations=["Ho Chi Minh"], fetcher=lambda u: board)
    assert [j.native_id for j in s.crawl("engineer", limit=5)] == ["1"]


def test_lever_reads_every_office_a_posting_is_open_in():
    """Lever puts only the first office in `location`. A role listed under
    London that is also open in Ho Chi Minh City must not be filtered out of
    the city it is hiring in."""
    posting = json.loads(LEVER)[0]
    posting["categories"]["allLocations"] = ["London, United Kingdom", "Ho Chi Minh City"]
    board = json.dumps([posting])

    scoped = LeverScraper(boards=["palantir"], locations=["Ho Chi Minh"], fetcher=lambda u: board)
    assert len(scoped.crawl("engineer", limit=5)) == 1
    # ...and the unmodified fixture is London only.
    london = LeverScraper(boards=["palantir"], locations=["Ho Chi Minh"], fetcher=lambda u: LEVER)
    assert london.crawl("engineer", limit=5) == []


def test_lever_knows_the_country_its_label_leaves_out():
    """Checked against a real board: every local posting was labelled with the
    city alone and carried the country as `country: "VN"`. A scope of
    "Vietnam" — the example the config file itself gives — kept none of them."""
    posting = json.loads(LEVER)[0]
    posting["categories"]["location"] = "Ho Chi Minh City"
    posting["country"] = "VN"
    board = json.dumps([posting])

    for scope in (["Vietnam"], ["Việt Nam"]):
        (job,) = LeverScraper(boards=["x"], locations=scope, fetcher=lambda u: board).crawl("engineer", limit=5)
        # In scope because of the country — and still stored under its city.
        # The first fix stored the country here: every local posting came out
        # located in "Vietnam", with no city for any filter to find.
        assert job.location == "Ho Chi Minh City"
    # The fixture as shipped is London, GB — no code is added raw, so "GB"
    # (or "CA", "IN", "DE": words and states too) never becomes a place.
    gb = json.loads(LEVER)[0] | {"country": "GB"}
    assert LeverScraper(boards=["x"], locations=["GB"], fetcher=lambda u: json.dumps([gb])).crawl("engineer", limit=5) == []


def test_a_lever_posting_with_a_country_but_no_label_is_still_an_unknown_city():
    """ "A posting that names no location is always kept" has to hold for the
    posting the country hint applies to as well. Treating the hint as a label
    dropped a posting in Vietnam from a Vietnamese city's scope while keeping
    the same posting when its country was anywhere else."""
    for country in ("VN", "US", None):
        posting = json.loads(LEVER)[0]
        del posting["categories"]["location"]
        if country:
            posting["country"] = country
        board = json.dumps([posting])
        s = LeverScraper(boards=["x"], locations=["Ho Chi Minh"], fetcher=lambda u: board)
        (job,) = s.crawl("engineer", limit=5)
        assert job.location is None, country


def test_a_posting_kept_for_its_second_office_is_stored_under_that_office():
    """Kept because it is open in Ho Chi Minh City, then stored as
    "Nairobi", the job would be invisible to the city filter it was crawled
    for. The stored location is the label that put it in scope."""
    posting = json.loads(LEVER)[0]
    posting["categories"]["location"] = "Nairobi"
    posting["categories"]["allLocations"] = ["Nairobi", "Ho Chi Minh City"]
    board = json.dumps([posting])

    (job,) = LeverScraper(boards=["x"], locations=["Ho Chi Minh"], fetcher=lambda u: board).crawl("engineer", limit=5)
    assert job.location == "Ho Chi Minh City"
    # The same under a country scope: the city label is what matched, so it
    # is what is stored — the posting's own country code here is not Vietnam's.
    posting["country"] = "KE"
    by_country = json.dumps([posting])
    (job,) = LeverScraper(boards=["x"], locations=["Vietnam"], fetcher=lambda u: by_country).crawl("engineer", limit=5)
    assert job.location == "Ho Chi Minh City"
    # Unscoped, nothing is rewritten: the board's own first office stands.
    (job,) = LeverScraper(boards=["x"], fetcher=lambda u: board).crawl("engineer", limit=5)
    assert job.location == "Nairobi"


def test_a_board_with_nothing_in_scope_does_not_stop_the_next_board_being_read(caplog):
    """The scope is applied inside the walk over boards, not to its result.

    Applied afterwards, the first board's out-of-scope postings fill `limit`,
    the walk stops there, and the second company — the one with the local jobs
    — is never requested. And the count that is logged is per search, so a
    second keyword over the same boards reports the same number, not double.
    """
    elsewhere = _gh(*[(str(i), "Software Engineer", "Lisbon") for i in range(3)])
    local = _gh(("9", "Software Engineer", "Saigon"))
    pages = {"a": elsewhere, "b": local}
    asked: list[str] = []

    def fetch(url: str) -> str:
        board = url.split("/boards/")[1].split("/")[0]
        asked.append(board)
        return pages[board]

    s = GreenhouseScraper(
        boards=["a", "b"],
        locations=["Ho Chi Minh"],
        fetcher=fetch,
        rate_limiter=RateLimiter(0, 0),  # two requests: don't sleep between them in a test
    )
    with caplog.at_level(logging.INFO):
        first = s.crawl("engineer", limit=2)
        second = s.crawl("software", limit=2)

    assert asked == ["a", "b"], "both boards read once; the second keyword is served from memory"
    assert [j.native_id for j in first] == ["9"] == [j.native_id for j in second]
    counts = [r.getMessage() for r in caplog.records if "outside ats.locations" in r.getMessage()]
    assert len(counts) == 2 and all("3 posting(s)" in c for c in counts)


def test_the_configured_locations_reach_the_ats_scrapers_only():
    from jobpilot.config import AtsCfg, Config, SourceCfg
    from jobpilot.crawler.registry import build_scrapers

    cfg = Config(
        sources=[SourceCfg(key="lever", tier=3, enabled=True), SourceCfg(key="itviec", enabled=True)],
        ats=AtsCfg(lever=["acme"], locations=["Ho Chi Minh"]),
    )
    lever, itviec = sorted(build_scrapers(cfg, respect_robots=False), key=lambda s: s.source == "itviec")
    assert lever.locations == ("Ho Chi Minh",) and lever.boards == ("acme",)
    assert not hasattr(itviec, "locations")


def test_a_company_board_is_exempt_from_the_stack_gate_only_when_scoped():
    """A query matches any word of a title. Against a whole worldwide board
    "ai engineer" also matches every engineer the company employs who does not
    write software, and the gate is what removes them — one real board kept
    dozens of such postings at score 0 without it. Held to a place, the board is the
    user's own short list and the gate only removes what they asked for."""
    from jobpilot.crawler.itviec import ITViecScraper

    for cls in (GreenhouseScraper, LeverScraper):
        assert cls(boards=["x"], locations=["Ho Chi Minh"]).stack_gated is False
        assert cls(boards=["x"]).stack_gated is True
        assert cls(boards=["x"], locations=[]).stack_gated is True
    assert ITViecScraper.stack_gated is True


# --------------------------------------------------------------------------- #
# ranking
# --------------------------------------------------------------------------- #
def test_closest_match_comes_first():
    """Verified live: "backend engineer java" against a 184-job board matched 44
    postings, and `limit` kept "AI Engineer" plus four "Customer Success
    Engineer" roles — all on the word *engineer* alone. Filtering harder would
    drop good jobs; ordering costs nothing."""
    s = GreenhouseScraper(boards=["x"])
    hits = [
        SearchHit(native_id="1", url="u1", title="AI Engineer"),
        SearchHit(native_id="2", url="u2", title="Backend Engineer, Java Platform"),
        SearchHit(native_id="3", url="u3", title="Backend Engineer"),
    ]
    ranked = s.rank_hits(hits, "backend engineer java")
    assert [h.native_id for h in ranked] == ["2", "3", "1"]


def test_ranking_is_stable_and_a_no_op_without_a_query():
    s = GreenhouseScraper(boards=["x"])
    hits = [SearchHit(native_id=str(i), url="u", title="Engineer") for i in range(4)]
    assert [h.native_id for h in s.rank_hits(hits, "engineer")] == ["0", "1", "2", "3"]
    assert s.rank_hits(hits, "") == hits
