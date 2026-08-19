"""``POST /api/cv/master/edit`` — queueing, refusals, and what lands in the DB."""

from __future__ import annotations

import pytest

from jobpilot.api.main import app
from jobpilot.api.deps import get_db
from jobpilot.api.routes.cv import get_edit_engine
from jobpilot.cv import store as cv_store
from jobpilot.cv.sample import sample_document
from jobpilot.tailor.edit import FixtureEditEngine, MasterEditPlan, NewEntry, empty_plan
from jobpilot.config import get_secrets
from jobpilot.tests.conftest import api_client

AUTH = {"X-API-Token": get_secrets().jobpilot_api_token}

INSTRUCTION = "Add a project called JobPilot, a job crawler that tailors my CV."
QUOTE = "a job crawler that tailors my CV"

def _entry(title: str, items: list[str]) -> NewEntry:
    return NewEntry(
        section_key="projects",
        title=title,
        date="",
        role="",
        tech_stack="",
        items=items,
        source_quote=QUOTE,
        reason="the user asked for it",
    )


PLAN = empty_plan().model_copy(
    update={"new_entries": [_entry("JobPilot", ["A job crawler that tailors my CV."])]}
)


@pytest.fixture
def edit_engine() -> FixtureEditEngine:
    return FixtureEditEngine(plan=PLAN)


@pytest.fixture
def client(worker_db, edit_engine):
    """``worker_db`` is not optional here — it is the whole test.

    The edit runs in a queue worker, which opens its *own* session from the
    process sessionmaker; overriding FastAPI's ``get_db`` never reaches it. Without
    this fixture the worker writes to whatever ``DATABASE_URL`` points at, which
    during development is the real Postgres — and it does it silently, because the
    task reports "done" either way. It appended a fabricated project to the real
    Master CV once; that is what this line prevents.
    """
    session_factory = worker_db

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
    app.dependency_overrides[get_edit_engine] = lambda: edit_engine
    c = api_client(app)
    yield c
    app.dependency_overrides.clear()


def test_edit_requires_token(client):
    assert client.post("/cv/master/edit", json={"instruction": "x"}).status_code == 401


def test_empty_instruction_is_refused(client):
    r = client.post("/cv/master/edit", json={"instruction": "   "}, headers=AUTH)
    assert r.status_code == 422


def test_a_tailored_scope_is_pointed_at_the_other_route(client):
    """Editing a tailored CV here would fork it from the plan that explains it."""
    r = client.post("/cv/itviec:1/edit", json={"instruction": "x"}, headers=AUTH)
    assert r.status_code == 400
    assert "/jobs/itviec:1/edit" in r.json()["detail"]


def test_an_instruction_appends_a_version_with_the_plan(client, run_task, edit_engine):
    r = client.post("/cv/master/edit", json={"instruction": INSTRUCTION}, headers=AUTH)
    assert r.status_code == 202
    task = run_task(client, r)
    assert task["status"] == "done", task.get("error")
    assert task["result"]["ops"] == 1

    doc = client.get("/cv/master", headers=AUTH).json()
    projects = [s for s in doc["document"]["sections"] if s["key"] == "projects"][0]
    assert projects["entries"][-1]["title"] == "JobPilot"

    # The change is a version, with the instruction and plan recorded on it.
    versions = client.get("/cv/master/versions", headers=AUTH).json()["items"]
    assert versions[0]["author"] == "agent"
    detail = client.get(f"/cv/master/versions/{versions[0]['version']}", headers=AUTH).json()
    assert detail["meta"]["instruction"] == INSTRUCTION
    assert detail["meta"]["edit_plan"]["new_entries"][0]["source_quote"] == QUOTE


def test_a_plan_that_invents_a_fact_fails_the_task_and_writes_no_version(client, run_task):
    """The guard runs in the worker too — a fixture engine cannot smuggle one past."""
    bad = empty_plan().model_copy(
        update={"new_entries": [_entry("Ghost", ["Ran a 40 person team."])]}
    )
    app.dependency_overrides[get_edit_engine] = lambda: FixtureEditEngine(plan=bad)

    before = client.get("/cv/master/versions", headers=AUTH).json()["total"]
    r = client.post("/cv/master/edit", json={"instruction": INSTRUCTION}, headers=AUTH)
    task = run_task(client, r)

    assert task["status"] == "failed"
    assert "40" in task["error"]
    assert client.get("/cv/master/versions", headers=AUTH).json()["total"] == before
