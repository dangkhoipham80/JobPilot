"""``POST /api/cv/master/edit`` — queueing, refusals, and what lands in the DB."""

from __future__ import annotations

import pytest

from jobpilot.api.main import app
from jobpilot.api.deps import get_db
from jobpilot.api.routes.cv import get_edit_engine
from jobpilot.cv import store as cv_store
from jobpilot.cv.sample import sample_document
from jobpilot.tailor.edit import FixtureEditEngine, NewEntry, empty_plan
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


def test_an_instruction_carries_a_raw_tex_override_forward(client, run_task, worker_db):
    """Editing the Master CV must not be a backdoor way to lose hand-written LaTeX.

    ``PUT /cv/{scope}`` already carries a ``tex_override`` forward for exactly
    this reason: dropping it the moment an unrelated field changes would throw
    away a human's raw ``.tex`` silently. ``edit_master`` appends a version the
    same way ``put_cv`` does, so it must do the same thing.
    """
    with worker_db() as s:
        cv_store.save_tex_override(s, cv_store.MASTER_SCOPE, {"cv.tex": r"\documentclass{article}"})

    before = client.get("/cv/master", headers=AUTH).json()
    assert before["tex_override"] is True

    r = client.post("/cv/master/edit", json={"instruction": INSTRUCTION}, headers=AUTH)
    task = run_task(client, r)
    assert task["status"] == "done", task.get("error")

    after = client.get("/cv/master", headers=AUTH).json()
    assert after["tex_override"] is True, "the raw .tex override was dropped by an unrelated edit"


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


def test_an_instruction_the_agent_declines_writes_no_version(client, run_task):
    """Declining to invent detail is the right answer, not an edit.

    A version identical to the previous one would file that answer as a change
    and bury the rows that mean something.
    """
    app.dependency_overrides[get_edit_engine] = lambda: FixtureEditEngine(
        plan=empty_plan().model_copy(update={"note": "too vague — no project name given"})
    )
    before = client.get("/cv/master/versions", headers=AUTH).json()["total"]

    r = client.post("/cv/master/edit", json={"instruction": "Add my Kafka project."}, headers=AUTH)
    task = run_task(client, r)

    assert task["status"] == "done"
    assert task["result"]["changed"] is False
    assert "too vague" in task["result"]["note"]
    assert client.get("/cv/master/versions", headers=AUTH).json()["total"] == before


def test_a_refused_edit_still_closes_its_run_row(client, run_task, worker_db):
    """``session_scope()`` rolls back on the way out, so the failure must be committed.

    Without that the Run row keeps the ``finished_at=NULL`` it was created with,
    and a refused edit shows on the Runs page as one that never stopped.
    """
    from sqlalchemy import select

    from jobpilot.store.models import Run

    bad = empty_plan().model_copy(
        update={"new_entries": [_entry("Ghost", ["Ran a 40 person team."])]}
    )
    app.dependency_overrides[get_edit_engine] = lambda: FixtureEditEngine(plan=bad)

    r = client.post("/cv/master/edit", json={"instruction": INSTRUCTION}, headers=AUTH)
    assert run_task(client, r)["status"] == "failed"

    with worker_db() as s:
        run = s.scalars(select(Run).where(Run.kind == "cv_edit").order_by(Run.id.desc())).first()
        assert run is not None
        assert run.finished_at is not None, "a refused edit left its Run row open"
        assert run.stats["ok"] is False
        assert "40" in run.stats["error"]
