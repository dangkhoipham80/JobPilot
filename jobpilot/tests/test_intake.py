"""Paste a JD in, have a model read it, and ask how well it fits.

The interesting assertions here are all about what the feature refuses to do:
the stored description is the user's paste and never the model's retelling, a
level the column's vocabulary doesn't contain is dropped rather than written,
the quality flags come from arithmetic rather than from the model, and a fit
report never touches ``match_score`` on a job that has been tailored.
"""

from __future__ import annotations

import pytest

from jobpilot.api.deps import get_db
from jobpilot.api.main import app
from jobpilot.api.routes.intake import get_engine
from jobpilot.config import get_secrets
from jobpilot.crawler.normalize import LEVELS
from jobpilot.crawler.quality import THIN_JD_CHARS
from jobpilot.cv import store as cv_store
from jobpilot.cv.sample import sample_document
from jobpilot.intake import service
from jobpilot.intake.engine import FixtureIntakeEngine, IntakeError
from jobpilot.intake.prompt import MAX_JD_CHARS
from jobpilot.intake.schema import FitReport, JdExtract, JdSections
from jobpilot.store.models import Job, JobStatus
from jobpilot.tailor.schema import Requirement
from jobpilot.tests.conftest import api_client

AUTH = {"X-API-Token": get_secrets().jobpilot_api_token}

# Long enough to clear THIN_JD_CHARS, so "thin_jd" only shows up in the test
# that is actually about a short posting.
JD_BODY = (
    "We are hiring a Senior Backend Engineer at ACME Corp in Ho Chi Minh City.\n"
    "You will build and operate Java and Spring Boot services backed by "
    "PostgreSQL, own them in production, and work with a small platform team.\n"
) + ("Responsibilities include designing REST APIs and reviewing pull requests. " * 8)

EXTRACT = JdExtract(
    title="Senior Backend Engineer",
    company="ACME Corp",
    location="Ho Chi Minh City",
    salary="30 - 45 triệu",
    level="senior",
    employment_type="full-time",
    work_mode="hybrid",
    skills=["Java", "Spring Boot", "PostgreSQL"],
    apply_email="jobs@acme.example",
    language="en",
)

SECTIONS = JdSections(
    role="Build and operate Java services for the payments platform.",
    responsibilities=["Design REST APIs", "Own services in production"],
    must_have=["4+ years of backend Java", "Spring Boot"],
    nice_to_have=["Docker, Kubernetes is a plus"],
    soft_skills=["Clear written communication"],
    outputs=[],
    benefits=["13th month salary", "Health insurance"],
    how_to_apply="Send your CV to jobs@acme.example",
)

REPORT = FitReport(
    match_score=0.72,
    verdict="fair",
    summary="Your Java and Spring Boot work lines up; you have no Kafka on the CV.",
    requirements=[
        Requirement(text="Java", kind="must_have", status="HAVE", evidence="experience: ACME"),
        Requirement(text="Kafka", kind="must_have", status="MISSING", evidence=""),
    ],
    dealbreakers=[],
    concerns=["The posting never names the end client."],
)


@pytest.fixture
def intake_engine() -> FixtureIntakeEngine:
    return FixtureIntakeEngine(extracted=EXTRACT, parsed=SECTIONS, report=REPORT)


@pytest.fixture
def client(session_factory, intake_engine):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    with session_factory() as s:
        cv_store.ensure_master(s)
        cv_store.save_version(s, cv_store.MASTER_SCOPE, sample_document(), author="user")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_engine] = lambda: intake_engine
    c = api_client(app)
    yield c
    app.dependency_overrides.clear()


def _save(client, **overrides) -> dict:
    """Create a job through the ordinary manual-add endpoint."""
    body = {
        "url": "https://jobs.example.com/backend-engineer",
        "title": "Senior Backend Engineer",
        "company": "ACME Corp",
        "location": "Ho Chi Minh City",
        "salary": "30 - 45 triệu",
        "skills": ["Java", "Spring Boot"],
        "description_md": JD_BODY,
    }
    body.update(overrides)
    r = client.post("/jobs", json=body, headers=AUTH)
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# reading a paste
# --------------------------------------------------------------------------- #


def test_intake_requires_a_token(client):
    assert client.post("/jobs/intake", json={"text": JD_BODY}).status_code == 401


