"""Operations surface: trigger crawls, watch tasks, read run history, edit settings.

Crawling is the one action that genuinely cannot answer inside a request — it
walks several sites behind a rate limiter. So ``POST /crawl`` returns 202 with a
task id, and progress arrives over the existing WebSocket as ``task_updated``.

Settings writes go to a gitignored overlay (``config.local.yaml``) rather than
editing ``config.yaml``, whose comments document the email safety gates.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jobpilot.api.deps import get_db, require_token
from jobpilot.api.paging import LimitParam, OffsetParam, page_list, page_query
from jobpilot.api.schemas import CrawlRequest, Page, RunOut, SettingsIn, TaskOut
from jobpilot.config import (
    LOCAL_CONFIG_PATH,
    LOCKED_SETTINGS,
    get_config,
    locked_violations,
    save_local_config,
)
from jobpilot.crawler.pipeline import MAX_QUERIES, default_query, split_queries
from jobpilot.orchestrator import crawl_body, queue
from jobpilot.store.models import Job, Run

router = APIRouter(tags=["ops"], dependencies=[Depends(require_token)])


@router.post("/crawl", response_model=TaskOut, status_code=202)
def start_crawl(
    query: str | None = None,
    no_robots: bool = False,
    body: CrawlRequest | None = None,
) -> JSONResponse:
    """Queue a crawl. Returns immediately; watch the task for progress.

    Only one crawl at a time — a second would race the same sites and trip
    their rate limits.

    Everything is optional and scoped to this run: an empty request crawls every
    enabled source with the configured query and page size, which is what the
    CLI and cron want. The dashboard sends a body to narrow it.
    """
    req = body or CrawlRequest()
    resolved_query = req.query or query
    # Refused up front, not truncated: dropping the ninth keyword silently would
    # report a crawl that searched for less than you asked.
    if len(split_queries(resolved_query)) > MAX_QUERIES:
        raise HTTPException(
            status_code=422,
            detail=f"at most {MAX_QUERIES} keywords per crawl — each one is a full pass over every site",
        )
    running = queue.active(kind="crawl")
    if running:
        raise HTTPException(
            status_code=409, detail=f"a crawl is already {running[0].status} ({running[0].id})"
        )

    known = {s.key for s in get_config().sources}
    unknown = [s for s in (req.sources or []) if s not in known]
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown source(s): {', '.join(unknown)}")

    task = queue.submit(
        "crawl",
        crawl_body(
            query=resolved_query,
            respect_robots=not (req.no_robots or no_robots),
            sources=req.sources,
            limit=req.limit,
        ),
        label=_crawl_label(resolved_query, req.sources),
    )
    return JSONResponse(status_code=202, content=TaskOut(**task.to_dict()).model_dump(mode="json"))


def _crawl_label(query: str | None, sources: list[str] | None) -> str:
    """A label you can tell two runs apart by, in the queue and in history."""
    where = "+".join(sources) if sources else "all sources"
    queries = split_queries(query)
    return f"crawl {where}" + (f" · {', '.join(queries)}" if queries else "")


def _request_of(run: Run) -> dict | None:
    """What a past crawl asked for: ``{queries, sources, limit}``, or None.

    Runs record their request since multi-keyword crawls landed. Older rows are
    read back from what they did keep — the query string and the sites that ran
    — with ``limit`` unknown (None = the configured default). ``sources`` None
    means "every enabled source", as in a crawl request.
    """
    stats = run.stats or {}
    req = stats.get("request")
    if isinstance(req, dict) and req.get("queries"):
        queries = [q for q in req["queries"] if isinstance(q, str) and q.strip()]
        sources, limit = req.get("sources"), req.get("limit")
    else:
        queries = split_queries(stats.get("query") if isinstance(stats.get("query"), str) else "")
        sites = stats.get("sites")
        sources = sorted(sites) if isinstance(sites, dict) and sites else None
        limit = None
    if not queries:
        return None
    return {
        "queries": queries,
        "sources": [s for s in sources if isinstance(s, str)]
        if isinstance(sources, list) and sources
        else None,
        "limit": limit if isinstance(limit, int) and limit > 0 else None,
    }


@router.get("/crawl/recent")
def recent_crawls(limit: int = Query(3, ge=1, le=10), db: Session = Depends(get_db)) -> list[dict]:
    """The last ``limit`` *distinct* crawl setups, newest first, ready to rerun.

    Distinct because the scheduled crawl repeats one setup twice a day: three
    identical rows would crowd out the one-off search you actually want back.
    Each item carries exactly what ``POST /crawl`` takes, so rerunning is
    sending it back unchanged.
    """
    out: list[dict] = []
    seen: set[tuple] = set()
    default_limit = get_config().crawl.jobs_per_site
    stmt = select(Run).where(Run.kind == "crawl").order_by(Run.id.desc()).limit(100)
    for run in db.scalars(stmt):
        req = _request_of(run)
        if req is None:
            continue
        key = (
            tuple(q.casefold() for q in req["queries"]),
            tuple(sorted(req["sources"])) if req["sources"] else None,
            # Asking for the default by number is asking for the default.
            None if req["limit"] == default_limit else req["limit"],
        )
        if key in seen:
            continue
        seen.add(key)
        totals = (run.stats or {}).get("totals") or {}
        out.append(
            {
                "run_id": run.id,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "query": ", ".join(req["queries"]),
                **req,
                "inserted": totals.get("inserted"),
            }
        )
        if len(out) >= limit:
            break
    return out


@router.get("/crawl/setup")
def crawl_setup(db: Session = Depends(get_db)) -> dict:
    """Everything the crawl form needs: what can run, and what to search for.

    Search terms come from your Master CV rather than a canned list, so a
    suggested query is one you can actually back up. An empty CV yields empty
    lists rather than an invented stack.

    ``sources`` reports ``ready`` per source — enabled in Settings is not the
    same as implemented, and a form that offers a source with no scraper behind
    it just produces a crawl that silently does nothing.
    """
    from jobpilot.crawler.registry import SCRAPERS
    from jobpilot.crawler.suggest import suggest_keywords
    from jobpilot.cv.store import get_document

    cfg = get_config()
    try:
        found = suggest_keywords(get_document(db, "master"))
    except Exception:  # no CV saved yet — the form still has to render
        found = {"tech": [], "roles": []}

    return {
        **found,
        "stacks": list(cfg.crawl.stacks),
        "default_query": default_query(cfg),
        "jobs_per_site": cfg.crawl.jobs_per_site,
        "sources": [
            {"key": s.key, "enabled": s.enabled, "ready": s.key in SCRAPERS} for s in cfg.sources
        ],
    }


@router.get("/tasks", response_model=Page[TaskOut])
def list_tasks(
    kind: str | None = None,
    limit: int = LimitParam(),
    offset: int = OffsetParam(),
) -> dict:
    """Recent tasks, newest first.

    ``total`` is the size of the queue's *retained* history, not of every task
    ever run: the queue lives in memory and keeps the last 50, and a restart
    empties it. Worth knowing before reading this number as a workload metric.
    """
    everything = queue.list(limit=None, kind=kind)
    window = everything[offset : offset + limit]
    return page_list([TaskOut(**t.to_dict()) for t in window], len(everything), limit, offset)


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: str) -> TaskOut:
    task = queue.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found (the queue keeps the last 50)")
    return TaskOut(**task.to_dict())


@router.get("/runs", response_model=Page[RunOut])
def list_runs(
    kind: str | None = None,
    limit: int = LimitParam(),
    offset: int = OffsetParam(),
    db: Session = Depends(get_db),
) -> dict:
    """Persisted history of crawl/tailor/apply runs, newest first."""
    stmt = select(Run)
    if kind:
        stmt = stmt.where(Run.kind == kind)
    # Run.id is unique, so ordering by it alone is already a total order.
    rows, total = page_query(db, stmt.order_by(Run.id.desc()), limit, offset)

    counts = dict(
        db.execute(
            select(Job.run_id, func.count())
            .where(Job.run_id.in_([r.id for r in rows]))
            .group_by(Job.run_id)
        ).all()
    )
    out = []
    for row in rows:
        item = RunOut.model_validate(row)
        item.job_count = counts.get(row.id, 0)
        out.append(item)
    return page_list(out, total, limit, offset)


@router.get("/settings")
def read_settings() -> dict:
    """The resolved config (base + overlay). Secrets are never included.

    Carries ``locked`` so the Settings page can render those controls read-only.
    A disabled switch explains itself; one that moves and then fails on save
    teaches the user that the page is unreliable.
    """
    return {
        **get_config().model_dump(),
        "locked": [".".join(path) for path in LOCKED_SETTINGS],
    }


@router.put("/settings")
def write_settings(body: SettingsIn) -> dict:
    """Patch the overlay. Rejected as a whole if the result wouldn't validate."""
    patch = body.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(status_code=422, detail="nothing to change")

    # The email gates are not editable over HTTP at any privilege level; see
    # config.LOCKED_SETTINGS. 403 and not 422: the request is well-formed, it is
    # simply not something this interface is allowed to do.
    locked = locked_violations(patch)
    if locked:
        raise HTTPException(
            status_code=403,
            detail=(
                f"{', '.join(locked)} can only be changed by editing "
                f"{LOCAL_CONFIG_PATH.name} on the host, then restarting"
            ),
        )
    try:
        return save_local_config(patch).model_dump()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"invalid settings: {exc}") from exc
