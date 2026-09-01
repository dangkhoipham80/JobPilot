"""The derived facets, and the honesty attached to them.

Two kinds of test here. The first kind pins parsing — a salary label becoming
numbers, a board tag becoming a countable skill. The second kind pins the thing
that makes the Market page trustworthy: **every aggregate reports how much of
the corpus it saw**. A ranking without its denominator describes the boards that
tag their ads while looking like it describes the market, and this database is
57% LinkedIn, which tags nothing.
"""

from __future__ import annotations

from datetime import date

from jobpilot.analytics import market
from jobpilot.crawler.salary import parse as parse_salary
from jobpilot.crawler.skills import canonicalise
from jobpilot.crawler.vietnam import canonical_city


# --------------------------------------------------------------------------- #
# salary
# --------------------------------------------------------------------------- #
def test_a_salary_label_becomes_numbers():
    vnd = parse_salary("20 - 60 triệu")
    assert (vnd.min, vnd.max, vnd.currency, vnd.period) == (20e6, 60e6, "VND", "month")

    usd = parse_salary("1,500 - 2,500 USD")
    assert (usd.min, usd.max, usd.currency) == (1500, 2500, "USD")

    yearly = parse_salary("120,000 - 160,000 USD/year")
    assert yearly.period == "year"
    # A yearly figure has to come down to a monthly one before it shares an axis
    # with a monthly one, or US remote roles dwarf every Vietnamese ad by 12x.
    assert yearly.usd_month == round(140_000 / 12, 2)


def test_the_unit_between_a_range_and_its_dash_is_not_lost():
    """"15tr - 25tr" parsed as 15–15: the unit broke the range pattern, so it
    fell through to the single-number branch and reported the floor as both
    bounds. A silently halved ceiling is the kind of wrong that looks right."""
    both = parse_salary("15tr - 25tr")
    assert (both.min, both.max) == (15e6, 25e6)


def test_a_tilde_is_a_range_separator_like_a_dash():
    """"2000～3000 USD" reported 2000-2000. Boards write the separator as a
    tilde, and a CJK-aware input method turns it full-width, so the label reads
    as a range to a human and as one number to the parser — the ceiling is
    replaced by the floor with nothing to show for it."""
    for label, low, high in (
        ("2000～3000 USD", 2000, 3000),
        ("1500~2500 USD", 1500, 2500),
        ("1000 ~ 2000 USD", 1000, 2000),
        ("2000〜3000 USD", 2000, 3000),
        # The real minus sign turns up too, and is not the ASCII hyphen.
        ("2000 − 3000 USD", 2000, 3000),
    ):
        parsed = parse_salary(label)
        assert (parsed.min, parsed.max) == (low, high), label


def test_a_currency_symbol_on_the_second_bound_does_not_break_the_range():
    """"$2,000 - $3,000" reported 2000-2000. The unit was allowed *after* the
    first figure but nothing was allowed *before* the second, and US boards
    write the symbol on both. Same failure as "15tr - 25tr", other end."""
    for label in (
        "$2,000 - $3,000",
        "$2,000-$3,000",
        "USD 2,000 - USD 3,000",
        "US$ 2,000 - US$ 3,000",
    ):
        parsed = parse_salary(label)
        assert (parsed.min, parsed.max) == (2000, 3000), label


def test_an_open_ended_floor_does_not_invent_a_ceiling():
    """"160 triệu+" reported 160-160, which asserts a maximum the ad never gave.
    The mirror of "up to 3000" leaving min None: an unstated bound stays None,
    because every such ad otherwise understates the top of the market by exactly
    the amount that made it worth posting."""
    for label in ("160 triệu+", "15tr+", "20 triệu trở lên", "Trên 30 triệu"):
        parsed = parse_salary(label)
        assert parsed.max is None, f"{label!r} invented a ceiling of {parsed.max}"
        assert parsed.min is not None
    assert parse_salary("160 triệu+").min == 160e6
    assert parse_salary("2000 USD or more").min == 2000
    # Punctuation after the "+" is still the open-ended reading.
    assert parse_salary("160 triệu+ (gross)").max is None


