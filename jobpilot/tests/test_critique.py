"""CV critique: counted market evidence + an advisory model opinion.

What matters is the split: every figure comes from the crawled jobs, never from
the model; verdicts that point at entries the CV does not have are dropped; and
nothing here writes to the CV.
"""

from __future__ import annotations

from datetime import date

import pytest

from jobpilot.api.deps import get_db
from jobpilot.api.main import app
from jobpilot.api.routes.critique import get_engine
from jobpilot.config import get_secrets
from jobpilot.critique import market
from jobpilot.critique.engine import CritiqueError, FixtureCritiqueEngine
from jobpilot.critique.prompt import system_prompt, user_prompt
from jobpilot.critique.schema import CvCritique, EntryVerdict, SectionVerdict, SkillAdvice
from jobpilot.critique.service import clean
from jobpilot.cv import store as cv_store
from jobpilot.cv.sample import sample_document
from jobpilot.cv.skeleton import empty_document
from jobpilot.store.models import Job
from jobpilot.tests.conftest import api_client

AUTH = {"X-API-Token": get_secrets().jobpilot_api_token}


def _payload(title: str, skills: list[str], level: str | None = None) -> dict:
    return {"title": title, "skills_canonical": skills, "level": level}


PAYLOADS = [
    _payload("Backend Engineer (Java)", ["java", "spring", "kafka"], "junior"),
    _payload("Java Developer", ["java", "spring", "docker"], "senior"),
    _payload("Senior Backend Developer", ["java", "kafka"], "senior"),
    _payload("Frontend Developer", ["react", "typescript"]),
    _payload("Game Developer", ["unity", "c#"]),
]

REPORT = CvCritique(
    headline="Junior backend engineer (Java)",
    summary="Reads as backend.",
    strengths=["Clear Spring Boot experience"],
    sections=[
        SectionVerdict(key="summary", verdict="improve", reason="generic"),
        SectionVerdict(key="nope", verdict="ok", reason="not a section"),
        SectionVerdict(key="summary", verdict="ok", reason="duplicate"),
    ],
    entries=[
        EntryVerdict(section_key="projects", entry_index=0, verdict="keep", reason="strong"),
        EntryVerdict(section_key="projects", entry_index=99, verdict="cut", reason="ghost"),
        EntryVerdict(section_key="skills", entry_index=0, verdict="trim", reason="not entries"),
    ],
    skills=[SkillAdvice(skill="kafka", advice="learn", reason="asked often")],
    priorities=["Rewrite the summary"],
)


# --------------------------------------------------------------------------- #
# market snapshot — the counted half
# --------------------------------------------------------------------------- #
def test_role_presets_match_titles_and_free_text_is_a_phrase():
    assert market.role_matches("backend", "Java Developer")
    assert market.role_matches("frontend", "Frontend Developer")
    assert not market.role_matches("backend", "Game Developer")
    assert market.role_matches("game developer", "Senior Game Developer")
    assert market.role_matches("", "anything")


def test_snapshot_counts_only_the_role_and_marks_what_the_cv_has():
    snap = market.snapshot(PAYLOADS, sample_document(), "backend")
    assert (snap["jobs"], snap["total_jobs"]) == (3, 5)
    rows = {r["key"]: r for r in snap["skills"]["rows"]}
    assert rows["java"]["count"] == 3 and rows["java"]["on_cv"]
    assert "react" not in rows  # the frontend ad is outside the role
    assert snap["skills"]["covered"] == 3 and snap["skills"]["total"] == 3
    assert {r["key"]: r["count"] for r in snap["levels"]["rows"]} == {"junior": 1, "senior": 2}


def test_snapshot_counts_how_often_the_cvs_own_skills_are_asked_for():
    snap = market.snapshot(PAYLOADS, sample_document(), "backend")
    asked = {s["name"]: s["count"] for s in snap["cv_skills"]}
    assert asked["Java"] == 3
    assert asked["Spring Boot"] == 2  # canonical "spring"
    assert asked.get("Jira", 0) == 0


def test_whole_term_matching():
    assert market.mentions("we use java daily", "java")
    assert not market.mentions("javascript only", "java")
    assert market.mentions("c# and .net", "c#")


