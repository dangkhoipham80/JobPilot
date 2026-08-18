"""Job quality signals: why the score, and is the posting worth answering.

Nothing here filters a job out. These are annotations a person argues with, so
each one has to be defensible on its own — a flag you can't explain is a flag
you can't disagree with.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from jobpilot.crawler.normalize import VN_TZ, normalize
from jobpilot.crawler.quality import THIN_JD_CHARS, describe, flags_for, stack_coverage
from jobpilot.crawler.types import RawJob
from jobpilot.config import ApplyCfg, Config, CrawlCfg, CvCfg

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=VN_TZ)
STACKS = ["Java", "Spring Boot", "Kafka"]


# --------------------------------------------------------------------------- #
# explaining the score
# --------------------------------------------------------------------------- #
def test_coverage_names_both_sides_of_the_score():
    matched, missing = stack_coverage("Java and Spring Boot role", STACKS)
    assert matched == ["Java", "Spring Boot"]
    assert missing == ["Kafka"]


def test_the_explanation_agrees_with_the_number_it_explains():
    """If these two used different rules, the explanation would be a second,
    competing score — and the one shown to the user would be the wrong one."""
    from jobpilot.crawler.normalize import stack_match_score

    hay = "Senior Java engineer, some Kafka exposure"
    matched, missing = stack_coverage(hay, STACKS)
    assert round(len(matched) / len(STACKS), 3) == stack_match_score(hay, STACKS)
    assert len(matched) + len(missing) == len(STACKS)  # nothing falls between them


def test_coverage_is_case_insensitive_and_survives_an_empty_stack_list():
    assert stack_coverage("JAVA developer", ["java"])[0] == ["java"]
    assert stack_coverage("anything", []) == ([], [])


# --------------------------------------------------------------------------- #
# is the posting real
# --------------------------------------------------------------------------- #
def test_a_healthy_recent_posting_gets_no_flags():
    assert flags_for(description_md="x" * 2000, posted_at=NOW - timedelta(days=2), now=NOW) == []


def test_an_old_posting_is_flagged_stale():
    flags = flags_for(description_md="x" * 2000, posted_at=NOW - timedelta(days=90), now=NOW)
    assert flags == ["stale"]


def test_stale_respects_the_configured_window():
    old = NOW - timedelta(days=50)
    assert "stale" in flags_for(description_md="x" * 900, posted_at=old, now=NOW, stale_days=45)
    assert "stale" not in flags_for(description_md="x" * 900, posted_at=old, now=NOW, stale_days=60)


def test_unknown_age_is_not_old_age():
    """A source that publishes no date must not have its jobs quietly aged out —
    "undated" and "stale" are different claims, the way pages=None and pages=0
    are."""
    flags = flags_for(description_md="x" * 2000, posted_at=None, now=NOW)
    assert flags == ["undated"]
    assert "stale" not in flags


def test_a_headline_with_no_body_is_flagged_thin():
    flags = flags_for(description_md="Backend dev wanted", posted_at=NOW, now=NOW)
    assert "thin_jd" in flags


def test_thin_jd_boundary():
    assert "thin_jd" not in flags_for(description_md="x" * THIN_JD_CHARS, posted_at=NOW, now=NOW)
    assert "thin_jd" in flags_for(description_md="x" * (THIN_JD_CHARS - 1), posted_at=NOW, now=NOW)


def test_no_jd_supersedes_thin_jd():
    """A LinkedIn alert has no description by design. Reporting it as both
    missing and short is one fact stated twice."""
    flags = flags_for(description_md="", posted_at=NOW, needs_jd=True, now=NOW)
    assert flags == ["no_jd"]


def test_every_flag_has_something_a_person_can_do_about_it():
    for flag in ("no_jd", "thin_jd", "stale", "undated"):
        assert describe(flag) != flag
        assert len(describe(flag)) > 20


# --------------------------------------------------------------------------- #
# the whole thing, through normalize
# --------------------------------------------------------------------------- #
def _cfg(**kw) -> Config:
    return Config(crawl=CrawlCfg(stacks=STACKS, **kw), apply=ApplyCfg(), cv=CvCfg())


def test_normalize_attaches_the_explanation_to_the_payload():
    raw = RawJob(
        source="topcv",
        native_id="1",
        url="https://x/1",
        title="Java Backend Engineer",
        company="ACME",
        posted_raw="2026-08-01",
        description_md="We use Java and Spring Boot for our services. " * 20,
    )
    nj = normalize(raw, _cfg(), NOW)
    quality = nj.payload["quality"]
    assert quality["matched"] == ["Java", "Spring Boot"]
    assert quality["missing"] == ["Kafka"]
    assert quality["flags"] == []
    # The explanation must add up to the score that sits beside it.
    assert nj.match_score == round(len(quality["matched"]) / len(STACKS), 3)


def test_normalize_flags_an_old_thin_posting():
    raw = RawJob(
        source="topcv",
        native_id="2",
        url="https://x/2",
        title="Java dev",
        company="ACME",
        posted_raw="2026-01-01",
        description_md="Hiring now.",
    )
    quality = normalize(raw, _cfg(), NOW).payload["quality"]
    assert set(quality["flags"]) == {"thin_jd", "stale"}


# --------------------------------------------------------------------------- #
# jobs crawled before any of this existed
# --------------------------------------------------------------------------- #
def test_backfill_annotates_old_rows_and_is_idempotent(session_factory):
    """The jobs that need the flags most are the ones that will never be
    re-crawled — LinkedIn alerts carry no description at all."""
    from jobpilot.crawler.quality import backfill
    from jobpilot.store.models import Job, JobStatus

    with session_factory() as db:
        db.add(
            Job(
                id="linkedin:1",
                source="linkedin",
                url="u",
                title="Java Backend Developer",
                company="ACME",
                status=JobStatus.DISCOVERED,
                match_score=0.0,
                payload={"title": "Java Backend Developer", "description_md": "", "needs_jd": True},
            )
        )
        db.commit()

        assert backfill(db, _cfg(), now=NOW) == 1
        job = db.get(Job, "linkedin:1")
        # An alert email carries neither a description nor a date, and both are
        # worth saying: one blocks tailoring, the other blocks the 🔥 flag.
        assert job.payload["quality"]["flags"] == ["no_jd", "undated"]
        assert job.payload["quality"]["matched"] == ["Java"]

        # Running it twice must cost nothing and change nothing.
        assert backfill(db, _cfg(), now=NOW) == 0


def test_the_orm_row_exposes_quality_so_both_routes_get_it(session_factory):
    """FastAPI serializes ORM rows straight through `from_attributes`, so this
    property is the single place the list and the detail response both read."""
    from jobpilot.store.models import Job, JobStatus

    job = Job(
        id="x:1",
        source="x",
        url="u",
        title="t",
        company="c",
        status=JobStatus.DISCOVERED,
        match_score=0.0,
        payload={"quality": {"matched": ["Java"], "missing": [], "flags": ["stale"]}},
    )
    assert job.quality == {"matched": ["Java"], "missing": [], "flags": ["stale"]}
    assert Job(id="y", source="s", url="u", title="t", company="c", payload={}).quality is None


# --------------------------------------------------------------------------- #
# "not seen lately" (found the expensive way: a job expired 16 days before the
# apply, and every signal needed to say so was already in the database)
# --------------------------------------------------------------------------- #
from datetime import datetime, timezone  # noqa: E402

from jobpilot.crawler.quality import (  # noqa: E402
    UNSEEN_PASSES,
    missed_passes,
    unseen_flag,
)

_T0 = datetime(2026, 8, 2, tzinfo=timezone.utc)


def _passes(*days: int) -> list[datetime]:
    return sorted((_T0 + timedelta(days=d) for d in days), reverse=True)


def test_a_posting_seen_on_the_latest_pass_is_not_flagged():
    assert unseen_flag(_passes(0, 6, 15), last_seen=_T0 + timedelta(days=15)) == []


def test_one_missed_pass_is_not_enough():
    """A live posting falls out of view as soon as jobs_per_site newer ones
    arrive, so a single miss says nothing."""
    assert missed_passes(_passes(0, 6), last_seen=_T0) == 1
    assert unseen_flag(_passes(0, 6), last_seen=_T0) == []


def test_two_missed_passes_are_worth_saying():
    """The real case: crawled 2 Aug, the source crawled again on the 8th and the
    17th, and it never came back."""
    assert missed_passes(_passes(0, 6, 15), last_seen=_T0) == 2
    assert unseen_flag(_passes(0, 6, 15), last_seen=_T0) == ["not_seen"]
    assert UNSEEN_PASSES == 2


def test_never_having_looked_again_is_not_evidence():
    """If the source has not been crawled since, the posting's absence means
    nothing — the same distinction as undated vs stale."""
    assert unseen_flag(_passes(0), last_seen=_T0) == []
    assert unseen_flag([], last_seen=_T0) == []


def test_an_unseen_last_seen_at_is_not_flagged():
    assert unseen_flag(_passes(0, 6, 15), last_seen=None) == []


def test_the_wording_admits_both_explanations():
    """Naming it "gone" would claim more than the data supports; naming it only
    "unseen" would hide why anyone should care."""
    text = describe("not_seen").lower()
    assert "taken down" in text and "sample" in text


def test_crawl_passes_ignores_a_pass_that_came_back_empty(session_factory):
    """A crawl that errored or was blocked proves nothing about whether a
    posting is still listed. Counting it would flag live jobs every time a
    source had a bad day."""
    from jobpilot.crawler.quality import crawl_passes
    from jobpilot.store.models import Run
    from jobpilot.timeutil import vn_now

    now = vn_now()
    with session_factory() as db:
        db.add_all([
            Run(kind="crawl", started_at=now - timedelta(days=3),
                stats={"sites": {"itviec": {"ok": True, "fetched": 10}}}),
            Run(kind="crawl", started_at=now - timedelta(days=2),
                stats={"sites": {"itviec": {"ok": False, "error": "blocked", "fetched": 0}}}),
            Run(kind="crawl", started_at=now - timedelta(days=1),
                stats={"sites": {"itviec": {"ok": True, "fetched": 0}}}),
        ])
        db.commit()
        passes = crawl_passes(db, ["itviec"]).get("itviec", [])

    assert len(passes) == 1, "only the pass that actually fetched something counts"


def test_crawl_passes_does_not_come_from_last_seen_at(session_factory):
    """last_seen_at is overwritten on every sighting, so a pass survives there
    only if it left a job nobody ever saw again. On real data the 8 August pass
    fetched ten ITviec jobs, updated four, and had disappeared from those
    timestamps by the 17th -- while being exactly the pass the signal needed."""
    from jobpilot.crawler.quality import crawl_passes
    from jobpilot.store.models import Job, Run
    from jobpilot.timeutil import vn_now

    now = vn_now()
    with session_factory() as db:
        db.add(Run(kind="crawl", started_at=now - timedelta(days=5),
                   stats={"sites": {"itviec": {"ok": True, "fetched": 10}}}))
        # Every job's sighting was later overwritten, so last_seen_at carries no
        # trace of that pass at all.
        db.add(Job(id="itviec:x", source="itviec", title="T", company="C",
                   crawled_at=now, last_seen_at=now))
        db.commit()
        passes = crawl_passes(db, ["itviec"]).get("itviec", [])

    assert len(passes) == 1, "the pass must still be visible via runs"
