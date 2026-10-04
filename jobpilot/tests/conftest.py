"""Shared fixtures: a throwaway SQLite DB standing in for Postgres.

The ``jobpilot`` schema is rewritten to the default via the engine's
schema_translate_map (wired in ``store.db.make_engine``), so the real models
run unchanged without a live Postgres.

**On disk, not in memory.** An in-memory database needs ``StaticPool`` — one
connection shared by every session — which stops modelling Postgres the moment a
second thread appears. Task bodies run on the queue's worker and open their own
session, and with a shared connection the request thread closing its session
issues a ROLLBACK that discards the worker's in-flight transaction. That showed
up as an apply task reporting success while the job stayed APPROVED. A file gives
every session its own connection, like the real thing.
"""

from __future__ import annotations

import threading
import time

import pytest
from sqlalchemy.orm import Session, sessionmaker

from jobpilot.config import get_secrets
from jobpilot.store.db import Base, make_engine


def api_client(app, **kwargs):
    """A ``TestClient`` whose relative paths land under the API prefix.

    Every REST route moved to ``/api`` when the dashboard started sharing the
    origin, but tests still say ``client.get("/jobs")`` — which reads better
    and, more usefully, keeps the prefix in one place instead of in 700
    assertions. httpx appends a relative path to ``base_url``'s own path, so
    this is exact rather than a rewrite.

    Does **not** cover ``websocket_connect``: Starlette builds that URL with
    ``urljoin("ws://testserver", url)`` and never consults ``base_url``, so
    those few call sites spell out ``/api/ws`` themselves.
    """
    from fastapi.testclient import TestClient

    from jobpilot.api.main import API_PREFIX

    return TestClient(app, base_url=f"http://testserver{API_PREFIX}", **kwargs)


@pytest.fixture(autouse=True)
def _seed_with_sample_cv(monkeypatch):
    """The app bootstraps an *empty* CV — it ships no content. Tests need a
    realistic one to assert against, so ``ensure_master`` is pointed at the
    fictional ``cv/sample.py`` document for the whole suite."""
    from jobpilot.cv.sample import sample_document

    monkeypatch.setattr("jobpilot.cv.store.empty_document", sample_document)


@pytest.fixture(autouse=True)
def _no_real_claude_cli(monkeypatch):
    """No test spawns the real ``claude`` binary.

    The ``claude_cli`` provider's readiness check runs ``claude auth status``,
    and ``/stats/llm`` asks every provider whether it is ready. On a developer's
    machine with Claude Code installed that would make the suite shell out to
    it (and pass or fail on how that machine is logged in); on CI the binary is
    absent. Pinning "absent" makes every machine behave like CI. Tests of the
    provider patch ``find_claude`` back in explicitly.
    """
    import jobpilot.llm.claude_cli as cli

    monkeypatch.setattr(cli, "find_claude", lambda: None)
    monkeypatch.setattr(cli, "_auth_cache", {})


@pytest.fixture
def engine(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "jobpilot.sqlite"
    eng = make_engine(
        f"sqlite:///{path.as_posix()}",
        # Worker threads read and write the same database as the request thread.
        connect_args={"check_same_thread": False},
    )
    # WAL lets the queue's worker write while a request holds a read snapshot,
    # instead of the two deadlocking into "database is locked".
    with eng.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture(autouse=True)
def _forbid_unrouted_sessions(monkeypatch):
    """No test may reach ``DATABASE_URL`` by forgetting ``worker_db``.

    A test posting to a 202-background-task endpoint without requesting
    ``worker_db`` used to just... write to the real Postgres, silently, because
    ``session_scope()`` builds its session from the process-wide sessionmaker
    and nothing pointed that at the test engine. The task still reported "done"
    (PHASES.md, Phase cv-B — it produced a fabricated Master CV entry in the
    real database). ``worker_db`` re-patches the same target after this one has
    already run, so it wins for tests that request it; everything else now
    fails loudly instead of writing somewhere real.

    Two targets, not one: ``jobpilot.api.deps`` did ``from jobpilot.store.db
    import get_sessionmaker``, which binds its own name at import time, so
    patching ``store.db.get_sessionmaker`` alone leaves the request path's
    ``get_db`` untouched. Nothing currently reaches it -- every test overrides
    FastAPI's ``get_db`` directly -- but that's exactly the kind of thing a new
    test could get wrong the same way the original incident did.
    """

    def _unrouted():
        raise RuntimeError(
            "session_scope() (or FastAPI's default get_db) was called without "
            "worker_db pointing get_sessionmaker() at the test database -- "
            "request worker_db (or run_task, which depends on it), or override "
            "get_db via app.dependency_overrides, instead of hitting DATABASE_URL"
        )

    monkeypatch.setattr("jobpilot.store.db.get_sessionmaker", _unrouted)
    monkeypatch.setattr("jobpilot.api.deps.get_sessionmaker", _unrouted)


@pytest.fixture
def worker_db(session_factory, monkeypatch):
    """Point the queue's worker threads at the test database.

    Task bodies deliberately open their own session — a request's session cannot
    outlive the request — so overriding FastAPI's ``get_db`` never reaches them.
    They call ``store.db.session_scope``, which builds one from the process
    sessionmaker; this points that at the test engine instead.
    """
    monkeypatch.setattr("jobpilot.store.db.get_sessionmaker", lambda: session_factory)
    yield session_factory
    # Let this test's tasks finish before the next one starts, while the patch is
    # still in place — a straggler would otherwise run against a disposed engine.
    _wait_until_idle()


@pytest.fixture
def run_task(worker_db):
    """Drive one of the endpoints that answer 202 with a background task.

    The test has to wait, because the request now returns before the work starts.
    Returns the finished task dict whether it succeeded or failed: a task that
    failed is a result to assert on, not an error to raise.
    """
    auth = {"X-API-Token": get_secrets().jobpilot_api_token}

    def _run(client, response, timeout: float = 20.0) -> dict:
        assert response.status_code == 202, f"expected 202, got {response.status_code}: {response.text}"
        task_id = response.json()["id"]
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            task = client.get(f"/tasks/{task_id}", headers=auth).json()
            if task["status"] in ("done", "failed"):
                return task
            time.sleep(0.02)
        raise AssertionError(f"task {task_id} did not finish within {timeout}s")

    return _run


def _wait_until_idle(timeout: float = 20.0) -> None:
    """The queue is process-wide and single-worker; don't leak work across tests."""
    from jobpilot.orchestrator import queue

    deadline = time.monotonic() + timeout
    while queue.active() and time.monotonic() < deadline:
        time.sleep(0.02)


@pytest.fixture
def hold_task():
    """Pin a task in the queue for a job, so the "one task per job" guard can be
    tested without racing a real round to the finish line.

    With a fixture engine a tailor round completes in microseconds, so asserting
    that a *second* request is refused while the first is in flight is otherwise
    a coin flip.
    """
    release = threading.Event()

    def _hold(job_id: str, kind: str = "tailor"):
        from jobpilot.orchestrator import queue

        def body(_progress):
            release.wait(10)
            return {}

        return queue.submit(kind, body, label=f"holding {job_id}", job_id=job_id)

    yield _hold
    release.set()
    _wait_until_idle()