def test_render_warns_on_a_small_sample():
    text = market.render(market.snapshot(PAYLOADS, sample_document(), "frontend"))
    assert "too few jobs" in text and "react: 1" in text


# --------------------------------------------------------------------------- #
# cleaning the model's answer
# --------------------------------------------------------------------------- #
def test_clean_drops_verdicts_that_point_at_nothing_and_resolves_titles():
    doc = sample_document()
    out = clean(REPORT, doc)
    assert [s["key"] for s in out.report["sections"]] == ["summary"]
    assert out.report["sections"][0]["title"] == "Summary"
    assert len(out.report["entries"]) == 1
    assert out.report["entries"][0]["title"].startswith("Lumen")
    assert out.dropped == 4 and out.report["dropped"] == 4


def test_prompt_language_and_rules():
    assert "Write every free-text field in Vietnamese" in system_prompt(sample_document())
    assert "in English" in system_prompt(sample_document(), "en")
    assert "never propose a number" in system_prompt(sample_document())


def test_user_prompt_carries_todays_date():
    """Without it the model calls a current "Oct 2026 -- Present" a typo."""
    text = user_prompt("SNAPSHOT", "backend", date(2026, 10, 14))
    assert "Today's date: 2026-10-14" in text and "backend" in text


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@pytest.fixture
def critic() -> FixtureCritiqueEngine:
    return FixtureCritiqueEngine(report=REPORT)


@pytest.fixture
def client(session_factory, critic):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    with session_factory() as s:
        cv_store.ensure_master(s)
        cv_store.save_version(s, cv_store.MASTER_SCOPE, sample_document(), author="user")
        for i, p in enumerate(PAYLOADS):
            s.add(Job(id=f"t:{i}", source="t", title=p["title"], company="ACME", payload=p))
        s.commit()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_engine] = lambda: critic
    yield api_client(app)
    app.dependency_overrides.clear()


def test_no_critique_yet_is_null(client):
    r = client.get("/cv/master/critique", headers=AUTH)
    assert r.status_code == 200 and r.json() is None


def test_critique_is_stored_with_its_evidence_and_version(client, critic):
    r = client.post("/cv/master/critique", json={"role": "backend", "lang": "en"}, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "backend" and body["lang"] == "en"
    assert body["cv_version"] == body["current_version"]
    assert body["market"]["jobs"] == 3
    assert body["report"]["headline"] == "Junior backend engineer (Java)"
    assert "backend" in body["roles"]
    assert critic.calls == [("backend", "en")]

    again = client.get("/cv/master/critique", headers=AUTH).json()
    assert again["id"] == body["id"]


def test_critique_goes_stale_when_the_cv_changes(client, session_factory):
    client.post("/cv/master/critique", json={}, headers=AUTH)
    with session_factory() as s:
        cv_store.save_version(s, cv_store.MASTER_SCOPE, sample_document(), author="user")
    body = client.get("/cv/master/critique", headers=AUTH).json()
    assert body["current_version"] == body["cv_version"] + 1


def test_critique_never_writes_the_cv(client, session_factory):
    with session_factory() as s:
        before = cv_store.latest_version(s, cv_store.MASTER_SCOPE).version
    client.post("/cv/master/critique", json={"role": "backend"}, headers=AUTH)
    with session_factory() as s:
        assert cv_store.latest_version(s, cv_store.MASTER_SCOPE).version == before


def test_a_role_no_title_matches_is_refused_before_the_call(client, critic):
    r = client.post("/cv/master/critique", json={"role": "astronaut"}, headers=AUTH)
    assert r.status_code == 409 and "astronaut" in r.json()["detail"]
    assert critic.calls == []


def test_an_empty_cv_is_refused(client, critic, session_factory):
    with session_factory() as s:
        cv_store.save_version(s, cv_store.MASTER_SCOPE, empty_document(), author="user")
    r = client.post("/cv/master/critique", json={}, headers=AUTH)
    assert r.status_code == 409 and critic.calls == []


def test_engine_failure_is_a_502(client, critic):
    critic.report = None
    r = client.post("/cv/master/critique", json={}, headers=AUTH)
    assert r.status_code == 502
    assert isinstance(CritiqueError("x"), RuntimeError)


def test_bad_language_is_rejected(client):
    r = client.post("/cv/master/critique", json={"lang": "fr"}, headers=AUTH)
    assert r.status_code == 422
