"""Paste a job description in, and ask how well it fits.

Registered **before** ``routes.jobs`` for the reason ``routes.review`` is: that
router's ``GET /{job_id:path}`` is greedy and would otherwise swallow
``/jobs/x/fit``. ``POST /jobs/intake`` needs the same precedence for a second
reason — ``POST /jobs`` is a sibling, and a path segment is not a job id.

Neither endpoint answers 202. Every other model call in the app runs on the task
queue; these two do not, and ``intake/service.py`` records why — one structured
call each, a user waiting at a form, and a single-worker queue that a running
crawl would park them behind for minutes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from jobpilot import llm
from jobpilot.api.deps import get_db, require_token
from jobpilot.api.schemas import (
    FitOut,
    IntakeFileIn,
    IntakeFileOut,
    IntakeIn,
    IntakeOut,
    JdSectionsOut,
)
from jobpilot.cv import importer as uploads
from jobpilot.intake import service
from jobpilot.intake.engine import IntakeEngine, IntakeError, default_engine

router = APIRouter(prefix="/jobs", tags=["intake"], dependencies=[Depends(require_token)])


def get_engine() -> IntakeEngine:
    """Overridden in tests with a fixture engine (no network, no API key).

    The key pre-flight lives in the dependency, not the route body, for the same
    reason it does in ``routes/review.py``: a test supplying its own engine must
    not be asked for a key it has no use for, or the suite starts passing and
    failing on whether the machine happened to have one.
    """
    blocked = llm.blocker("intake")
    if blocked:
        raise HTTPException(status_code=409, detail=blocked)
    return default_engine()


@router.post("/intake", response_model=IntakeOut)
def read_paste(
    body: IntakeIn,
    engine: IntakeEngine = Depends(get_engine),
) -> IntakeOut:
    """Read a pasted posting into form fields. Saves nothing.

    200, not 201: no resource is created. The next step is the ordinary
    ``POST /jobs`` with whatever the user left standing after reading this over,
    which is what keeps a hand-added job identical whether or not a model helped
    fill the form in.
    """
    try:
        result = service.extract_jd(body.text, engine, url=body.url)
    except service.IntakeRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntakeError as exc:
        # 502, not 500: the provider failed, this app did not. The distinction
        # is what tells the user to check /models rather than the logs.
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    extract = result.extract
    return IntakeOut(
        title=extract.title,
        company=extract.company,
        location=extract.location,
        salary=extract.salary,
        level=extract.level,
        employment_type=extract.employment_type,
        work_mode=result.work_mode or "",
        city=result.city,
        skills=extract.skills,
        sections=JdSectionsOut(**result.sections.model_dump()),
        description_md=result.description_md,
        apply_email=extract.apply_email,
        language=extract.language,
        flags=result.flags,
        notes=result.notes,
    )


@router.post("/intake/file", response_model=IntakeFileOut)
def read_file(
    body: IntakeFileIn,
    engine: IntakeEngine = Depends(get_engine),
) -> IntakeFileOut:
    """Get the text out of a posting uploaded as images or a PDF. Saves nothing.

    Text only — the fields are read from it by ``POST /jobs/intake``, the same
    call a paste makes, once the text is in the form. Two requests rather than
    one so that what gets stored as the job's description is what the user saw
    in the box, not something that went from a picture to a row unseen.
    """
    try:
        files = uploads.decode_uploads([(f.name, f.data) for f in body.files])
        reading = service.read_files(files, engine)
    except (uploads.CvImportRefused, service.IntakeRefused) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntakeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return IntakeFileOut(
        text=reading.text,
        transcribed=reading.transcribed,
        unreadable=reading.unreadable,
        files=reading.files,
    )


@router.post("/{job_id:path}/fit", response_model=FitOut)
def assess(
    job_id: str,
    db: Session = Depends(get_db),
    engine: IntakeEngine = Depends(get_engine),
) -> FitOut:
    """Score a saved job against the Master CV.

    Allowed from any status on purpose. The other job endpoints gate on state
    because they move the job through the funnel; this one only reads and
    reports, and "how well did my CV match the job I got rejected from" is a
    fair question to ask afterwards.
    """
    try:
        outcome = service.assess_fit(db, job_id, engine)
    except service.IntakeRefused as exc:
        status = 404 if "not found" in str(exc) else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except IntakeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return FitOut(
        **outcome.report.model_dump(mode="json"), assessed_at=outcome.assessed_at
    )
