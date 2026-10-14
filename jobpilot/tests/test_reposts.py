"""Re-listings: every copy keeps its row, the list shows the newest.

The shape seen on the live data: one board lists a role, takes it down, and lists
it again weeks later under a new id — outside the dedup window, so it is
inserted. These pin that the old copies then point at the new one, that the list
hides them unless the user acted on them, and that "same posting" is the dedup
layer's own rule rather than a looser one.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from jobpilot.api.deps import get_db
from jobpilot.api.main import app
from jobpilot.config import get_secrets
from jobpilot.crawler.reposts import relink_all
from jobpilot.store.models import Job, JobStatus
from jobpilot.tests.conftest import api_client
from jobpilot.config import Config, CrawlCfg
from jobpilot.tests.test_crawler_dedup import NOW, _job, _persist

AUTH = {"X-API-Token": get_secrets().jobpilot_api_token}
LATER = NOW + timedelta(days=30)  # well past the 14-day window


@pytest.fixture
def cfg() -> Config:
    return Config(crawl=CrawlCfg(stacks=["Java"], exclude_keywords=[]))


@pytest.fixture
def db(session_factory):
    with session_factory() as session:
        yield session


def _row(db, job_id: str) -> Job:
    return db.get(Job, job_id)


def test_a_board_relisting_a_posting_points_the_old_copy_at_the_new(db, cfg):
    _persist(db, cfg, [_job("itviec", "1", "Java Backend Developer")])
    stats = _persist(db, cfg, [_job("itviec", "2", "Java Backend Developer")], now=LATER)

    assert stats.inserted == 1  # the live copy is kept, not suppressed
    assert _row(db, "itviec:1").latest_id == "itviec:2"
    assert _row(db, "itviec:2").latest_id is None


def test_a_third_listing_moves_the_whole_chain_to_it(db, cfg):
    _persist(db, cfg, [_job("itviec", "1", "Java Backend Developer")])
    _persist(db, cfg, [_job("itviec", "2", "Java Backend Developer")], now=LATER)
    _persist(db, cfg, [_job("itviec", "3", "Java Backend Developer")], now=LATER + timedelta(days=30))

    assert {_row(db, f"itviec:{i}").latest_id for i in (1, 2)} == {"itviec:3"}
    assert _row(db, "itviec:3").latest_id is None


def test_two_titles_on_one_board_are_two_postings(db, cfg):
    """Same rule as the dedup layer: one board, two titles = two postings."""
    _persist(db, cfg, [_job("linkedin", "1", "Java Developer")])
    _persist(db, cfg, [_job("linkedin", "2", "Junior Java Developer (Mandarin)")], now=LATER)

    assert _row(db, "linkedin:1").latest_id is None
    assert _row(db, "linkedin:2").latest_id is None


def test_other_employers_are_never_grouped(db, cfg):
    _persist(db, cfg, [_job("itviec", "1", "Java Developer", company="ACME")])
    _persist(db, cfg, [_job("itviec", "2", "Java Developer", company="Globex")], now=LATER)

    assert _row(db, "itviec:1").latest_id is None


def test_the_copy_still_being_seen_is_the_newest(db, cfg):
    """An older id re-seen after the new one went up takes the head back."""
    _persist(db, cfg, [_job("itviec", "1", "Java Backend Developer")])
    _persist(db, cfg, [_job("itviec", "2", "Java Backend Developer")], now=LATER)
    _persist(db, cfg, [_job("itviec", "1", "Java Backend Developer")], now=LATER + timedelta(days=1))

    assert _row(db, "itviec:1").latest_id is None
    assert _row(db, "itviec:2").latest_id == "itviec:1"


def test_backfill_links_rows_written_before_the_column_and_is_idempotent(db, cfg):
    _persist(db, cfg, [_job("itviec", "1", "Java Backend Developer")])
    _persist(db, cfg, [_job("itviec", "2", "Java Backend Developer")], now=LATER)
    for job in db.scalars(select(Job)):
        job.latest_id = None
    db.flush()

    first = relink_all(db)
    assert (first.groups, first.hidden) == (1, 1)
    assert _row(db, "itviec:1").latest_id == "itviec:2"
    assert relink_all(db).changed == 0


# --------------------------------------------------------------------------- #
# the list and the detail page
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(session_factory, cfg):
    with session_factory() as s:
        _persist(s, cfg, [_job("itviec", "1", "Java Backend Developer")])
        _persist(s, cfg, [_job("itviec", "2", "Java Backend Developer")], now=LATER)
        _persist(s, cfg, [_job("itviec", "3", "Java Backend Developer")], now=LATER + timedelta(days=30))
        s.commit()

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield api_client(app)
    app.dependency_overrides.clear()


def _list(client, **params) -> list[dict]:
    r = client.get("/jobs", params=params, headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_the_list_shows_one_row_per_posting_with_its_count(client):
    items = _list(client)
    assert [j["id"] for j in items] == ["itviec:3"]
    assert items[0]["reposts"] == 2


def test_every_copy_is_one_parameter_away(client):
    assert {j["id"] for j in _list(client, reposts=True)} == {"itviec:1", "itviec:2", "itviec:3"}


def test_an_old_copy_the_user_acted_on_stays_on_the_list(client, session_factory):
    with session_factory() as s:
        s.get(Job, "itviec:1").status = JobStatus.SHORTLISTED
        s.commit()
    assert {j["id"] for j in _list(client)} == {"itviec:1", "itviec:3"}


def test_detail_lists_the_other_copies(client):
    newest = client.get("/jobs/itviec:3", headers=AUTH).json()
    assert [c["id"] for c in newest["copies"]] == ["itviec:2", "itviec:1"]
    assert newest["reposts"] == 2

    old = client.get("/jobs/itviec:1", headers=AUTH).json()
    assert old["latest_id"] == "itviec:3"
    assert {c["id"] for c in old["copies"]} == {"itviec:2", "itviec:3"}
