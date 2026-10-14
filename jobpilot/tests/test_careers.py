"""Company career sites beyond Greenhouse/Lever: XML feed, Workday, Eightfold, Google.

Fixtures are invented (Acme, Globex): which companies the user follows is
personal and this repo is public (crawler/CLAUDE.md). The *shapes* are the ones
read off the live sites on 2026-10-14.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from jobpilot.config import Config, CrawlCfg
from jobpilot.crawler.careers import (
    CareerFeedScraper,
    EightfoldScraper,
    GoogleCareersScraper,
    WorkdayScraper,
    _company_from_legal,
)
from jobpilot.crawler.normalize import VN_TZ, normalize
from jobpilot.crawler.persist import persist_jobs
from jobpilot.crawler.ratelimit import RateLimiter
from jobpilot.crawler.types import RawJob

NO_WAIT = RateLimiter(0, 0)

FEED = """<?xml version="1.0" encoding="utf-8"?>
<source>
  <publisher>Acme</publisher>
  <job>
    <title><![CDATA[Backend Engineer, Payments]]></title>
    <date><![CDATA[Wed, 14 Oct 2026 10:42:02 GMT]]></date>
    <referencenumber><![CDATA[REF1]]></referencenumber>
    <url><![CDATA[https://careers.acme.example/en/jobs/700000000000001/senior-software-engineer-backend/]]></url>
    <company><![CDATA[Acme]]></company>
    <city><![CDATA[HCMC]]></city><state><![CDATA[]]></state><country><![CDATA[Vietnam]]></country>
    <description><![CDATA[<p>Build Java services.</p>]]></description>
    <jobtype><![CDATA[Full-time]]></jobtype><category><![CDATA[Engineering]]></category>
    <remotetype><![CDATA[Hybrid]]></remotetype>
  </job>
  <job>
    <title><![CDATA[Backend Engineer, Payments]]></title>
    <date><![CDATA[Tue, 13 Oct 2026 09:00:00 GMT]]></date>
    <url><![CDATA[https://careers.acme.example/en/jobs/700000000000002/senior-software-engineer-backend/]]></url>
    <company><![CDATA[Acme]]></company>
    <city><![CDATA[HCMC]]></city><country><![CDATA[Vietnam]]></country>
    <description><![CDATA[<p>Another team.</p>]]></description>
    <category><![CDATA[Engineering]]></category>
  </job>
  <job>
    <title><![CDATA[Backend Engineer]]></title>
    <url><![CDATA[https://careers.acme.example/en/jobs/700000000000003/backend-engineer/]]></url>
    <company><![CDATA[Acme]]></company>
    <city><![CDATA[Singapore]]></city><country><![CDATA[Singapore]]></country>
    <description><![CDATA[<p>Elsewhere.</p>]]></description>
  </job>
</source>"""


def test_xml_feed_reads_every_posting_and_keeps_the_scope():
    s = CareerFeedScraper(
        boards=["https://careers.acme.example/jobs/xml/?rss=true"],
        locations=["Ho Chi Minh"],
        fetcher=lambda u: FEED,
        rate_limiter=NO_WAIT,
    )
    jobs = s.crawl("backend", limit=10)
    assert [j.native_id for j in jobs] == ["700000000000001", "700000000000002"]  # id from URL
    first = jobs[0]
    assert (first.company, first.location) == ("Acme", "HCMC, Vietnam")
    assert "Build Java services" in first.description_html
    assert first.extra["work_mode_stated"] == "hybrid"
    assert first.apply_channel == "external"


def test_xml_feed_refuses_something_that_is_not_a_feed():
    s = CareerFeedScraper(boards=["x"], fetcher=lambda u: "<html/>", rate_limiter=NO_WAIT)
    with pytest.raises(ValueError):
        s.crawl("backend", limit=5)


# --------------------------------------------------------------------------- #
# Workday
# --------------------------------------------------------------------------- #
WD_BOARD = "acme.wd5.myworkdayjobs.com/AcmeCareers"
WD_LIST = {
    "total": 2,
    "jobPostings": [
        {
            "title": "Backend Engineer",
            "externalPath": "/job/Vietnam-Ho-Chi-Minh-City/Backend-Engineer_JR100",
            "locationsText": "Vietnam, Ho Chi Minh City",
        },
        {
            "title": "Platform Engineer",
            "externalPath": "/job/Vietnam-Hanoi/Platform-Engineer_JR101",
            "locationsText": "2 Locations",
        },
    ],
}


def _wd_detail(title: str, location: str, extra: list[str] | None = None) -> str:
    return json.dumps(
        {
            "jobPostingInfo": {
                "title": title,
                "jobDescription": "<p>Java and Kafka.</p>",
                "location": location,
                "additionalLocations": extra or [],
                "startDate": "2026-10-01",
                "jobReqId": "JR100",
                "externalUrl": f"https://{WD_BOARD.split('/')[0]}/AcmeCareers/job/x",
            },
            "hiringOrganization": {"name": "VN01 Acme Vietnam Company Limited"},
        }
    )


class _PostingFetcher:
    """A fetcher that can POST, recording both kinds of request."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, url):
        self.calls.append(("GET", url, None))
        return self.routes(url, None)

    def post_json(self, url, body):
        self.calls.append(("POST", url, body))
        return self.routes(url, body)


def test_workday_posts_a_paged_search_and_reads_the_posting_api():
    def routes(url, body):
        if url.endswith("/jobs"):
            return json.dumps(WD_LIST if body["offset"] == 0 else {"jobPostings": []})
        if url.endswith("_JR100"):
            return _wd_detail("Backend Engineer", "Vietnam, Ho Chi Minh City")
        return _wd_detail("Platform Engineer", "Vietnam, Hanoi", ["Vietnam, Ho Chi Minh City"])

    fetch = _PostingFetcher(routes)
    s = WorkdayScraper(boards=[WD_BOARD], locations=["Ho Chi Minh"], fetcher=fetch, rate_limiter=NO_WAIT)
    jobs = s.crawl("engineer", limit=10)

    first_post = fetch.calls[0]
    assert first_post[0] == "POST"
    assert first_post[1] == "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/AcmeCareers/jobs"
    assert first_post[2]["searchText"] == "Vietnam" and first_post[2]["offset"] == 0
    # "2 Locations" names no place: kept, and the posting's own list decides.
    assert [j.native_id for j in jobs] == ["acme:JR100", "acme:JR101"]
    assert jobs[0].company == "Acme"  # not "VN01 Acme Vietnam Company Limited"
    assert jobs[1].location == "Vietnam, Ho Chi Minh City"  # the label that is in scope
    assert "Kafka" in jobs[0].description_html


def test_workday_board_token_is_validated():
    with pytest.raises(ValueError):
        WorkdayScraper(boards=["acme.example.com/Careers"]).board_page_url(
            "acme.example.com/Careers", "", 1
        )


@pytest.mark.parametrize(
    ("legal", "name"),
    [
        ("VN01 Acme Vietnam Company Limited", "Acme"),
        ("Globex Pte. Ltd.", "Globex"),
        ("Initech", "Initech"),
    ],
)
def test_workday_employer_name_drops_codes_and_legal_tails(legal, name):
    assert _company_from_legal(legal) == name


# --------------------------------------------------------------------------- #
# Eightfold
# --------------------------------------------------------------------------- #
EF_SEARCH = {
    "status": 200,
    "data": {
        "count": 1,
        "positions": [
            {
                "id": 555,
                "name": "Solution Architect",
                "locations": ["Vietnam, Multiple Locations", "Singapore, Singapore"],
                "postedTs": 1790000000,
                "department": "Cloud",
                "workLocationOption": "onsite",
            }
        ],
    },
}
EF_DETAIL = {
    "data": {
        "name": "Solution Architect",
        "jobDescription": "<p>Design systems.</p>",
        "publicUrl": "https://apply.careers.acme.example/careers/job/555",
        "workLocationOption": "onsite",
    }
}


def test_eightfold_warms_up_the_session_before_the_api():
    def routes(url, body):
        if url.endswith("/careers"):
            return "<html>careers</html>"
        if "/api/pcsx/search" in url:
            return json.dumps(EF_SEARCH if "start=0" in url else {"data": {"positions": []}})
        return json.dumps(EF_DETAIL)

    fetch = _PostingFetcher(routes)
    s = EightfoldScraper(
        boards=["apply.careers.acme.example/acme.example"],
        locations=["Vietnam"],
        fetcher=fetch,
        rate_limiter=NO_WAIT,
    )
    jobs = s.crawl("architect", limit=5)

    assert fetch.calls[0][1] == "https://apply.careers.acme.example/careers"
    assert "location=Vietnam" in fetch.calls[1][1]
    [job] = jobs
    assert (job.native_id, job.company) == ("555", "Acme")
    assert job.location == "Vietnam, Multiple Locations"
    assert job.extra["work_mode_stated"] == "onsite"
    assert job.url.endswith("/careers/job/555")


# --------------------------------------------------------------------------- #
# Google Careers
# --------------------------------------------------------------------------- #
def _google_row(jid: str, title: str, place: str) -> list:
    row = [None] * 21
    row[0], row[1], row[7] = jid, title, "Google"
    row[3] = [None, "<ul><li>Own the service.</li></ul>"]
    row[4] = [None, "<ul><li>Java.</li></ul>"]
    row[9] = [[place, [place], "City", None, "Region", "VN"]]
    row[10] = [None, "<div>About the job.</div>"]
    row[12] = [1791467031, 0]
    return row


def _google_page(rows: list) -> str:
    data = json.dumps([rows, None, len(rows), 20])
    return (
        "<html><script>AF_initDataCallback({key: 'ds:0', hash: '1', data:[], sideChannel: {}});"
        f"</script><script>AF_initDataCallback({{key: 'ds:1', hash: '2', data:{data}, "
        "sideChannel: {}});</script></html>"
    )


def test_google_reads_the_embedded_rows_from_page_one_only():
    fetched: list[str] = []
    page = _google_page([_google_row("123", "Software Engineer", "Hanoi, Ha Noi, Vietnam")])
    s = GoogleCareersScraper(
        boards=["google"],
        locations=["Vietnam"],
        fetcher=lambda u: fetched.append(u) or page,
        rate_limiter=NO_WAIT,
    )
    [job] = s.crawl("software engineer", limit=5)

    # robots.txt disallows `results?page=`: one request, narrowed by q=.
    assert len(fetched) == 1 and "page=" not in fetched[0] and "q=software+engineer" in fetched[0]
    assert job.native_id == "123" and job.location == "Hanoi, Ha Noi, Vietnam"
    assert "Own the service" in job.description_html and "About the job" in job.description_html
    assert s.board_page_url("google", "x", 2) == ""


def test_google_layout_change_is_an_error_not_an_empty_board():
    page = _google_page([["not", "a", "job", "row"]])
    s = GoogleCareersScraper(boards=["google"], fetcher=lambda u: page, rate_limiter=NO_WAIT)
    with pytest.raises(ValueError):
        s.crawl("engineer", limit=5)


# --------------------------------------------------------------------------- #
# what the pipeline does with them
# --------------------------------------------------------------------------- #
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=VN_TZ)


def _raw(source: str, native_id: str, company: str = "Acme", **kw) -> RawJob:
    return RawJob(
        source=source,
        native_id=native_id,
        url=f"https://careers.acme.example/{native_id}",
        title="Backend Engineer, Payments",
        company=company,
        description_md="Java services. " * 40,
        **kw,
    )


def test_one_title_twice_on_a_company_board_is_two_openings(session_factory):
    """Several openings under one title on one employer's system were deduped
    to one — the same-board rule is for job boards re-listing, not requisitions."""
    cfg = Config(crawl=CrawlCfg(stacks=["Java"], exclude_keywords=[]))
    with session_factory() as db:
        jobs = [normalize(_raw("careerfeed", n), cfg, NOW) for n in ("1", "2")]
        stats = persist_jobs(db, jobs, now=NOW)
        assert (stats.inserted, stats.duplicates) == (2, 0)

        board = [
            normalize(_raw("itviec", n, company="Globex"), cfg, NOW + timedelta(days=1))
            for n in ("1", "2")
        ]
        stats = persist_jobs(db, board, now=NOW + timedelta(days=1))
        assert stats.duplicates == 1  # a job board listing one title twice is still one


def test_a_stated_work_mode_beats_the_label():
    cfg = Config(crawl=CrawlCfg(stacks=["Java"], exclude_keywords=[]))
    raw = _raw("eightfold", "9", location="Vietnam", extra={"work_mode_stated": "remote"})
    job = normalize(raw, cfg, NOW)
    assert job.payload["work_mode"] == "remote" and job.payload["is_remote"] is True