def test_a_plus_that_introduces_a_bonus_is_not_an_open_range():
    """"2000 USD + phụ cấp" is a base plus allowances, not "2000 or more" — and
    it is common enough in Vietnamese ads that reading it as an open range would
    be a guess rendered as a fact. It stays a point salary.

    The signal is the space *before* the plus, not what follows it. Keying on
    what follows gets "15tr+ gross" and "2000+ USD" backwards — both are open
    ranges whose plus happens to precede a word."""
    for label in ("2000 USD + phụ cấp", "3000 USD + bonus", "Lương cứng 15 triệu + hoa hồng"):
        parsed = parse_salary(label)
        assert parsed.min == parsed.max, f"{label!r} was read as an open range"
    for label in ("15tr+ gross", "2000+ USD", "5.000.000+ VNĐ"):
        assert parse_salary(label).max is None, f"{label!r} invented a ceiling"


def test_an_open_floor_also_needs_a_figure_written_as_money():
    """The money fence went on the floor/ceiling keywords but not on this branch,
    so any "<digits>+" still qualified: "20 triệu, 3+ năm kinh nghiệm" reported a
    floor of 3 million and put a 20tr job in the "<$500" band. Years of
    experience are the most common thing a "+" is attached to in a job ad."""
    for label in ("20 triệu, 3+ năm kinh nghiệm", "2000 USD, 5+ years experience"):
        parsed = parse_salary(label)
        assert parsed.min == parsed.max, f"{label!r} read a year count as pay"
    assert parse_salary("20 triệu, 3+ năm kinh nghiệm").min == 20e6
    assert parse_salary("2000 USD, 5+ years experience").min == 2000


def test_a_bounded_keyword_only_binds_to_a_figure_written_as_money():
    """"trên" and "dưới" are among the commonest words in Vietnamese ads and
    almost never introduce a salary. Letting them take any following number made
    "Lương 20 triệu, trên 2 năm kinh nghiệm" report a floor of 2 million — a
    20tr job dropped into the "<$500" band — and made "20 triệu, dưới 30 tuổi"
    use an *age* as the pay ceiling. Both are worse than the bare-figure branch
    they displaced, and both fail plausibly."""
    for label in (
        "Lương 20 triệu, trên 2 năm kinh nghiệm",
        "20 triệu, dưới 30 tuổi",
        # The first fence also accepted a bare figure at end of label, which let
        # the same sentence back in with the words reordered. An anchor is not
        # a unit.
        "Lương 20 triệu, tuổi dưới 30",
        "Lương 20 triệu, trên 2",
    ):
        parsed = parse_salary(label)
        assert (parsed.min, parsed.max) == (20e6, 20e6), label
    assert parse_salary("Lương 25 triệu (trên 3 năm KN)").min == 25e6

    # ...while the same keywords still work when they do introduce money.
    assert parse_salary("trên 30 triệu").min == 30e6
    assert parse_salary("dưới 30 triệu").max == 30e6
    assert parse_salary("up to 25 million VND").max == 25e6
    assert parse_salary("dưới 5.000.000 đ").max == 5e6


def test_a_trailing_dollar_sign_is_a_currency_marker_like_a_leading_one():
    """"$" counted as money before a figure but not after it, because the marker
    list had been written out three times and the copies drifted. So "Up to
    2000$" invented a floor of 2000 — breaking this module's own stated rule
    that "up to" has no minimum — while "Up to 2000 USD" did not."""
    capped = parse_salary("Up to 2000$")
    assert capped.min is None and capped.max == 2000
    floored = parse_salary("từ 2000$")
    assert floored.min == 2000 and floored.max is None
    # And the keyword must still find the right figure when another precedes it.
    assert parse_salary("Thưởng 2 tháng, up to 3000 dollars").max == 3000


def test_min_does_not_match_inside_another_word():
    """The floor keyword had no word boundary, so "Lương admin 5 triệu" matched
    the "min" inside "admin" and became an open-ended floor of 5 triệu."""
    parsed = parse_salary("Lương admin 5 triệu")
    assert (parsed.min, parsed.max) == (5e6, 5e6)


