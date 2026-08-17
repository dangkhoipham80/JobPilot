"""FastAPI application entrypoint (REST + WebSocket + the built dashboard).

Run with ``uvicorn jobpilot.api.main:app`` or ``python -m jobpilot.cli serve``.
Binds to localhost only; reachable from other devices solely over Tailscale,
which terminates TLS and proxies back to 127.0.0.1 (PLAN.md §5.6).

**Every API route lives under ``/api``.** It has to: the dashboard is a
client-side router serving pages at ``/jobs``, ``/cv``, ``/settings`` and
``/applications``, which are the very paths the API answers on. Sharing an
origin without a prefix means refreshing the browser on ``/jobs`` renders a JSON
array instead of the page.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from jobpilot import __version__
from jobpilot.api.routes import analytics, apply, cv, inbox, jobs, ops, review, stats
from jobpilot.api.security import check_api_token
from jobpilot.api.static import mount_spa
from jobpilot.api.ws import manager, websocket_endpoint
from jobpilot.orchestrator import queue

#: Prefix for every REST route and the WebSocket. Anything *not* under it is the
#: dashboard's own routing and is answered with ``index.html``.
API_PREFIX = "/api"

# Vite dev server (Web Dashboard, Phase 4) origins. Only reachable in dev:
# `npm run dev` proxies /api to this process, so the deployed build is
# same-origin and sends no preflight at all.
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Refuse to serve on a placeholder token rather than handing the whole
    # dashboard — CV, mailbox, apply — to anyone who guesses "changeme".
    # In lifespan and not in create_app() because building the app is also what
    # the test suite does, and a checkout without a .env should still be able to
    # run its tests; what it must not do is *listen*.
    check_api_token()
    # Worker threads publish task progress by hopping back onto this loop.
    queue.bind(asyncio.get_running_loop(), manager.broadcast)
    yield
    queue.shutdown(wait=False)


def create_app(serve_spa: bool = True) -> FastAPI:
    app = FastAPI(title="JobPilot API", version=__version__, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Unauthenticated liveness probe. Registered at both roots on purpose: an
    # uptime monitor or a systemd readiness check wants the short one, and an
    # API client that prefixes everything wants the other. Neither should have
    # to know about the split.
    @app.get("/health", tags=["meta"])
    @app.get(f"{API_PREFIX}/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    # review + apply first: jobs' GET /{job_id:path} is greedy and would shadow
    # /jobs/{id}/review and /jobs/{id}/cv.
    for router in (
        review.router,
        apply.router,
        apply.board,
        jobs.router,
        stats.router,
        analytics.router,
        cv.router,
        inbox.router,
        ops.router,
    ):
        app.include_router(router, prefix=API_PREFIX)
    app.add_api_websocket_route(f"{API_PREFIX}/ws", websocket_endpoint)

    # Last, so it can see every route above and knows which 404s are the API's.
    if serve_spa:
        mount_spa(app)
    return app


app = create_app()
