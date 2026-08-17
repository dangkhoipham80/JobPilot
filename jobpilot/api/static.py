"""Serve the built dashboard from the API process, same-origin.

Two servers on two ports is a dev-time convenience (Vite's HMR), not a way to
run. Same-origin means the browser sends no preflight, the WebSocket inherits
the page's scheme, and — the reason this exists — there is exactly one address
to put behind Tailscale instead of two.

Mounted **last** so every API route is matched first. The catch-all below still
has to know which paths belong to the API, because a 404 that renders the
dashboard is worse than a 404: ``GET /stats/typoo`` would answer ``200`` with an
HTML page, and a fetch expecting JSON reports "unexpected token '<'" instead of
"no such endpoint".
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from jobpilot.config import REPO_ROOT

DIST_DIR = REPO_ROOT / "web" / "dist"

#: Vite writes content-hashed names (``index-BOF9OOGL.js``) into this directory
#: and nowhere else. A hash changes whenever the bytes do, so a stale copy can
#: never be served under a name that is still referenced.
_HASHED_DIR = "assets"

#: Only for ``_HASHED_DIR``. Applying it more widely is the trap: ``index.html``
#: is what *names* the hashed files, so caching it for a year pins the browser
#: to the previous build; and ``logos/*.png`` are copied through unhashed, so a
#: replaced logo would never be picked up. Both look fine until the first deploy
#: after the cache is warm, which is the worst time to find out.
_IMMUTABLE = "public, max-age=31536000, immutable"

#: Everything else revalidates. Cheap: the response is a 304 when unchanged.
_REVALIDATE = "no-cache"


def api_roots(app: FastAPI) -> set[str]:
    """First path segment of every route registered so far.

    Derived rather than hardcoded: a router added later is covered the day it is
    added, instead of the day someone remembers this file.
    """
    roots = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        segment = path.split("/")[1] if path.startswith("/") and len(path) > 1 else ""
        # A router mounted at a parameter root would swallow everything; none
        # exist today, and one added later should not silently disable the SPA.
        if segment and not segment.startswith("{"):
            roots.add(segment)
    return roots


def mount_spa(app: FastAPI, dist: Path | None = None) -> bool:
    """Serve ``web/dist`` under ``app``. Returns False when there is no build.

    A missing build is the normal state during development (``npm run dev``
    serves the frontend itself), so it is not an error — but the API must not
    then answer ``/`` with an HTML page it does not have.
    """
    dist = (dist or DIST_DIR).resolve()
    index = dist / "index.html"
    if not index.is_file():
        return False

    reserved = api_roots(app)

    # No StaticFiles mount for /assets: a mount is matched before this route and
    # would answer with its own headers, so the cache policy below would silently
    # not apply to the one directory it exists for. One code path, one policy.
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        root = full_path.split("/")[0]
        if root in reserved:
            # Belongs to the API and no route claimed it — say so in JSON.
            raise HTTPException(status_code=404, detail="not found")

        candidate = (dist / full_path).resolve()
        # A client-side route ("/jobs" is both an API path and a page) has no
        # file behind it, so anything that is not a real file inside dist falls
        # through to index.html and lets the router sort it out.
        # is_relative_to keeps "../../etc/passwd" from escaping the directory.
        if full_path and candidate.is_relative_to(dist) and candidate.is_file():
            cache = _IMMUTABLE if root == _HASHED_DIR else _REVALIDATE
            return FileResponse(candidate, headers={"Cache-Control": cache})
        return FileResponse(index, headers={"Cache-Control": _REVALIDATE})

    return True
