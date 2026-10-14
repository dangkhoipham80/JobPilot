"""Where and how the user wants to work: what it narrows, and what it keeps."""

from __future__ import annotations

from datetime import datetime

import pytest

from jobpilot.config import AtsCfg, Config, CrawlCfg, SourceCfg
from jobpilot.crawler.cityscope import CityScopedScraper
from jobpilot.crawler.normalize import VN_TZ, normalize
from jobpilot.crawler.registry import build_scrapers
from jobpilot.crawler.scope import Scope
from jobpilot.crawler.types import RawJob
from jobpilot.crawler.vietnam import canonical_city

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=VN_TZ)
CFG = Config(crawl=CrawlCfg(stacks=["Java"], exclude_keywords=[]))


_LABEL = {"onsite": "On-site", "hybrid": "Hybrid", "remote": "Remote"}


def _job(location: str | None, mode: str | None = None):
    # The work mode as LinkedIn writes it, on the location label.
    label = f"{location} ({_LABEL[mode]})" if location and mode else location
    raw = RawJob(
        source="itviec",
        native_id="1",
        url="https://itviec.example/1",
        title="Java Developer",
        company="Acme",
        location=label,
        description_md="Java " * 50,
    )
    return normalize(raw, CFG, NOW)


def test_every_mode_chosen_is_no_filter_and_unknown_modes_are_dropped():
    assert Scope.of([], ["onsite", "hybrid", "remote"]).work_modes == ()
    assert Scope.of([" Ha Noi ", "Ha Noi", ""], ["remote", "freelance"]) == Scope(
        places=("Ha Noi",), work_modes=("remote",)
    )


@pytest.mark.parametrize(
    ("places", "city"),
    [
        ([], None),  # no preference: crawl.city stands
        (["Ho Chi Minh"], "Ho Chi Minh"),
        (["hcm"], "hcm"),
        (["Ho Chi Minh", "Ha Noi"], ""),  # two cities: whole country, then narrow
        (["Vietnam"], ""),
        (["Ho Chi Minh", "Vietnam"], ""),
        (["Singapore"], ""),
    ],
)
def test_the_boards_get_one_city_or_the_whole_country(places, city):
    assert Scope.of(places, []).board_city() == city


def test_a_stated_mismatch_is_left_out_and_silence_is_kept():
    hybrid_only = Scope.of([], ["hybrid", "remote"])
    assert hybrid_only.keeps(_job("Ho Chi Minh", "onsite")) == "work mode onsite"
    assert _job("Ho Chi Minh", "onsite").payload["work_mode"] == "onsite"
    assert hybrid_only.keeps(_job("Ho Chi Minh", "remote")) is None
    assert hybrid_only.keeps(_job("Ho Chi Minh")) is None  # nobody said: kept


def test_places_match_by_city_spelling_and_country():
    hcm = Scope.of(["Ho Chi Minh"], [])
    assert hcm.keeps(_job("HCMC, Vietnam")) is None
    assert hcm.keeps(_job("Thành phố Hồ Chí Minh")) is None
    assert hcm.keeps(_job("Ha Noi")) == "location Ha Noi"
    assert hcm.keeps(_job(None)) is None  # no label: kept

    vietnam = Scope.of(["Vietnam"], [])
    assert vietnam.keeps(_job("Da Nang")) is None
    assert vietnam.keeps(_job("Singapore")) == "location Singapore"


def test_remote_in_the_places_asks_for_remote_postings():
    scope = Scope.of(["Ho Chi Minh", "Remote"], [])
    assert scope.keeps(_job("Berlin, Germany", "remote")) is None
    assert scope.keeps(_job("Berlin, Germany", "onsite")) == "location Berlin, Germany (On-site)"


def test_the_scope_narrows_the_search_where_a_source_can_be_narrowed():
    cfg = Config(
        crawl=CrawlCfg(city="Da Nang"),
        ats=AtsCfg(greenhouse=["acme"], locations=["Singapore"]),
        sources=[
            SourceCfg(key="itviec", tier=1, enabled=True),
            SourceCfg(key="greenhouse", tier=3, enabled=True),
        ],
    )
    city_board, company_board = build_scrapers(cfg, scope=Scope.of(["Ha Noi"], []))
    assert isinstance(city_board, CityScopedScraper)
    assert canonical_city(city_board.city) == canonical_city("Ha Noi")
    assert company_board.locations == ("Ha Noi",)

    # No place preference: the saved city and ats.locations stand.
    city_board, company_board = build_scrapers(cfg, scope=Scope.of([], ["remote"]))
    assert canonical_city(city_board.city) == canonical_city("Da Nang")
    assert company_board.locations == ("Singapore",)


def test_saved_work_modes_are_validated():
    with pytest.raises(ValueError):
        CrawlCfg(work_modes=["freelance"])