def test_a_salary_with_no_currency_is_refused():
    """"20 - 60" is millions of dong or dollars an hour depending on the board.
    Guessing would render a coin flip as a fact."""
    assert parse_salary("20 - 60") is None
    assert parse_salary("Thoả thuận") is None
    assert parse_salary("Negotiable") is None


def test_the_itviec_banner_is_not_a_salary():
    """A real row in the live database: the "IT Salary Report 2024-2025" banner
    was captured into the salary field by an older scraper. It must not become
    a number now that salaries are plotted."""
    assert parse_salary("IT Salary Report 2024-2025") is None


def test_up_to_has_no_floor_and_does_not_invent_one():
    capped = parse_salary("Up to 3,000 USD")
    assert capped.min is None and capped.max == 3000
    # Not 1500 — a midpoint against an imagined zero floor would drag the median
    # of the whole corpus down.
    assert capped.usd_month == 3000


# --------------------------------------------------------------------------- #
# skills
# --------------------------------------------------------------------------- #
def test_board_tags_become_countable_skills():
    out = canonicalise(["Java", "Spring Boot", "ReactJS", "spring boot", "+2", "Vollzeit"])
    # "+2" is an ITviec card's overflow badge; "Vollzeit" is German for
    # "full-time". Neither is a technology, and both outranked real stacks.
    assert out == ["java", "spring", "react"]


def test_a_role_is_not_a_skill_but_a_discipline_is():
    """Boards put "Backend Developer" in the same tag strip as "Java". The
    singular noun is the role; the -ing form is a field of work."""
    assert canonicalise(["Backend Developer", "Software Engineer"]) == []
    assert canonicalise(["Data Engineering"]) == ["data engineering"]


def test_industries_and_places_are_not_skills():
    assert canonicalise(["IT Services and IT Consulting", "India", "Financial Services"]) == []


# --------------------------------------------------------------------------- #
# cities
# --------------------------------------------------------------------------- #
def test_one_city_written_five_ways_counts_once():
    """Live data had Hà Nội split across three spellings, each with its own bar,
    each a third of the real number."""
    assert {canonical_city(t) for t in ("Ha Noi", "Hà Nội", "Hanoi", "HN")} == {"Hà Nội"}
    assert {canonical_city(t) for t in ("Ho Chi Minh", "Ho Chi Minh City", "TPHCM")} == {
        "Hồ Chí Minh"
    }


# --------------------------------------------------------------------------- #
# the aggregates, and their denominators
# --------------------------------------------------------------------------- #
def _payloads() -> list[dict]:
    return [
        {
            "source": "itviec",
            "skills_canonical": ["java", "spring"],
            "salary_range": {"usd_month": 1200},
            "city": "Hà Nội",
            "level": "senior",
            "match_score": 0.5,
            "posted_at": "2026-08-01T00:00:00+07:00",
            "quality": {"flags": []},
        },
        {
            "source": "linkedin",  # the shape that carries almost nothing
            "skills_canonical": [],
            "salary_range": None,
            "city": None,
            "level": None,
            "match_score": 0.25,
            "posted_at": None,
            "quality": {"flags": ["no_jd", "undated"]},
        },
    ]


def test_every_facet_reports_what_it_could_not_see():
    """The load-bearing test. A skills chart built from one of two jobs is a
    fact about one job; only the denominator says so."""
    payloads = _payloads()

    skills = market.top_skills(payloads)
    assert skills.covered == 1 and skills.total == 2
    assert skills.coverage == 0.5

    salary = market.salary_bands(payloads)
    assert salary.covered == 1
    assert "too few" in salary.note  # below MIN_SAMPLE

    # Every job is scored and every job lands in a quality bucket, so these two
    # are the only facets that legitimately claim full coverage.
    assert market.match_score_histogram(payloads).coverage == 1.0
    assert market.quality_flags(payloads).coverage == 1.0


def test_a_facet_with_nothing_in_it_says_so_rather_than_drawing_zero():
    bare = [{"source": "linkedin", "match_score": 0.1, "quality": {"flags": []}}]
    salary = market.salary_bands(bare)
    assert salary.covered == 0
    assert "No job" in salary.note
    # No summary row is appended when there is nothing to summarise — the page
    # would otherwise print a median of nothing.
    assert not any(r["key"] == "_summary" for r in salary.rows)