def test_a_paste_comes_back_as_form_fields(client, intake_engine):
    r = client.post("/jobs/intake", json={"text": JD_BODY}, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Senior Backend Engineer"
    assert body["company"] == "ACME Corp"
    assert body["salary"] == "30 - 45 triệu"
    assert body["skills"] == ["Java", "Spring Boot", "PostgreSQL"]
    assert body["apply_email"] == "jobs@acme.example"
    assert intake_engine.extract_calls, "the engine should have been asked"


def test_the_stored_description_is_the_users_paste_not_the_models(client, intake_engine):
    """The one rule of extraction: the JD is evidence, so it stays verbatim.

    Every guardrail downstream reads ``description_md`` as the thing the CV is
    checked against. If a model's retelling could land there, the tailor would
    be checking a CV against a paraphrase and calling it the posting.
    """
    r = client.post("/jobs/intake", json={"text": JD_BODY}, headers=AUTH)
    assert r.json()["description_md"] == JD_BODY.strip()
    # And the model saw that same text, not a summary of it.
    assert intake_engine.extract_calls[0][0] == JD_BODY.strip()


def test_html_pasted_from_devtools_becomes_markdown(client):
    html = "<div><p>We need a <strong>Java</strong> engineer.</p><ul><li>Spring</li></ul></div>"
    r = client.post("/jobs/intake", json={"text": html}, headers=AUTH)
    stored = r.json()["description_md"]
    assert "<div>" not in stored and "Java" in stored


def test_a_less_than_sign_in_prose_is_not_html(client):
    """`"<" in text` would have converted this and eaten the rest of the line."""
    text = "Latency must stay < 200ms under load. " + JD_BODY
    r = client.post("/jobs/intake", json={"text": text}, headers=AUTH)
    assert "< 200ms" in r.json()["description_md"]


def test_an_empty_paste_is_refused_before_any_model_call(client, intake_engine):
    r = client.post("/jobs/intake", json={"text": "   \n  "}, headers=AUTH)
    assert r.status_code == 422
    assert not intake_engine.extract_calls, "nothing to read should cost nothing"


def test_a_whole_careers_page_is_refused_with_the_limit_in_the_message(client, intake_engine):
    r = client.post("/jobs/intake", json={"text": "x" * (MAX_JD_CHARS + 1)}, headers=AUTH)
    assert r.status_code == 422
    assert f"{MAX_JD_CHARS:,}" in r.json()["detail"]
    assert not intake_engine.extract_calls


def test_a_provider_failure_reads_as_the_providers_fault(client):
    app.dependency_overrides[get_engine] = lambda: FixtureIntakeEngine()
    r = client.post("/jobs/intake", json={"text": JD_BODY}, headers=AUTH)
    # 502, not 500: the thing that broke is reachable from /models.
    assert r.status_code == 502


def test_quality_flags_come_from_arithmetic_not_from_the_model(client):
    """A short paste is flagged thin, and the flag is the crawler's own."""
    r = client.post("/jobs/intake", json={"text": "Java dev wanted."}, headers=AUTH)
    body = r.json()
    assert "thin_jd" in body["flags"]
    # Never `stale`: a paste carries no publication date, and unknown age is not
    # old age. `undated` is true of every paste but is dropped from the preview —
    # `create_job` stamps posted_at on save, so a chip that every paste raises
    # and every save clears only teaches the user to ignore the chips.
    assert "undated" not in body["flags"] and "stale" not in body["flags"]
    assert body["notes"], "each flag should come with a line the user can act on"
    assert len("Java dev wanted.") < THIN_JD_CHARS


def test_a_level_outside_the_columns_vocabulary_is_dropped(client, intake_engine):
    """A model answering "mid-senior" would create a bucket no filter selects.

    Built through validation rather than ``model_copy``, because that is the
    path a real answer takes: the provider hands back JSON and pydantic
    validates it. ``model_copy(update=...)`` skips validators, so asserting
    through it would test nothing.
    """
    intake_engine.extracted = JdExtract(**{**EXTRACT.model_dump(), "level": "mid-senior"})
    r = client.post("/jobs/intake", json={"text": JD_BODY}, headers=AUTH)
    assert r.json()["level"] == ""


def test_the_level_vocabulary_is_the_one_infer_level_writes():
    """Pins the schema's validator to the crawler's own list.

    They are the same frozenset today; this fails if someone gives the model a
    richer vocabulary than the column has ever held.
    """
    assert LEVELS == {"intern", "fresher", "junior", "senior", "middle"}
    assert JdExtract(**{**EXTRACT.model_dump(), "level": "senior"}).level == "senior"


# --------------------------------------------------------------------------- #
# saving: a hand-added job gets what a crawled one gets
# --------------------------------------------------------------------------- #


def test_a_hand_added_job_carries_the_crawlers_signals(client):
    job = _save(client)
    assert job["quality"]["flags"] == [] or "no_jd" not in job["quality"]["flags"]
    assert job["quality"]["matched"] or job["quality"]["missing"]


def test_a_hand_added_job_is_visible_to_the_market_facets(client, session_factory):
    """Before this, /market could not see a manually added job at all."""
    job = _save(client)
    with session_factory() as s:
        payload = s.get(Job, job["id"]).payload
    assert payload["salary_range"] is not None
    assert payload["skills_canonical"]
    # Canonicalised, not echoed: `canonical_city` is what makes /market able
    # to group "Ho Chi Minh City", "HCMC" and "TP.HCM" into one bar.
    assert payload["city"] == "Hồ Chí Minh"
    assert payload["is_remote"] is False


def test_a_salary_too_long_for_the_column_is_clamped_not_a_500(client, session_factory):
    """The failure the intake path made reachable.

    The extract prompt tells the model to copy the pay label *verbatim*, so a
    posting that words its pay as a sentence produces a "salary" of a couple of
    hundred characters, pre-filled into the form the user then saves. Postgres
    answers an overlong value with StringDataRightTruncation mid-flush — a 500
    naming no field, after the model call has already been paid for. SQLite
    ignores VARCHAR widths, so this test asserts on the clamp rather than on the
    error it prevents; the error only ever appears on the real database.
    """
    sentence = "Lương thoả thuận theo năng lực và kinh nghiệm, " * 6
    assert len(sentence) > 128
    job = _save(client, salary=sentence, title="X" * 400, location="Y" * 400)
    assert len(job["salary"]) <= 128
    assert len(job["title"]) <= 256
    assert len(job["location"]) <= 256
    with session_factory() as s:
        row = s.get(Job, job["id"])
        assert len(row.salary) <= 128 and len(row.title) <= 256


def test_patch_clamps_the_same_fields_create_does(client):
    """PATCH takes the same fields from the same form, so it needs the same clamp."""
    job = _save(client)
    r = client.patch(f"/jobs/{job['id']}", json={"salary": "z" * 400}, headers=AUTH)
    assert r.status_code == 200, r.text
    assert len(r.json()["salary"]) <= 128


def test_the_clamp_keeps_an_absent_salary_absent(client):
    """None is "not disclosed"; "" would read as a published empty salary."""
    job = _save(client, salary=None)
    assert job["salary"] is None


def test_a_hand_added_job_is_scored_like_a_crawled_one(client):
    job = _save(client)
    assert job["match_score"] > 0.0


def test_pasting_a_description_re_derives_the_signals(client):
    """The LinkedIn-alert path: `no_jd` should not survive the paste that fixes it."""
    thin = _save(client, description_md="")
    assert "thin_jd" in thin["quality"]["flags"]

    r = client.patch(f"/jobs/{thin['id']}", json={"description_md": JD_BODY}, headers=AUTH)
    assert r.status_code == 200, r.text
    patched = r.json()
    assert "thin_jd" not in patched["quality"]["flags"]
    assert patched["match_score"] > 0.0


def test_editing_a_tailored_job_does_not_downgrade_its_match_score(client, session_factory):
    """Two measurements share that column; the cheap one must not overwrite the good one."""
    job = _save(client)
    with session_factory() as s:
        row = s.get(Job, job["id"])
        row.status = JobStatus.REVIEW
        row.match_score = 0.91  # as `tailor_job` would have left it
        s.commit()

    r = client.patch(f"/jobs/{job['id']}", json={"location": "Da Nang"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["match_score"] == pytest.approx(0.91)
    # The payload copy still follows the text, so /market stays correct.
    with session_factory() as s:
        assert s.get(Job, job["id"]).payload["city"] == "Đà Nẵng"


# --------------------------------------------------------------------------- #
# the fit check
# --------------------------------------------------------------------------- #


def test_fit_returns_a_verdict_and_stores_it_on_the_job(client, session_factory):
    job = _save(client)
    r = client.post(f"/jobs/{job['id']}/fit", headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] == "fair"
    # 0.5, not the 0.72 the fixture "returned": one must_have HAVE and one
    # must_have MISSING is half the weight earned, and the score is derived from
    # the list rather than taken from the model. See FitReport._recompute_score.
    assert body["match_score"] == pytest.approx(0.5)
    assert body["concerns"] == ["The posting never names the end client."]
    assert body["assessed_at"]

    with session_factory() as s:
        assert s.get(Job, job["id"]).payload["fit"]["verdict"] == "fair"


def test_a_stored_fit_report_comes_back_on_the_job_detail(client):
    job = _save(client)
    client.post(f"/jobs/{job['id']}/fit", headers=AUTH)
    detail = client.get(f"/jobs/{job['id']}", headers=AUTH).json()
    assert detail["fit"]["verdict"] == "fair"
    assert [r["status"] for r in detail["fit"]["requirements"]] == ["HAVE", "MISSING"]


def test_a_job_without_a_fit_report_says_so_rather_than_guessing(client):
    job = _save(client)
    assert client.get(f"/jobs/{job['id']}", headers=AUTH).json()["fit"] is None


def test_a_fit_report_never_touches_match_score(client, session_factory):
    """The fit score and the column are different measurements of different things."""
    job = _save(client)
    before = job["match_score"]
    client.post(f"/jobs/{job['id']}/fit", headers=AUTH)
    with session_factory() as s:
        assert s.get(Job, job["id"]).match_score == pytest.approx(before)


def test_fit_refuses_a_job_with_no_description(client, intake_engine):
    job = _save(client, description_md="")
    r = client.post(f"/jobs/{job['id']}/fit", headers=AUTH)
    assert r.status_code == 409
    assert not intake_engine.assess_calls, "no JD means nothing to assess and nothing to spend"


def test_fit_refuses_an_unfilled_master_cv_before_spending_a_call(
    client, session_factory, intake_engine
):
    """A fresh database bootstraps an empty CV; assessing it would return "weak, 0%".

    That is a confident verdict about someone's career when the true answer is
    "you have not filled in your CV yet" — the repo's own rule that not knowing
    is not the same as being broken. Refusing costs nothing; the alternative is
    a paid call that produces a discouraging lie.
    """
    from jobpilot.cv.skeleton import empty_document

    job = _save(client)
    with session_factory() as s:
        cv_store.save_version(s, cv_store.MASTER_SCOPE, empty_document(), author="user")

    r = client.post(f"/jobs/{job['id']}/fit", headers=AUTH)
    assert r.status_code == 409
    assert "empty" in r.json()["detail"].lower()
    assert not intake_engine.assess_calls, "an unfilled CV should cost nothing"


def test_the_unfilled_threshold_is_measured_from_the_skeleton_not_guessed():
    """The skeleton's own section titles came to exactly 200 characters.

    A hand-picked 200 would have sat right on that boundary and let the empty
    document through. Pinned because the failure is silent in both directions.
    """
    from jobpilot.cv.skeleton import empty_document

    assert service.cv_is_unfilled(empty_document())
    assert not service.cv_is_unfilled(sample_document())


def test_fit_on_a_missing_job_is_404(client):
    assert client.post("/jobs/manual:nope/fit", headers=AUTH).status_code == 404


def test_fit_works_after_the_funnel_has_moved_on(client, session_factory):
    """'How well did my CV match the job that rejected me' is a fair question."""
    job = _save(client)
    with session_factory() as s:
        s.get(Job, job["id"]).status = JobStatus.SUBMITTED
        s.commit()
    assert client.post(f"/jobs/{job['id']}/fit", headers=AUTH).status_code == 200


def test_a_garbled_stored_report_does_not_break_the_page(client, session_factory):
    """JSONB is written by whatever build was running; the detail page still renders."""
    job = _save(client)
    with session_factory() as s:
        row = s.get(Job, job["id"])
        row.payload = {**row.payload, "fit": {"verdict": "fair"}}  # no match_score
        s.commit()
    r = client.get(f"/jobs/{job['id']}", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["fit"] is None


# --------------------------------------------------------------------------- #
# service-level
# --------------------------------------------------------------------------- #


def test_nested_bullets_survive_the_paste(client):
    """A posting that nests JPA under Java is saying how those relate.

    `clean_text` per line would strip the indent and leave four siblings — the
    structure gone silently, in the field every later step reads as evidence.
    """
    text = "Yeu cau:\n- Java\n    - Spring Boot\n    - JPA\n- SQL"
    r = client.post("/jobs/intake", json={"text": text}, headers=AUTH)
    stored = r.json()["description_md"]
    assert "    - Spring Boot" in stored and "\n- SQL" in stored


def test_runs_of_blank_lines_collapse_to_one(client):
    r = client.post("/jobs/intake", json={"text": "A\n\n\n\nB"}, headers=AUTH)


    assert r.json()["description_md"] == "A\n\nB"

def test_the_skills_the_model_read_are_returned_for_saving(client):
    """They are a job's whole contribution to the Market page's skill facet."""
    r = client.post("/jobs/intake", json={"text": JD_BODY}, headers=AUTH)
    assert r.json()["skills"] == ["Java", "Spring Boot", "PostgreSQL"]


def test_the_body_comes_back_bucketed(client, intake_engine):
    r = client.post("/jobs/intake", json={"text": JD_BODY}, headers=AUTH)
    got = r.json()["sections"]
    assert got["must_have"] == ["4+ years of backend Java", "Spring Boot"]
    assert got["nice_to_have"] == ["Docker, Kubernetes is a plus"]
    assert got["soft_skills"] == ["Clear written communication"]
    assert got["outputs"] == [], "empty is the right answer when a posting says nothing"
    assert got["how_to_apply"]
    assert intake_engine.section_calls, "the sections engine should have been asked"


def test_both_reads_see_the_same_text(client, intake_engine):
    """They run concurrently over one posting; different inputs would describe
    different jobs."""
    client.post("/jobs/intake", json={"text": JD_BODY}, headers=AUTH)
    assert intake_engine.extract_calls[0][0] == intake_engine.section_calls[0]


def test_the_buckets_do_not_replace_the_raw_jd(client):
    """A table of contents over the text, never instead of it."""
    body = client.post("/jobs/intake", json={"text": JD_BODY}, headers=AUTH).json()
    assert body["description_md"] == JD_BODY.strip()
    assert body["sections"]["must_have"]


def test_saved_sections_come_back_on_the_job_detail(client):
    job = _save(client, sections=SECTIONS.model_dump())
    detail = client.get(f"/jobs/{job['id']}", headers=AUTH).json()
    assert detail["sections"]["benefits"] == ["13th month salary", "Health insurance"]
    assert detail["description_md"], "the raw JD is still there beside the buckets"


def test_rewriting_the_description_drops_the_stale_buckets(client):
    """The buckets are quoted as the posting's own lines, so they cannot outlive it.

    Otherwise the structured tab shows "Required: Java" beside a raw tab that
    now asks for Python, both presented as the same ad.
    """
    job = _save(client, sections=SECTIONS.model_dump())
    assert job["sections"]["must_have"]

    r = client.patch(
        f"/jobs/{job['id']}",
        json={"description_md": "A completely different posting about Python. " * 20},
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    assert r.json()["sections"] is None


def test_rewriting_the_description_drops_the_stale_fit_report(client, session_factory):
    """It judged a posting that no longer exists, and nothing on the card says so."""
    job = _save(client)
    client.post(f"/jobs/{job['id']}/fit", headers=AUTH)
    assert client.get(f"/jobs/{job['id']}", headers=AUTH).json()["fit"]

    client.patch(
        f"/jobs/{job['id']}",
        json={"description_md": "Another posting entirely. " * 25},
        headers=AUTH,
    )
    assert client.get(f"/jobs/{job['id']}", headers=AUTH).json()["fit"] is None


def test_new_buckets_sent_with_the_new_description_are_kept(client):
    """Dropping is for *stale* readings, not for the fresh one arriving with it."""
    job = _save(client, sections=SECTIONS.model_dump())
    fresh = {**SECTIONS.model_dump(), "must_have": ["Python"]}
    r = client.patch(
        f"/jobs/{job['id']}",
        json={"description_md": "Python job. " * 40, "sections": fresh},
        headers=AUTH,
    )
    assert r.json()["sections"]["must_have"] == ["Python"]


def test_editing_something_other_than_the_jd_keeps_the_buckets(client):
    """Only a rewritten description invalidates them — a salary fix does not."""
    job = _save(client, sections=SECTIONS.model_dump())
    r = client.patch(f"/jobs/{job['id']}", json={"salary": "50 triệu"}, headers=AUTH)
    assert r.json()["sections"]["must_have"] == SECTIONS.must_have


def test_re_pasting_a_changed_posting_drops_the_old_reading(client):
    """POST upserts, so the second paste lands on the first paste's buckets."""
    body = {
        "url": "https://example.com/upsert-probe",
        "title": "Probe",
        "company": "Probe Co",
        "description_md": JD_BODY,
        "sections": SECTIONS.model_dump(),
    }
    first = client.post("/jobs", json=body, headers=AUTH).json()
    assert first["sections"]["must_have"]

    again = client.post(
        "/jobs", json={**body, "description_md": "Different text. " * 40, "sections": None},
        headers=AUTH,
    ).json()
    assert again["id"] == first["id"], "same posting, same row"
    assert again["sections"] is None


def test_backfill_does_not_wipe_a_hand_added_jobs_facets(client, session_factory):
    """`backfill --force` is the command the docs say you MUST run after a parser
    fix — so it must not be the command that erases half the corpus.

    `backfill_facets` used to read `payload["location"]`/`["salary"]`, which only
    `normalize()` writes. A job added through POST /jobs never had them, so the
    backfill handed `derived_facets(None, ..., None)` every hand-added job and
    nulled its city, salary_range, is_remote and work_mode. Silently.
    """
    from jobpilot.crawler.normalize import backfill_facets

    job = _save(client, location="Ho Chi Minh City, Vietnam (Hybrid)", salary="20 - 60 triệu")
    with session_factory() as s:
        before = s.get(Job, job["id"]).payload
        assert before["city"] == "Hồ Chí Minh" and before["work_mode"] == "hybrid"
        assert before["salary_range"]["kind"] == "range"

        backfill_facets(s, force=True)

        after = s.get(Job, job["id"]).payload
        assert after["city"] == "Hồ Chí Minh", "backfill erased the province"
        assert after["work_mode"] == "hybrid", "backfill erased the work mode"
        assert after["salary_range"]["kind"] == "range", "backfill erased the pay"


def test_patching_a_job_keeps_its_work_mode(client, session_factory):
    """Editing the JD must not erase a work mode the location can't re-derive.

    `signals.payload` always carries a `work_mode` key, so spreading it last
    overwrote the stored value with the location-derived one — null, for a
    location like "Ho Chi Minh City". Editing the description of a remote job
    through the Job description card erased its mode for good.
    """
    job = _save(client, location="Ho Chi Minh City", work_mode="remote")
    assert job["work_mode"] == "remote"

    r = client.patch(
        f"/jobs/{job['id']}", json={"description_md": JD_BODY + " more"}, headers=AUTH
    )
    assert r.status_code == 200, r.text
    assert r.json()["work_mode"] == "remote"


def test_patch_can_set_the_work_mode(client):
    job = _save(client, location="Ho Chi Minh City")
    assert job["work_mode"] is None
    r = client.patch(f"/jobs/{job['id']}", json={"work_mode": "hybrid"}, headers=AUTH)
    assert r.json()["work_mode"] == "hybrid"


def test_a_stated_work_mode_beats_the_one_read_off_the_location(client):
    """The model read the body; the fallback only ever read the label."""
    job = _save(client, location="Ho Chi Minh City (On-site)", work_mode="hybrid")
    assert job["work_mode"] == "hybrid"


def test_a_work_mode_off_the_vocabulary_is_a_422_not_a_mystery_chip(client):
    r = client.post(
        "/jobs",
        json={"title": "T", "company": "C", "work_mode": "Work From Home (mostly)"},
        headers=AUTH,
    )
    assert r.status_code == 422


def test_an_overlong_level_is_clamped_like_the_other_columns(client, session_factory):
    """`Job.level` is String(32) and reachable straight from a request body."""
    job = _save(client, level="s" * 200)
    with session_factory() as s:
        assert len(s.get(Job, job["id"]).level or "") <= 32


def test_the_salary_shape_reaches_the_job_detail(client):
    """It was computed and buried in JSONB; the user asked to see pay shapes."""
    job = _save(client, salary="Từ 35 triệu")
    assert client.get(f"/jobs/{job['id']}", headers=AUTH).json()["salary_kind"] == "from"


def test_a_sections_failure_still_returns_the_fields(client, intake_engine):
    """The larger schema failing must not throw away an extract already paid for."""
    intake_engine.parsed = None  # sections engine will raise
    r = client.post("/jobs/intake", json={"text": JD_BODY}, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Senior Backend Engineer", "the fields still arrived"
    assert body["sections"]["must_have"] == [], "and the buckets are simply empty"


def test_a_crawled_job_has_no_sections_and_that_is_normal(client, session_factory):
    """Absence is the common case — the crawlers store the JD whole."""
    job = _save(client)
    assert client.get(f"/jobs/{job['id']}", headers=AUTH).json()["sections"] is None


def test_a_garbled_stored_sections_blob_does_not_break_the_page(client, session_factory):
    job = _save(client)
    with session_factory() as s:
        row = s.get(Job, job["id"])
        row.payload = {**row.payload, "sections": {"must_have": "not a list"}}
        s.commit()
    r = client.get(f"/jobs/{job['id']}", headers=AUTH)
    assert r.status_code == 200 and r.json()["sections"] is None


# --------------------------------------------------------------------------- #
# location, work mode, salary shape
# --------------------------------------------------------------------------- #


def test_the_province_survives_a_country_suffix(client):
    """"Ho Chi Minh City, Vietnam" is the shape every LinkedIn alert uses."""
    from jobpilot.crawler.vietnam import canonical_city, looks_like_city

    for label in ("Ho Chi Minh City, Vietnam", "Ha Noi, Vietnam", "Đà Nẵng, Việt Nam"):
        assert looks_like_city(label), label
    assert canonical_city("Ho Chi Minh City, Vietnam") == "Hồ Chí Minh"
    assert canonical_city("TP.HCM") == "Hồ Chí Minh"
    assert canonical_city("Thành phố Hồ Chí Minh") == "Hồ Chí Minh"


def test_a_country_alone_is_still_not_a_location():
    """Dropping filler parts must not let a label through that names no place."""
    from jobpilot.crawler.vietnam import looks_like_city

    assert not looks_like_city("Vietnam")
    assert not looks_like_city("Việt Nam")
    # And the substring trap this repo already paid for stays closed.
    assert not looks_like_city("remote debugging")
    assert not looks_like_city("Java, Remote debugging")


def test_the_work_mode_annotation_does_not_hide_the_city(client):
    """LinkedIn writes "Ho Chi Minh City, Vietnam (Hybrid)" — one place, one mode."""
    from jobpilot.crawler.normalize import parse_work_mode
    from jobpilot.crawler.vietnam import canonical_city

    label = "Ho Chi Minh City, Vietnam (Hybrid)"
    assert canonical_city(label) == "Hồ Chí Minh"
    assert parse_work_mode(label) == "hybrid"


def test_hybrid_wins_over_onsite_when_both_words_appear():
    """"hybrid (2 days onsite)" is hybrid; first-match order decides it."""
    from jobpilot.crawler.normalize import parse_work_mode

    assert parse_work_mode("Hybrid (2 days onsite)") == "hybrid"
    assert parse_work_mode("On-site") == "onsite"
    assert parse_work_mode("Làm việc từ xa") == "remote"
    assert parse_work_mode("Ho Chi Minh City") is None, "unstated is not a mode"


def test_is_remote_and_work_mode_cannot_disagree():
    """Two fields derived from one label, so they share one vocabulary.

    Measured on the live corpus: eight jobs said "Anywhere in the World", which
    `_REMOTE_RE` knows and a hand-written twin pattern did not — `is_remote`
    true, `work_mode` null, same row, same question.
    """
    from jobpilot.crawler.normalize import derived_facets

    for label in ("Anywhere in the World", "Remote", "Work from home", "WFH", "Vietnam (Remote)"):
        facets = derived_facets(None, [], label)
        assert facets["is_remote"] == (facets["work_mode"] == "remote"), label


def test_a_work_mode_off_the_list_is_dropped():
    bad = JdExtract(**{**EXTRACT.model_dump(), "work_mode": "flexible-ish"})
    assert bad.work_mode == ""


def test_salary_shapes_are_labelled_including_the_fourth_one():
    """The list said three; live ads write a floor too, and the parser finds it."""
    from jobpilot.crawler.salary import parse

    assert parse("25 triệu").kind == "fixed"
    assert parse("Up to $3000").kind == "up_to"
    assert parse("20 - 60 triệu").kind == "range"
    # "Từ 15 triệu" has a floor and no ceiling. Calling it a range would invent
    # a ceiling; calling it fixed would invent a salary.
    assert parse("Từ 15 triệu").kind == "from"
    assert parse("trên 20 triệu").kind == "from"


def test_the_salary_shape_travels_with_the_stored_facet(client, session_factory):
    job = _save(client, salary="20 - 60 triệu")
    with session_factory() as s:
        assert s.get(Job, job["id"]).payload["salary_range"]["kind"] == "range"


def test_work_mode_is_read_off_the_location_when_nobody_states_it(client, session_factory):
    job = _save(client, location="Ho Chi Minh City, Vietnam (Hybrid)")
    with session_factory() as s:
        row = s.get(Job, job["id"])
        assert row.payload["work_mode"] == "hybrid"
        # And the annotation did not cost us the province.
        assert row.payload["city"] == "Hồ Chí Minh"


def test_extract_refuses_before_calling_the_engine():
    engine = FixtureIntakeEngine(extracted=EXTRACT)
    with pytest.raises(service.IntakeRefused):
        service.extract_jd("", engine)
    assert not engine.extract_calls

def test_the_fixture_engine_without_an_answer_raises_intake_error():
    with pytest.raises(IntakeError):
        FixtureIntakeEngine().extract("anything")

def test_the_score_is_derived_from_the_list_not_taken_from_the_model():
    """Whatever number comes back, the one shown agrees with the requirements."""
    for claimed in (1.4, -0.2, 0.9, 0.0):
        assert FitReport(**{**REPORT.model_dump(), "match_score": claimed}).match_score == 0.5

def test_the_model_score_is_kept_only_when_there_is_no_list_to_derive_from():
    bare = FitReport(**{**REPORT.model_dump(), "requirements": [], "match_score": 1.4})
    assert bare.match_score == 1.0  # clamped, but its own

def test_soft_requirements_do_not_move_the_score():
    """A CV cannot evidence "high growth drive"; counting it would score the prose."""
    soft = Requirement(text="High growth drive", kind="soft", status="MISSING", evidence="")
    with_soft = FitReport(**{**REPORT.model_dump(), "requirements": [*REPORT.requirements, soft]})
    assert with_soft.match_score == pytest.approx(0.5)

def test_a_posting_that_asks_only_for_personality_scores_the_middle():
    """Not 0.0 — nothing was demanded that a CV could have answered."""
    soft = Requirement(text="Product thinking", kind="soft", status="MISSING", evidence="")
    only_soft = FitReport(**{**REPORT.model_dump(), "requirements": [soft]})
    assert only_soft.match_score == pytest.approx(0.5)

def test_the_verdict_never_contradicts_the_score():
    strong = [Requirement(text=f"r{i}", kind="must_have", status="HAVE", evidence="cv")
              for i in range(3)]
    assert FitReport(**{**REPORT.model_dump(), "requirements": strong}).verdict == "strong"

    weak = [Requirement(text=f"r{i}", kind="must_have", status="MISSING", evidence="")
            for i in range(3)]
    assert FitReport(**{**REPORT.model_dump(), "requirements": weak}).verdict == "weak"

def test_a_dealbreaker_forces_a_weak_verdict_whatever_the_score():
    """No percentage is encouraging when you don't hold the degree they require."""
    strong = [Requirement(text=f"r{i}", kind="must_have", status="HAVE", evidence="cv")
              for i in range(3)]
    blocked = FitReport(
        **{**REPORT.model_dump(), "requirements": strong, "dealbreakers": ["Requires a PhD"]}
    )
    assert blocked.match_score == pytest.approx(1.0)
    assert blocked.verdict == "weak"

def test_gaps_reads_the_same_as_a_tailor_plans():
    assert [r.text for r in REPORT.gaps()] == ["Kafka"]
