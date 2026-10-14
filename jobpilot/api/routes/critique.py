"""Review the Master CV against the crawled market (advisory — never edits the CV).

Synchronous, like the fit check (``routes/intake.py``): one structured call, the
user waiting on the page, and a single-worker queue a running crawl would park
it behind for minutes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from jobpilot import llm
from jobpilot.api.deps import get_db, require_token
from jobpilot.api.schemas import CritiqueIn, CritiqueOut
from jobpilot.critique import service
from jobpilot.critique.engine import CritiqueEngine, CritiqueError, default_engine
from jobpilot.critique.market import ROLE_PATTERNS
from jobpilot.cv import store as cv_store
from jobpilot.store.models import CvCritique

router = APIRouter(prefix="/cv/master/critique", tags=["cv"], dependencies=[Depends(require_token)])


def get_engine() -> CritiqueEngine:
    """Overridden in tests. Key pre-flight here, not in the body — see routes/intake."""
    blocked = llm.blocker("intake")
    if blocked:
        raise HTTPException(status_code=409, detail=blocked)
    return default_engine()


def _out(db: Session, row: CvCritique) -> CritiqueOut:
    current = cv_store.latest_version(db, cv_store.MASTER_SCOPE)
    return CritiqueOut(
        id=row.id,
        cv_version=row.cv_version,
        current_version=current.version if current else 0,
        role=row.role,
        lang=row.lang,
        report=row.report,
        market=row.market,
        created_at=row.created_at,
        roles=list(ROLE_PATTERNS),
    )


@router.get("", response_model=CritiqueOut | None)
def latest(db: Session = Depends(get_db)) -> CritiqueOut | None:
    """The most recent critique, or null when none has been made."""
    row = service.latest(db)
    return _out(db, row) if row else None


@router.post("", response_model=CritiqueOut)
def critique(
    body: CritiqueIn,
    db: Session = Depends(get_db),
    engine: CritiqueEngine = Depends(get_engine),
) -> CritiqueOut:
    try:
        row = service.critique_master(db, engine, role=body.role, lang=body.lang)
    except service.CritiqueRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CritiqueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _out(db, row)
