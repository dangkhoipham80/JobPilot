"""Pagination, and the two ways it goes wrong quietly.

The obvious half — "does `?limit=2&offset=2` return the third and fourth row" —
is barely worth a test. These pin the parts that fail *without an error*:

1. **A window with no total order.** `LIMIT/OFFSET` over an ordering that has
   ties is not deterministic. The database is free to order the ties one way
   for the page-1 query and another way for the page-2 query, so one row is
   served twice and another is never served at all. Nothing raises; you simply
   never see a job. Every paginated query here ends in a unique column, and
   `test_paging_a_tied_ordering_*` is what keeps it that way — the fixtures
   deliberately give every row the *same* sort key so the tie-break is the only
   thing doing any work.

2. **A total that doesn't match its filter.** `total` is what the UI divides to
   get a page count, so a total counted over the whole table while the rows are
   filtered produces pages 4 through 9 that are all empty.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from jobpilot.tests.conftest import api_client

from jobpilot.api.deps import get_db
from jobpilot.api.main import app
from jobpilot.api.schemas import MAX_PAGE_SIZE
from jobpilot.config import get_secrets
from jobpilot.store.models import Job, JobStatus

AUTH = {"X-API-Token": get_secrets().jobpilot_api_token}


@pytest.fixture
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Twelve jobs that all tie on every sort key the endpoint offers: no
    # `posted_at`, no `crawled_at`. If the ordering did not end in `Job.id`,
    # the rows would come back in whatever order the planner felt like.
    with session_factory() as s:
        s.add_all(
            Job(
                id=f"itviec:{i:02d}",
                source="itviec" if i % 2 else "topcv",
                title=f"Job {i:02d}",
                company="ACME",
                status=JobStatus.DISCOVERED,
            )
            for i in range(12)
        )
        s.commit()

    c = api_client(app)
    yield c
    app.dependency_overrides.clear()


def _page(client, **params) -> dict:
    r = client.get("/jobs", params=params, headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_window_reports_the_total_behind_it(client):
    """`len(items)` cannot answer "is there more?" — a page of 5 out of 5 and a
    page of 5 out of 900 are the same array on the wire."""
    body = _page(client, limit=5)
    assert len(body["items"]) == 5
    assert body["total"] == 12
    assert body["limit"] == 5 and body["offset"] == 0


def test_walking_the_pages_yields_every_row_exactly_once(client):
    """The tie-break test. Every seeded job has a null `posted_at`, so the
    only thing separating them is `Job.id` — remove it from the ORDER BY and
    this is the test that starts flaking."""
    seen: list[str] = []
    for offset in range(0, 12, 5):
        seen.extend(j["id"] for j in _page(client, limit=5, offset=offset)["items"])

    assert len(seen) == 12, "a row was served twice or skipped"
    assert len(set(seen)) == 12
    assert seen == sorted(seen, reverse=True), "pages must stay in one global order"


def test_skipped_jobs_sink_to_the_end_across_pages_not_within_each(client, session_factory):
    """A job you passed on stops holding a row among the ones still waiting.

    Two half-fixes are what this is written against. Re-sorting each page
    after the fact puts a skipped row at the bottom of *its* page and leaves
    page 1 one job short, hence the walk. And a sort key placed *after* the
    date keys only breaks ties — so the two skipped jobs here are given the
    newest dates on both clocks: with the shared fixture's all-null dates
    every row ties and that misplaced key passes too.
    """
    base = datetime(2026, 10, 1, tzinfo=timezone.utc)
    with session_factory() as s:
        for i in range(12):
            job = s.get(Job, f"itviec:{i:02d}")
            job.posted_at = job.crawled_at = base + timedelta(days=i)
        # Newest of all, on both clocks: by date alone they lead the list.
        for job_id, days in (("itviec:11", 31), ("itviec:07", 30)):
            job = s.get(Job, job_id)
            job.status = JobStatus.SKIPPED
            job.posted_at = job.crawled_at = base + timedelta(days=days)
        s.commit()

    live = [f"itviec:{i:02d}" for i in (10, 9, 8, 6, 5, 4, 3, 2, 1, 0)]
    for order in ("posted", "crawled", "match"):
        seen: list[str] = []
        for offset in range(0, 12, 5):
            page = _page(client, limit=5, offset=offset, order=order)
            seen.extend(j["id"] for j in page["items"])
        assert seen == live + ["itviec:11", "itviec:07"], order


def _spread(session_factory) -> None:
    """Give the twelve jobs two crawl days and the four scores a crawl produces.

    Even ids were crawled on the newer day, odd ids the day before. Inside a
    day the *lower* scores carry the *later* timestamps, so an ordering by
    exact crawl time and an ordering by crawl day then match disagree on every
    adjacent pair.
    """
    newer = datetime(2026, 10, 2, 2, 0, tzinfo=timezone.utc)
    older = datetime(2026, 10, 1, 2, 0, tzinfo=timezone.utc)
    with session_factory() as s:
        for i in range(12):
            job = s.get(Job, f"itviec:{i:02d}")
            job.match_score = (0.25, 0.5, 0.75, 1.0)[(i // 2) % 4]
            # later in the day the lower the score
            job.crawled_at = (older if i % 2 else newer) + timedelta(hours=4 - (i // 2) % 4)
        s.commit()


def test_the_default_order_is_crawl_day_then_match(client, session_factory):
    """What turned up most recently, best match first.

    The day is the outer key and it beats the score: a perfect match from
    yesterday stays under a weak one from today. Inside the day the score
    decides and the timestamp does not — by exact crawl time the score would
    only ever break ties, and one crawl's best job would sit under the next
    crawl's worst.
    """
    _spread(session_factory)
    rows = _page(client, limit=12)["items"]  # no `order`: this is the default

    days = [r["crawled_at"][:10] for r in rows]
    assert days == ["2026-10-02"] * 6 + ["2026-10-01"] * 6
    for half in (rows[:6], rows[6:]):
        scores = [r["match_score"] for r in half]
        assert scores == sorted(scores, reverse=True)
        assert scores[0] == 1.0 and scores[-1] == 0.25
    # ...and that really is a different list from "most recently crawled".
    by_time = sorted(rows, key=lambda r: r["crawled_at"], reverse=True)
    assert [r["id"] for r in rows] != [r["id"] for r in by_time]
    assert rows == _page(client, limit=12, order="crawled")["items"]


def test_order_match_ranks_everything_by_score_across_days(client, session_factory):
    _spread(session_factory)
    seen: list[dict] = []
    for offset in range(0, 12, 5):
        seen.extend(_page(client, limit=5, offset=offset, order="match")["items"])

    assert len({r["id"] for r in seen}) == 12, "ties on the score must not repeat or drop a row"
    scores = [r["match_score"] for r in seen]
    assert scores == sorted(scores, reverse=True)
    # Both days appear among the top scores: the day is no longer the outer key.
    assert {r["crawled_at"][:10] for r in seen if r["match_score"] == 1.0} == {
        "2026-10-01",
        "2026-10-02",
    }


def test_match_bands_are_half_open_so_adjacent_ones_partition_the_list(client, session_factory):
    """Every crawled score sits exactly on a band edge (0.25, 0.5, 0.75, 1.0).

    With two inclusive ends a 0.5 job would be counted in the band below and
    the band above; with two exclusive ones, in neither. `match_min` is
    inclusive and `match_below` exclusive, so the bands the Jobs page offers
    add up to the whole list.
    """
    _spread(session_factory)
    bands = [
        {"match_min": 0.75},
        {"match_min": 0.5, "match_below": 0.75},
        {"match_min": 0.25, "match_below": 0.5},
        {"match_below": 0.25},
    ]
    pages = [_page(client, limit=50, **band) for band in bands]

    # The fixture holds 0.25 x4, 0.5 x4, 0.75 x2 and 1.0 x2.
    assert [p["total"] for p in pages] == [4, 4, 4, 0]
    assert {r["match_score"] for r in pages[0]["items"]} == {0.75, 1.0}
    assert {r["match_score"] for r in pages[1]["items"]} == {0.5}
    ids = [r["id"] for p in pages for r in p["items"]]
    assert len(ids) == len(set(ids)) == 12


def test_order_posted_puts_undated_postings_after_dated_ones(client, session_factory):
    """ "Newest postings first" must not open with postings that have no date.

    Honest about its reach: SQLite already sorts NULL last under DESC, so this
    passes here with or without `nulls_last()`. Postgres sorts NULL *first* —
    that is where the bug lived (the first five rows of the real list were all
    undated) and where the fix was checked. What this pins is the contract.
    """
    with session_factory() as s:
        for i in (2, 5, 9):
            s.get(Job, f"itviec:{i:02d}").posted_at = datetime(2026, 10, i, tzinfo=timezone.utc)
        s.commit()

    rows = _page(client, limit=12, order="posted")["items"]
    assert [r["id"] for r in rows[:3]] == ["itviec:09", "itviec:05", "itviec:02"]
    assert all(r["posted_at"] is None for r in rows[3:])


def test_an_inverted_match_band_is_refused_not_answered_with_nothing(client):
    """An empty page would read as "no jobs score that" — a different fact."""
    r = client.get("/jobs", params={"match_min": 0.75, "match_below": 0.5}, headers=AUTH)
    assert r.status_code == 422
    assert client.get("/jobs", params={"match_min": 1.5}, headers=AUTH).status_code == 422
    assert client.get("/jobs", params={"order": "salary"}, headers=AUTH).status_code == 422


def test_filtering_to_skipped_still_finds_them(client, session_factory):
    """Sinking is not hiding: the status filter is how a skipped job is found
    again, so it has to keep returning them, in the usual order."""
    with session_factory() as s:
        s.get(Job, "itviec:11").status = JobStatus.SKIPPED
        s.get(Job, "itviec:07").status = JobStatus.SKIPPED
        s.commit()

    body = _page(client, status="SKIPPED")
    assert body["total"] == 2
    assert [j["id"] for j in body["items"]] == ["itviec:11", "itviec:07"]


def test_the_total_is_counted_with_the_same_filter_as_the_rows(client):
    """A total counted over the table instead of the query offers the user
    pages that come back empty."""
    body = _page(client, source="itviec", limit=2)
    assert body["total"] == 6, "six of the twelve are itviec"
    assert len(body["items"]) == 2
    assert all(j["source"] == "itviec" for j in body["items"])


def test_an_offset_past_the_end_is_an_empty_page_not_an_error(client):
    body = _page(client, limit=5, offset=99)
    assert body["items"] == []
    # The total still describes the result, so the UI can say "you're past the
    # end" and offer a way back rather than showing a bare empty list.
    assert body["total"] == 12


def test_the_page_size_is_capped(client):
    """`/applications` used to take an uncapped `limit`. An unbounded list
    endpoint is a denial of service against your own dashboard, so asking for
    too much is a 422 rather than a slow success."""
    assert client.get("/jobs", params={"limit": MAX_PAGE_SIZE + 1}, headers=AUTH).status_code == 422
    assert client.get("/jobs", params={"limit": 0}, headers=AUTH).status_code == 422
    assert client.get("/jobs", params={"offset": -1}, headers=AUTH).status_code == 422
    assert client.get("/jobs", params={"limit": MAX_PAGE_SIZE}, headers=AUTH).status_code == 200


def test_paginated_queries_must_declare_an_order(session_factory):
    """The helper refuses an unordered statement rather than producing a page
    that is only accidentally correct."""
    from sqlalchemy import select

    from jobpilot.api.paging import page_query

    with session_factory() as db:
        with pytest.raises(ValueError, match="ORDER BY"):
            page_query(db, select(Job), limit=5, offset=0)
