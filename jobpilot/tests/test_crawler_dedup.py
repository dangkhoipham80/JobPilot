"""Cross-source dedup: the window, the level split, and the trace it leaves.

These pin four behaviours that a green suite previously agreed were fine, and
which only showed up by running ``persist_jobs`` against a real database and
counting the rows:

A. re-crawling the same posting never duplicates it (this always worked, and is
   pinned here so the rest of the file cannot quietly break it),
B. the dedup window is measured from the **last** sighting, so a posting still
   on its board keeps another board's copy out indefinitely,
C. *Senior* / *Junior* / *Intern* of one title at one company are three roles,
   while a title that names no level still matches anything,
D. nothing is dropped without a trace, and the copy carrying a JD wins even when
   the JD-less one got there first.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from jobpilot.config import Config, CrawlCfg
from jobpilot.crawler.normalize import VN_TZ, normalize
from jobpilot.crawler.persist import persist_jobs
from jobpilot.crawler.quality import THIN_JD_CHARS
from jobpilot.crawler.types import RawJob
from jobpilot.store.models import Job

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=VN_TZ)

#: Long enough to clear ``THIN_JD_CHARS`` — a description the tailor could work
#: from, as opposed to a LinkedIn alert's title-and-nothing-else.
FULL_JD = "Build and run Java services. " * 40


@pytest.fixture
def cfg() -> Config:
    return Config(crawl=CrawlCfg(stacks=["Java"], exclude_keywords=[]))


@pytest.fixture
def db(session_factory):
    with session_factory() as session:
        yield session


def _job(
    source: str,
    native_id: str,
    title: str,
    company: str = "ACME",
    *,
    jd: str = FULL_JD,
    needs_jd: bool = False,
):
    return RawJob(
        source=source,
        native_id=native_id,
        url=f"https://{source}.example/{native_id}",
        title=title,
        company=company,
        posted_raw="2 days ago",
        skills=["Java"],
        description_md=jd,
        extra={"needs_jd": True} if needs_jd else {},
    )


def _persist(db, cfg, raws, *, now=NOW, dedup_days: int = 14):
    jobs = [normalize(raw, cfg, now) for raw in raws]
    return persist_jobs(db, jobs, dedup_days=dedup_days, now=now)


def _ids(db) -> set[str]:
    return set(db.scalars(select(Job.id)))


def _naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None)


# --------------------------------------------------------------------------- #
# A. the same posting, crawled again
# --------------------------------------------------------------------------- #
def test_recrawling_the_same_posting_updates_it_rather_than_duplicating(db, cfg):
    raw = _job("itviec", "1", "Backend Engineer")

    first = _persist(db, cfg, [raw])
    second = _persist(db, cfg, [raw], now=NOW + timedelta(days=1))

    assert (first.inserted, first.updated) == (1, 0)
    assert (second.inserted, second.updated) == (0, 1)
    assert len(_ids(db)) == 1


def test_a_refresh_bumps_last_seen_at_and_leaves_crawled_at_alone(db, cfg):
    """The whole point of the second column.

    ``crawled_at`` drives the dashboard's by-day chart, the ``crawled`` sort and
    the ``crawled_after`` filter. Bumping it on re-crawl would pile every job
    ever seen onto today — a chart that is wrong and looks entirely plausible.
    """
    raw = _job("itviec", "1", "Backend Engineer")
    later = NOW + timedelta(days=10)

    _persist(db, cfg, [raw])
    _persist(db, cfg, [raw], now=later)

    job = db.get(Job, "itviec:1")
    # SQLite hands back naive datetimes where Postgres returns aware ones, so
    # compare wall-clock values rather than the tzinfo the backend chose.
    assert _naive(job.crawled_at) == _naive(NOW)
    assert _naive(job.last_seen_at) == _naive(later)


# --------------------------------------------------------------------------- #
# B. the window runs from the last sighting
# --------------------------------------------------------------------------- #
def test_a_posting_still_on_its_board_keeps_the_other_boards_copy_out(db, cfg):
    """The bug this file exists for.

    The ITviec posting is re-crawled every day, so it is never gone. Measured
    from ``crawled_at`` (first sighting) it nevertheless fell out of its own
    14-day window, and on day 15 the TopCV copy of the same role walked in.
    """
    itviec = _job("itviec", "1", "Backend Engineer")
    for day in range(0, 20):
        _persist(db, cfg, [itviec], now=NOW + timedelta(days=day))

    stats = _persist(
        db, cfg, [_job("topcv", "9", "Backend Engineer")], now=NOW + timedelta(days=19)
    )

    assert stats.inserted == 0
    assert stats.duplicates == 1
    assert _ids(db) == {"itviec:1"}


def test_a_posting_nobody_has_seen_since_stops_holding_the_key(db, cfg):
    """The other half: the window still expires when the posting really is gone.

    Without this, the fix above would turn a 14-day suppression into a permanent
    one, and a role that came back six months later could never be re-added.
    """
    _persist(db, cfg, [_job("itviec", "1", "Backend Engineer")])

    stats = _persist(
        db, cfg, [_job("topcv", "9", "Backend Engineer")], now=NOW + timedelta(days=15)
    )

    assert stats.inserted == 1
    assert _ids(db) == {"itviec:1", "topcv:9"}


def test_dedup_days_zero_keeps_every_boards_version(db, cfg):
    stats = _persist(
        db,
        cfg,
        [_job("itviec", "1", "Backend Engineer"), _job("topcv", "9", "Backend Engineer")],
        dedup_days=0,
    )

    assert (stats.inserted, stats.duplicates) == (2, 0)


# --------------------------------------------------------------------------- #
# C. levels named on both sides are different roles
# --------------------------------------------------------------------------- #
def test_senior_junior_and_intern_of_one_title_are_three_jobs(db, cfg):
    """The silent-loss case: all three used to collapse to 'acme|backend engineer'.

    Two of the three were dropped, counted only in ``stats.duplicates``, and left
    no record anywhere that they had ever been scraped.
    """
    stats = _persist(
        db,
        cfg,
        [
            _job("itviec", "1", "Senior Backend Engineer"),
            _job("itviec", "2", "Junior Backend Engineer"),
            _job("itviec", "3", "Intern Backend Engineer"),
        ],
    )

    assert stats.inserted == 3
    assert stats.duplicates == 0


def test_a_title_that_names_no_level_still_matches_one_that_does(db, cfg):
    """The original intent, kept.

    A board writing "Backend Engineer" where another writes "Junior Backend
    Engineer" has not announced a different job — it has left the level out. Only
    a level stated on *both* sides is evidence of a real difference.
    """
    stats = _persist(
        db,
        cfg,
        [
            _job("itviec", "1", "Junior Backend Engineer"),
            _job("topcv", "9", "Backend Engineer"),
        ],
    )

    assert (stats.inserted, stats.duplicates) == (1, 1)


def test_house_style_is_not_a_different_level(db, cfg):
    """ "Sr." and "Lead" mean the level ``infer_level`` already calls senior.

    If these split, a job's ``level`` column would say "senior" while its dedup
    key insisted it was a different role from the senior posting next to it.
    """
    stats = _persist(
        db,
        cfg,
        [
            _job("itviec", "1", "Senior Backend Engineer"),
            _job("topcv", "9", "Sr. Backend Engineer"),
            _job("vietnamworks", "5", "Lead Backend Engineer"),
        ],
    )

    assert (stats.inserted, stats.duplicates) == (1, 2)


# --------------------------------------------------------------------------- #
# D. nothing disappears silently; the copy with a JD wins
# --------------------------------------------------------------------------- #
def test_a_skipped_posting_is_recorded_on_the_row_that_displaced_it(db, cfg):
    _persist(db, cfg, [_job("itviec", "1", "Backend Engineer")])
    _persist(db, cfg, [_job("topcv", "9", "Backend Engineer")])

    trace = db.get(Job, "itviec:1").payload["dedup"]["suppressed"]
    assert [e["id"] for e in trace] == ["topcv:9"]
    assert trace[0]["url"] == "https://topcv.example/9"


def test_the_trace_survives_the_next_re_crawl(db, cfg):
    """``_refresh`` overwrites payload with what the scraper produced, and the
    scraper knows nothing about suppressed siblings. A trace erased by the next
    run is a trace that does not exist."""
    itviec = _job("itviec", "1", "Backend Engineer")
    _persist(db, cfg, [itviec])
    _persist(db, cfg, [_job("topcv", "9", "Backend Engineer")])

    _persist(db, cfg, [itviec], now=NOW + timedelta(days=1))

    assert db.get(Job, "itviec:1").payload["dedup"]["suppressed"][0]["id"] == "topcv:9"


def test_the_copy_with_a_real_jd_is_kept_even_when_the_empty_one_arrived_first(db, cfg):
    """The LinkedIn-alert case.

    Alert mail carries a title and no description, and it usually lands before
    the board crawl. Suppressing the only copy the tailor can actually read, in
    favour of one flagged ``needs_jd``, is worse than carrying an extra row.
    """
    _persist(db, cfg, [_job("linkedin", "abc", "Backend Engineer", jd="", needs_jd=True)])

    stats = _persist(db, cfg, [_job("itviec", "1", "Backend Engineer", jd=FULL_JD)])

    assert (stats.inserted, stats.superseded, stats.duplicates) == (1, 1, 0)
    assert _ids(db) == {"linkedin:abc", "itviec:1"}
    # Both halves of the link, so either row explains the other's existence.
    assert db.get(Job, "itviec:1").payload["dedup"]["supersedes"]["id"] == "linkedin:abc"
    assert db.get(Job, "linkedin:abc").payload["dedup"]["superseded_by"]["id"] == "itviec:1"


def test_both_copies_can_arrive_in_one_batch(db, cfg):
    """The same case with no flush in between, which is the ordinary one.

    A single crawl pass reads the LinkedIn alerts and the ITviec board into one
    list, so the incumbent ``_record_superseded_by`` annotates is a row still
    *pending* — added to the session but not yet written. The annotation has to
    reach the database as part of that row's INSERT rather than being dropped or
    provoking a second write.
    """
    stats = _persist(
        db,
        cfg,
        [
            _job("linkedin", "abc", "Backend Engineer", jd="", needs_jd=True),
            _job("itviec", "1", "Backend Engineer", jd=FULL_JD),
        ],
    )

    assert (stats.inserted, stats.superseded, stats.duplicates) == (2, 1, 0)

    # Re-read from the database rather than the identity map, or this would pass
    # on the in-memory objects the test just built regardless of what was written.
    db.commit()
    db.expunge_all()
    assert db.get(Job, "linkedin:abc").payload["dedup"]["superseded_by"]["id"] == "itviec:1"
    assert db.get(Job, "itviec:1").payload["dedup"]["supersedes"]["id"] == "linkedin:abc"


def test_the_jd_less_row_is_annotated_not_demoted(db, cfg):
    """It may already be shortlisted or applied to. Dedup does not get a vote."""
    _persist(db, cfg, [_job("linkedin", "abc", "Backend Engineer", jd="", needs_jd=True)])
    before = db.get(Job, "linkedin:abc").status

    _persist(db, cfg, [_job("itviec", "1", "Backend Engineer")])

    assert db.get(Job, "linkedin:abc").status == before


def test_a_second_jd_less_copy_does_not_displace_the_full_one(db, cfg):
    """Once a full-JD row exists it is the incumbent, whatever order the rest
    arrive in — otherwise every thin sibling would let another row in."""
    _persist(db, cfg, [_job("linkedin", "abc", "Backend Engineer", jd="", needs_jd=True)])
    _persist(db, cfg, [_job("itviec", "1", "Backend Engineer", jd=FULL_JD)])

    stats = _persist(db, cfg, [_job("arbeitnow", "7", "Backend Engineer", jd="")])

    assert (stats.inserted, stats.superseded, stats.duplicates) == (0, 0, 1)


def test_two_thin_copies_do_not_supersede_each_other(db, cfg):
    """The rule is "has a JD the other lacks", not "has one more character"."""
    short = "Java role. " * 3
    assert len(short) < THIN_JD_CHARS

    _persist(db, cfg, [_job("linkedin", "abc", "Backend Engineer", jd="", needs_jd=True)])
    stats = _persist(db, cfg, [_job("topcv", "9", "Backend Engineer", jd=short)])

    assert (stats.inserted, stats.duplicates) == (0, 1)
