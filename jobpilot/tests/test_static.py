"""Serving the dashboard from the API process (jobpilot/api/static.py).

Builds a fake ``web/dist`` rather than depending on a real ``npm run build``:
the suite has to pass on a checkout that has never built the frontend.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jobpilot.api.static import mount_spa


@pytest.fixture
def dist(tmp_path):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "logos").mkdir()
    (d / "index.html").write_text("<!doctype html><title>JobPilot</title>", encoding="utf-8")
    (d / "assets" / "index-ABC123.js").write_text("console.log(1)", encoding="utf-8")
    (d / "logos" / "itviec.png").write_bytes(b"\x89PNG\r\n")
    return d


@pytest.fixture
def client(dist):
    app = FastAPI()

    @app.get("/api/jobs")
    def jobs():
        return {"items": []}

    assert mount_spa(app, dist) is True
    return TestClient(app)


def test_root_serves_the_dashboard(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<!doctype html>" in r.text


def test_a_client_side_route_falls_through_to_index(client):
    """Refreshing the browser on /jobs must render the page, not a JSON array.
    This is the whole reason the API moved under /api."""
    r = client.get("/jobs")
    assert r.status_code == 200
    assert "<title>JobPilot</title>" in r.text


def test_a_real_api_route_still_wins(client):
    assert client.get("/api/jobs").json() == {"items": []}


def test_an_unmatched_api_path_is_json_404_not_the_dashboard(client):
    """Falling through to index.html would answer 200 + HTML, and a fetch
    expecting JSON would report "unexpected token '<'" instead of "no such
    endpoint" — a full afternoon pointed at the wrong layer."""
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


def test_hashed_assets_are_immutable(client):
    r = client.get("/assets/index-ABC123.js")
    assert r.status_code == 200
    assert "immutable" in r.headers["cache-control"]


def test_index_is_never_immutable(client):
    """index.html names the hashed bundle. Cache it for a year and the browser
    is pinned to the previous build across the next deploy."""
    for path in ("/", "/index.html", "/some/client/route"):
        assert "immutable" not in client.get(path).headers["cache-control"], path


def test_unhashed_files_are_not_immutable(client):
    """Logos are copied through without a content hash, so a replaced logo would
    never reach anyone who had already loaded the old one."""
    assert "immutable" not in client.get("/logos/itviec.png").headers["cache-control"]


def test_traversal_outside_dist_is_refused(tmp_path, dist):
    """`.env` sits one level above `web/dist`, so this is not hypothetical.

    Driven through the handler rather than the client on purpose: httpx
    normalises `..` out of the path before it is ever sent, so a client-level
    test passes without the guard ever running — green for the wrong reason.
    """
    (tmp_path / "secret.txt").write_text("SMTP_PASSWORD=hunter2", encoding="utf-8")

    app = FastAPI()
    mount_spa(app, dist)
    handler = next(r.endpoint for r in app.routes if getattr(r, "path", "") == "/{full_path:path}")

    for attempt in ("../secret.txt", "../../secret.txt", "assets/../../secret.txt"):
        # Falling back to the dashboard is the only allowed outcome.
        assert Path(handler(attempt).path).name == "index.html", attempt


def test_no_build_is_not_an_error(tmp_path):
    """A checkout that has never run `npm run build` still serves the API; it
    just has no dashboard to hand out."""
    app = FastAPI()
    assert mount_spa(app, tmp_path / "missing") is False


def test_api_roots_are_derived_from_the_app(dist):
    """Hardcoding the reserved prefixes would mean a router added later quietly
    starts returning HTML on its 404s."""
    app = FastAPI()

    @app.get("/api/x")
    def x():
        return {}

    @app.get("/health")
    def health():
        return {}

    mount_spa(app, dist)
    client = TestClient(app)
    assert client.get("/api/unknown").status_code == 404
    assert client.get("/health/unknown").status_code == 404
    # Not an API root, so it is a dashboard route.
    assert client.get("/applications").status_code == 200
