"""Which source is worth crawling — PLAN.md §9.1 slot 20.

Every test here pins a decision that has a plausible wrong version, because the
wrong version is the one that ships quietly: a rate built from ``current``
instead of ``reached`` still renders, a "33%" from three applications still
looks like a measurement, and an unanswered application folded into the reply
median still produces a number.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from jobpilot.analytics.outcomes import (
    MIN_SAMPLE,
    REPEAT_MIN_POSTINGS,
    outcome_analytics,
    repeat_postings,
)
from jobpilot.apply.outcome import INTERVIEW, OFFER, REJECTED, REPLIED, record_outcome
from jobpilot.store.models import Application, Job, JobStatus
from jobpilot.timeutil import VN_TZ

NOW = datetime(2026, 8, 5, 9, 0, tzinfo=VN_TZ)


def _job(db, job_id: str, *, source="itviec", level="mid", company="ACME", title="Java Backend"):
    if db.get(Job, job_id) is None:
        db.add(
            Job(
                id=job_id,
                source=source,
                url=f"https://example.test/{job_id}",
                title=title,
                company=company,
                level=level,
                status=JobStatus.SUBMITTED,
                match_score=1.0,
            )
        )
        db.commit()


def _sent(db, job_id: str, *, channel="email", days_ago=10, result="success", **job_kw):
    """One application that really went out."""
    _job(db, job_id, **job_kw)
    app = Application(
        job_id=job_id,
        channel=channel,
        result=result,
        submitted_at=NOW - timedelta(days=days_ago),
    )
    db.add(app)
    db.commit()
    return app


def _bucket(split: dict, key: str) -> dict:
    return next(row for row in split["rows"] if row["key"] == key)


# --------------------------------------------------------------------------- #
# rates come from the event log, not from the current stage
# --------------------------------------------------------------------------- #
def test_an_interview_still_counts_after_the_rejection(session_factory):
    """The whole reason ``reached`` exists.

    An application that interviewed and was then rejected sits in ``current``
    only under ``rejected``. If the split counted that way, the interview rate
    would fall at the exact moment the search started going well.
    """
    with session_factory() as db:
        app = _sent(db, "itviec:1")
        record_outcome(db, app.id, INTERVIEW)
        record_outcome(db, app.id, REJECTED)

        source = outcome_analytics(db)["by_source"]
        assert _bucket(source, "itviec")["interviewed"] == 1
        assert _bucket(source, "itviec")["answered"] == 1


def test_an_interview_counts_as_an_answer_without_an_explicit_reply(session_factory):
    """Nobody types "they replied" and then "they invited me" for one email."""
    with session_factory() as db:
        app = _sent(db, "itviec:1")
        record_outcome(db, app.id, INTERVIEW)

        assert _bucket(outcome_analytics(db)["by_source"], "itviec")["answered"] == 1


def test_a_retracted_event_stops_counting(session_factory):
    """A mis-click that has been taken back must not hold up a rate."""
    from jobpilot.apply.outcome import retract_outcome_event

    with session_factory() as db:
        app = _sent(db, "itviec:1")
        event, _ = record_outcome(db, app.id, REPLIED)
        retract_outcome_event(db, app.id, event.id)

        assert _bucket(outcome_analytics(db)["by_source"], "itviec")["answered"] == 0


def test_only_applications_that_really_went_out_are_counted(session_factory):
    """A dry run sent nothing, so there was nobody who could have answered.

    Counting it would inflate the denominator every rate here divides by.
    """
    with session_factory() as db:
        _sent(db, "itviec:1")
        _sent(db, "itviec:2", result="dry_run")

        assert outcome_analytics(db)["total_sent"] == 1


# --------------------------------------------------------------------------- #
# small samples report counts, never percentages
# --------------------------------------------------------------------------- #
def test_a_thin_bucket_reports_no_rate_at_all(session_factory):
    """One reply out of three is three applications, not "33%".

    Slicing by source is exactly what makes samples small, so the suppression
    has to live in the split rather than only in the whole-corpus number.
    """
    with session_factory() as db:
        for i in range(3):
            app = _sent(db, f"itviec:{i}")
            if i == 0:
                record_outcome(db, app.id, REPLIED)

        bucket = _bucket(outcome_analytics(db)["by_source"], "itviec")
        assert bucket["sent"] == 3
        assert bucket["answered"] == 1
        assert bucket["thin"] is True
        assert bucket["reply_rate"] is None
        assert bucket["interview_rate"] is None


def test_a_bucket_at_the_threshold_does_report_a_rate(session_factory):
    with session_factory() as db:
        for i in range(MIN_SAMPLE):
            app = _sent(db, f"itviec:{i}")
            if i < 2:
                record_outcome(db, app.id, REPLIED)

        bucket = _bucket(outcome_analytics(db)["by_source"], "itviec")
        assert bucket["sent"] == MIN_SAMPLE
        assert bucket["thin"] is False
        assert bucket["reply_rate"] == round(2 / MIN_SAMPLE, 4)


def test_each_source_is_judged_on_its_own_sample(session_factory):
    """A big board crossing the threshold must not lend its confidence to a
    small one — the comparison is the whole point of the page."""
    with session_factory() as db:
        for i in range(MIN_SAMPLE):
            _sent(db, f"itviec:{i}", source="itviec")
        _sent(db, "topcv:1", source="topcv")

        split = outcome_analytics(db)["by_source"]
        assert _bucket(split, "itviec")["thin"] is False
        assert _bucket(split, "topcv")["thin"] is True
        assert _bucket(split, "topcv")["reply_rate"] is None


def test_a_missing_level_becomes_its_own_bucket(session_factory):
    """Dropping unknowns would make the buckets sum to less than the total with
    nothing on the page to explain the gap."""
    with session_factory() as db:
        _sent(db, "itviec:1", level=None)
        _sent(db, "itviec:2", level="senior")

        split = outcome_analytics(db)["by_level"]
        assert _bucket(split, "unknown")["sent"] == 1
        assert split["covered"] == 1
        assert split["total"] == 2


# --------------------------------------------------------------------------- #
# time to first reply
# --------------------------------------------------------------------------- #
def test_an_unanswered_application_is_not_a_slow_reply(session_factory):
    """It is left out of the median and counted separately.

    Folding it in as "so far N days" would make the number drift worse every
    day nothing happened, which is the opposite of what it measures.
    """
    with session_factory() as db:
        answered = _sent(db, "itviec:1", days_ago=10)
        record_outcome(db, answered.id, REPLIED, occurred_at=NOW - timedelta(days=8))
        _sent(db, "itviec:2", days_ago=200)  # still silent

        timing = outcome_analytics(db)["timing"]
        assert timing["answered"] == 1
        assert timing["still_waiting"] == 1
        assert timing["median_days"] == 2.0


def test_the_first_answer_wins_not_the_latest(session_factory):
    """Time-to-*first*-reply. A later interview must not overwrite the reply
    that actually broke the silence."""
    with session_factory() as db:
        app = _sent(db, "itviec:1", days_ago=30)
        record_outcome(db, app.id, REPLIED, occurred_at=NOW - timedelta(days=28))
        record_outcome(db, app.id, INTERVIEW, occurred_at=NOW - timedelta(days=10))

        assert outcome_analytics(db)["timing"]["median_days"] == 2.0


def test_an_application_with_no_submitted_at_is_undated_not_instant(session_factory):
    """Not knowing when it went out is not the same as a zero-day reply."""
    with session_factory() as db:
        app = _sent(db, "itviec:1")
        app.submitted_at = None
        db.commit()
        record_outcome(db, app.id, REPLIED)

        timing = outcome_analytics(db)["timing"]
        assert timing["undated"] == 1
        assert timing["answered"] == 0
        assert timing["median_days"] is None


def test_no_applications_gives_no_median(session_factory):
    """``None``, not ``0.0`` — zero days would be a claim about the world."""
    with session_factory() as db:
        timing = outcome_analytics(db)["timing"]
        assert timing["median_days"] is None
        assert timing["thin"] is True


def test_an_answer_dated_before_the_send_is_dropped_not_clamped(session_factory):
    """A mail header with a skewed clock must not become the fastest reply.

    Clamping to ``0`` would report a same-day answer that never happened, and
    keeping the raw delta would report a *negative* wait — a median of ``-0.02``
    reads as a rounding artefact rather than as broken data. Both hide the same
    thing, so the pair is dropped and counted where it can be seen.
    """
    with session_factory() as db:
        app = _sent(db, "itviec:1", days_ago=10)
        record_outcome(db, app.id, REPLIED, occurred_at=NOW - timedelta(days=12))

        timing = outcome_analytics(db)["timing"]
        assert timing["inconsistent"] == 1
        assert timing["answered"] == 0
        assert timing["median_days"] is None
        assert timing["fastest_days"] is None


def test_a_good_answer_survives_a_neighbouring_bad_one(session_factory):
    """Dropping the broken pair must not drop the corpus around it."""
    with session_factory() as db:
        bad = _sent(db, "itviec:1", days_ago=10)
        record_outcome(db, bad.id, REPLIED, occurred_at=NOW - timedelta(days=12))
        good = _sent(db, "itviec:2", days_ago=10)
        record_outcome(db, good.id, REPLIED, occurred_at=NOW - timedelta(days=6))

        timing = outcome_analytics(db)["timing"]
        assert timing["inconsistent"] == 1
        assert timing["answered"] == 1
        assert timing["median_days"] == 4.0


# --------------------------------------------------------------------------- #
# repeat postings — a signal, never a verdict
# --------------------------------------------------------------------------- #
def test_one_posting_is_not_a_repeat(session_factory):
    with session_factory() as db:
        _job(db, "itviec:1")
        assert repeat_postings(db)["rows"] == []


def test_two_postings_are_ordinary_hiring(session_factory):
    """The threshold exists so that a company with two openings is not accused
    of anything."""
    with session_factory() as db:
        _job(db, "itviec:1")
        _job(db, "itviec:2")
        assert repeat_postings(db)["total_groups"] == 0


def test_a_repeatedly_reposted_ad_is_reported_with_its_shape(session_factory):
    with session_factory() as db:
        for i in range(REPEAT_MIN_POSTINGS):
            _job(db, f"itviec:{i}")
            db.get(Job, f"itviec:{i}").posted_at = NOW - timedelta(days=30 * i)
        db.commit()

        found = repeat_postings(db)
        assert found["total_groups"] == 1
        row = found["rows"][0]
        assert row["postings"] == REPEAT_MIN_POSTINGS
        assert row["span_days"] == 30 * (REPEAT_MIN_POSTINGS - 1)
        # Reported as shape, not as an accusation.
        assert "ghost" not in str(row).lower()


def test_accented_company_names_are_one_employer(session_factory):
    """``"Công ty TNHH X"`` and ``"CONG TY TNHH X"`` are the same company.

    Without folding they are two groups of one, and neither ever crosses the
    repeat threshold — the detector silently stops detecting.
    """
    with session_factory() as db:
        for i, company in enumerate(["Công ty TNHH X", "CONG TY TNHH X", "công ty tnhh x"]):
            _job(db, f"itviec:{i}", company=company)

        assert repeat_postings(db)["total_groups"] == 1


def test_a_senior_and_a_junior_opening_are_not_one_ad_reposted(session_factory):
    """The deliberate difference from ``crawler.text.dedup_key``.

    Both grouping rules now come from the same pair of helpers, separated only
    by ``strip_level``. Cross-source dedup strips the level, because a board
    omitting "Junior" has not announced a different job; this does not, because
    an employer hiring at three levels is not running one ad three times.
    """
    with session_factory() as db:
        for i, title in enumerate(
            ["Senior Java Backend", "Junior Java Backend", "Intern Java Backend"]
        ):
            _job(db, f"itviec:{i}", title=title)

        assert repeat_postings(db)["total_groups"] == 0


def test_a_parenthetical_suffix_does_not_hide_a_repost(session_factory):
    """Grouping shares the crawler's normalisation, so "(Java)" is decoration.

    These were three groups of one under the old hand-written ``fold``-only
    rule, and three groups of one never reach the repeat threshold.
    """
    with session_factory() as db:
        for i, title in enumerate(
            ["Java Backend", "Java Backend (Spring Boot)", "Java  Backend!"]
        ):
            _job(db, f"itviec:{i}", title=title)

        assert repeat_postings(db)["total_groups"] == 1


def test_different_titles_at_one_company_are_not_a_repeat(session_factory):
    with session_factory() as db:
        for i, title in enumerate(["Java Backend", "React Frontend", "Data Engineer"]):
            _job(db, f"itviec:{i}", title=title)

        assert repeat_postings(db)["total_groups"] == 0


def test_undated_postings_give_an_unknown_span_not_a_zero(session_factory):
    """``span_days=0`` would read as "all posted the same day", which is a
    different and much stronger claim than "we don't know"."""
    with session_factory() as db:
        for i in range(REPEAT_MIN_POSTINGS):
            _job(db, f"itviec:{i}")

        row = repeat_postings(db)["rows"][0]
        assert row["span_days"] is None
        assert row["undated_postings"] == REPEAT_MIN_POSTINGS


def test_a_capped_list_declares_what_it_dropped(session_factory):
    """A page showing 2 of 5 groups has to be able to say so — a silent
    truncation reads as "that's all of them"."""
    with session_factory() as db:
        for company in range(5):
            for i in range(REPEAT_MIN_POSTINGS):
                _job(db, f"itviec:{company}-{i}", company=f"ACME {company}")

        found = repeat_postings(db, limit=2)
        assert found["total_groups"] == 5
        assert found["shown"] == 2
        assert len(found["rows"]) == 2


# --------------------------------------------------------------------------- #
# over HTTP
# --------------------------------------------------------------------------- #
def test_the_endpoint_serves_the_split(session_factory):
    """The contract the dashboard reads. Pinned end to end because a schema
    that silently drops ``thin`` would let the page render a percentage the
    module went out of its way to suppress."""
    from fastapi.testclient import TestClient

    from jobpilot.api.deps import get_db
    from jobpilot.api.main import app as fastapi_app
    from jobpilot.config import get_secrets

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    with session_factory() as db:
        sent = _sent(db, "itviec:1")
        record_outcome(db, sent.id, OFFER)

    fastapi_app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(fastapi_app)
        res = client.get("/stats/outcomes", headers={"X-API-Token": get_secrets().jobpilot_api_token})
        assert res.status_code == 200
        body = res.json()
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)

    assert body["total_sent"] == 1
    assert body["min_sample"] == MIN_SAMPLE
    bucket = _bucket(body["by_source"], "itviec")
    assert bucket["offered"] == 1
    # One application is not a rate, and the wire format has to say so.
    assert bucket["thin"] is True
    assert bucket["reply_rate"] is None


def test_the_endpoint_serves_an_empty_corpus(session_factory):
    """A fresh DB has to survive the schema, not just the aggregation.

    The unit tests cover the empty aggregate; this covers *serialising* it. A
    day-one user opens the dashboard before any application exists, and a
    required field that is only ever populated with data would turn that first
    visit into a 500.
    """
    from fastapi.testclient import TestClient

    from jobpilot.api.deps import get_db
    from jobpilot.api.main import app as fastapi_app
    from jobpilot.config import get_secrets

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(fastapi_app)
        res = client.get("/stats/outcomes", headers={"X-API-Token": get_secrets().jobpilot_api_token})
        assert res.status_code == 200
        body = res.json()
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)

    assert body["total_sent"] == 0
    assert body["by_source"]["rows"] == []
    # Says so out loud rather than rendering an empty table with no explanation.
    assert body["by_source"]["note"]
    assert body["timing"]["median_days"] is None
    assert body["timing"]["inconsistent"] == 0
    assert body["repeats"]["rows"] == []
    assert body["repeats"]["total_groups"] == 0