def test_remote_is_a_place_of_its_own():
    payloads = [
        {"is_remote": True, "city": None},
        {"is_remote": False, "city": "Hà Nội"},
    ]
    rows = {r["key"]: r["count"] for r in market.by_city(payloads).rows}
    assert rows == {"Remote": 1, "Hà Nội": 1}


def test_the_calendar_counts_posting_days_not_crawl_days():
    """The deck already charts `crawled_at`, which measures how often you ran
    the crawler. This has to measure the market instead."""
    payloads = [
        {"posted_at": "2026-08-01T09:00:00+07:00"},
        {"posted_at": "2026-08-01T18:00:00+07:00"},
        {"posted_at": "2026-08-02T09:00:00+07:00"},
        {"posted_at": None},
    ]
    facet = market.posting_calendar(payloads, today=date(2026, 8, 2))
    counts = {r["key"]: r["count"] for r in facet.rows}
    assert counts["2026-08-01"] == 2 and counts["2026-08-02"] == 1
    assert facet.covered == 3 and facet.total == 4


def test_the_calendar_emits_every_day_in_the_window_even_the_empty_ones():
    """A day nobody posted on is a fact about the market, and it has to hold a
    slot on the axis. Emitting only the days that *had* a posting turns a time
    axis into a list of unrelated labels: the distance between two neighbouring
    points is a day here and eighteen months there, so the plot silently
    rescales itself and three real weeks of hiring get squeezed into a third of
    the width."""
    payloads = [{"posted_at": "2026-08-08"}, {"posted_at": "2026-08-06"}]
    facet = market.posting_calendar(payloads, days=5, today=date(2026, 8, 8))

    assert [r["key"] for r in facet.rows] == [
        "2026-08-04",
        "2026-08-05",
        "2026-08-06",
        "2026-08-07",
        "2026-08-08",
    ]
    assert [r["count"] for r in facet.rows] == [0, 0, 1, 0, 1]


def test_postings_outside_the_window_are_excluded_and_counted():
    """Dropping them quietly would leave `covered` claiming the chart drew jobs
    it never plotted — and `covered` is the number this whole page rests on."""
    payloads = [
        {"posted_at": "2026-08-08"},
        {"posted_at": "2024-02-21"},  # a stray from two years ago
        {"posted_at": "not a date"},
    ]
    facet = market.posting_calendar(payloads, days=7, today=date(2026, 8, 8))

    assert facet.covered == 1, "only the in-window posting was drawn"
    assert facet.total == 3
    assert "2 dated posting(s) fall outside" in facet.note


def test_microservices_survives_the_industry_filter():
    """The bug the review gate caught, and the reason it caught it and 658 tests
    did not: "services" with no word boundary is a substring of "microservices",
    so one of the most common tags on the market was dropped from every ranking.
    The chart still rendered perfectly — it was just missing an entry nobody
    could see was missing.

    Same shape as `"remote" in "remote debugging"` and `intern` inside
    `internal`, both of which this repo has already paid for once.
    """
    from jobpilot.crawler.skills import canonical

    assert canonical("microservices") == "microservices"
    assert canonical("web services") == "web services"
    # And the industry sense is still filtered, which is what the pattern is for.
    assert canonical("IT Services and IT Consulting") is None
    assert canonical("Financial Services") is None


def test_a_city_abbreviation_survives_the_production_path():
    """`canonical_city("TPHCM")` always answered correctly, but `derived_facets`
    gates on `looks_like_city`, which knew a different vocabulary — so the
    pipeline dropped it and the unit test passed anyway by calling the
    canonicaliser directly. Test the path production actually takes.
    """
    from jobpilot.crawler.normalize import derived_facets

    for spelling in ("HN", "TPHCM", "Saigon", "Ha Noi", "Hà Nội"):
        assert derived_facets(None, [], spelling)["city"] in {"Hà Nội", "Hồ Chí Minh"}

    # And a non-place still yields no city rather than a bogus one.
    assert derived_facets(None, [], "Anywhere in the World")["city"] is None
