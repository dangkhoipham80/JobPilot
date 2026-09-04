"""Employers, the people at them, and how much of your search each one holds.

The list is a ``Page`` like every other list endpoint. The three counts on a row
are computed for the rows on that page only — a correlated subquery per row
across 160 companies would be three extra scans of ``jobs`` for a page of 25.
The two orderings that need a count to sort by use correlated subqueries, which
is the one place paying for them is unavoidable.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from jobpilot.api.deps import get_db, require_token
from jobpilot.api.paging import LimitParam, OffsetParam, page_list, page_query
from jobpilot.api.schemas import (
    CompanyDetailOut,
    CompanyIn,
    CompanyOut,
    CompanyPatch,
    HrContactIn,
    HrContactOut,
    JobOut,
    Page,
)
from jobpilot.apply.followup import SENT_RESULTS
from jobpilot.companies.service import company_key, resolve_company
from jobpilot.crawler.normalize import fit_column
from jobpilot.crawler.text import clean_text
from jobpilot.store.models import Application, Company, HrContact, Job

router = APIRouter(prefix="/companies", tags=["companies"], dependencies=[Depends(require_token)])

#: How many of an employer's postings the detail view carries. The Jobs page,
#: which is paged and filterable, is one click away for the rest — this is the
#: "what have I seen from them" glance, not a second jobs browser.
JOBS_ON_DETAIL = 20

#: What counts as having applied.
#:
#: ``SENT_RESULTS`` is imported, never restated — ``apply/outcome.py`` says so in
#: as many words, and this is exactly the drift it was guarding against. It is
#: ``{"success", "awaiting_user"}``: an ITviec or LinkedIn application is handed
#: off for you to submit and lands as ``awaiting_user``, and every other part of
#: the app already treats that as sent (the board shows it, the follow-up clock
#: starts, inbox sync matches replies to it, `/analytics` counts it in the reply
#: rate). Counting only ``success`` here would have shown `0 applied` for the
#: employers you are actually chasing — and since `order=applied` is the default,
#: it would have buried them under 150 rows the corpus provisioned by itself.
#: ``dry_run`` is absent on purpose: it never left the machine.


def _escape_like(term: str) -> str:
    """Make a user's search term literal for LIKE. Backslash first, or it would
    escape the escapes added after it."""
    for char in ("\\", "%", "_"):
        term = term.replace(char, f"\\{char}")
    return term


def _applied_jobs_subquery():
    """Distinct jobs at the correlated company with an application that went out."""
    return (
        select(func.count(distinct(Job.id)))
        .select_from(Job)
        .join(Application, Application.job_id == Job.id)
        .where(Job.company_id == Company.id, Application.result.in_(tuple(SENT_RESULTS)))
        .correlate(Company)
        .scalar_subquery()
    )


def _job_count_subquery():
    return (
        select(func.count(Job.id))
        .where(Job.company_id == Company.id)
        .correlate(Company)
        .scalar_subquery()
    )


def _counts_for(db: Session, ids: list[int]) -> dict[int, tuple[int, int, int]]:
    """``{company_id: (jobs, applied, contacts)}`` for the rows on this page."""
    if not ids:
        return {}
    jobs = dict(
        db.execute(
            select(Job.company_id, func.count(Job.id))
            .where(Job.company_id.in_(ids))
            .group_by(Job.company_id)
        ).all()
    )
    applied = dict(
        db.execute(
            select(Job.company_id, func.count(distinct(Job.id)))
            .join(Application, Application.job_id == Job.id)
            .where(Job.company_id.in_(ids), Application.result.in_(tuple(SENT_RESULTS)))
            .group_by(Job.company_id)
        ).all()
    )
    contacts = dict(
        db.execute(
            select(HrContact.company_id, func.count(HrContact.id))
            .where(HrContact.company_id.in_(ids))
            .group_by(HrContact.company_id)
        ).all()
    )
    return {i: (jobs.get(i, 0), applied.get(i, 0), contacts.get(i, 0)) for i in ids}


def _as_out(company: Company, counts: tuple[int, int, int]) -> CompanyOut:
    jobs, applied, contacts = counts
    return CompanyOut(
        id=company.id,
        name=company.name,
        normalized_name=company.normalized_name,
        job_count=jobs,
        applied_count=applied,
        contact_count=contacts,
    )


@router.get("", response_model=Page[CompanyOut])
def list_companies(
    db: Session = Depends(get_db),
    q: str | None = Query(None, description="search the employer name"),
    with_contacts: bool = Query(False, description="only employers with an HR contact on file"),
    order: str = Query("applied", pattern="^(applied|jobs|name)$"),
    limit: int = LimitParam(),
    offset: int = OffsetParam(),
) -> dict:
    stmt = select(Company)
    if q:
        # `%` and `_` are wildcards in LIKE, so a name containing either has to
        # be escaped or the search quietly answers a different question than the
        # one typed — "100%" would match "1000 anything".
        like = f"%{_escape_like(q)}%"
        # Both columns: typing "gitlab" should find a row displayed as "GitLab",
        # and typing "GitLab" should find one somebody renamed to "GitLab Inc".
        stmt = stmt.where(
            or_(
                Company.name.ilike(like, escape="\\"),
                Company.normalized_name.ilike(like, escape="\\"),
            )
        )
    if with_contacts:
        stmt = stmt.where(
            select(func.count(HrContact.id))
            .where(HrContact.company_id == Company.id)
            .correlate(Company)
            .scalar_subquery()
            > 0
        )

    # Default is "who have I actually applied to" — the question the page exists
    # to answer, and the one that floats the handful of live employers above the
    # ~150 rows the corpus provisioned on its own.
    if order == "name":
        stmt = stmt.order_by(Company.name.asc())
    elif order == "jobs":
        stmt = stmt.order_by(_job_count_subquery().desc())
    else:
        stmt = stmt.order_by(_applied_jobs_subquery().desc(), _job_count_subquery().desc())
    # `Company.id` last is what makes the order total: most employers tie at
    # zero applications, and a tie under LIMIT/OFFSET is how one row shows up on
    # two pages while another never shows up at all.
    stmt = stmt.order_by(Company.id.asc())

    rows, total = page_query(db, stmt, limit, offset)
    counts = _counts_for(db, [r.id for r in rows])
    return page_list([_as_out(r, counts[r.id]) for r in rows], total, limit, offset)


@router.post("", response_model=CompanyDetailOut, status_code=201)
def create_company(body: CompanyIn, db: Session = Depends(get_db)) -> CompanyDetailOut:
    """Track an employer by name.

    Upserts on the fold rather than erroring: typing "GitLab" when a row folded
    from "gitlab" already exists means you want *that* employer, and a 409 would
    send you hunting for a row you cannot see under the name you know it by.
    """
    if not company_key(body.name):
        raise HTTPException(status_code=422, detail="company name is required")
    company = resolve_company(db, body.name)
    assert company is not None  # company_key was non-empty, so resolve creates
    db.commit()
    db.refresh(company)
    return _detail(db, company)


@router.get("/{company_id}", response_model=CompanyDetailOut)
def get_company(company_id: int, db: Session = Depends(get_db)) -> CompanyDetailOut:
    return _detail(db, _require(db, company_id))


@router.patch("/{company_id}", response_model=CompanyDetailOut)
def patch_company(
    company_id: int, body: CompanyPatch, db: Session = Depends(get_db)
) -> CompanyDetailOut:
    """Rename an employer. ``normalized_name`` is untouched — see ``CompanyPatch``."""
    company = _require(db, company_id)
    name = clean_text(body.name)
    if not name:
        raise HTTPException(status_code=422, detail="company name is required")
    company.name = fit_column("company", name)
    db.commit()
    db.refresh(company)
    return _detail(db, company)


@router.post("/{company_id}/contacts", response_model=HrContactOut, status_code=201)
def add_contact(company_id: int, body: HrContactIn, db: Session = Depends(get_db)) -> HrContactOut:
    company = _require(db, company_id)
    contact = HrContact(company_id=company.id, **_contact_fields(body))
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return HrContactOut.model_validate(contact)


@router.patch("/{company_id}/contacts/{contact_id}", response_model=HrContactOut)
def patch_contact(
    company_id: int, contact_id: int, body: HrContactIn, db: Session = Depends(get_db)
) -> HrContactOut:
    contact = _require_contact(db, company_id, contact_id)
    for field, value in _contact_fields(body).items():
        setattr(contact, field, value)
    db.commit()
    db.refresh(contact)
    return HrContactOut.model_validate(contact)


@router.delete("/{company_id}/contacts/{contact_id}", response_model=CompanyDetailOut)
def delete_contact(
    company_id: int, contact_id: int, db: Session = Depends(get_db)
) -> CompanyDetailOut:
    """Remove a contact and hand back the company as it now stands.

    Returns the new state rather than a bare 204, matching ``DELETE /cv/{scope}/tex``:
    the caller's next move is always to redraw the card it just changed, and
    returning it saves a round-trip whose answer this function already holds.
    """
    company = _require(db, company_id)
    db.delete(_require_contact(db, company_id, contact_id))
    db.commit()
    db.refresh(company)
    return _detail(db, company)


# --------------------------------------------------------------------------- #
def _require(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="company not found")
    return company


def _require_contact(db: Session, company_id: int, contact_id: int) -> HrContact:
    contact = db.get(HrContact, contact_id)
    # The company is checked too, so a contact id from one employer cannot be
    # edited through another's URL — that would silently move a person's phone
    # number onto the wrong company's card.
    if contact is None or contact.company_id != company_id:
        raise HTTPException(status_code=404, detail="contact not found")
    return contact


def _contact_fields(body: HrContactIn) -> dict:
    name = clean_text(body.name)
    if not name:
        raise HTTPException(status_code=422, detail="contact name is required")
    # Clamped for the same reason job fields are: SQLite ignores VARCHAR widths
    # and Postgres answers an overlong value with StringDataRightTruncation
    # mid-flush — a 500 that names no field. A pasted mail signature is exactly
    # the kind of thing that arrives 400 characters long.
    return {
        "name": name[:128],
        "phone": _clamped(body.phone, 64),
        "email": _clamped(body.email, 320),
        # Text, not VARCHAR — a note is prose and has no width to overflow.
        "note": (body.note or "").strip() or None,
    }


def _clamped(value: str | None, width: int) -> str | None:
    """Trimmed to ``width``, or ``None`` when there is nothing there.

    ``None`` rather than ``""``: "no phone number on file" and "a phone number
    that is the empty string" are the same fact, and storing two spellings of it
    means every reader has to check for both.
    """
    return clean_text(value)[:width] or None


def _detail(db: Session, company: Company) -> CompanyDetailOut:
    counts = _counts_for(db, [company.id])[company.id]
    jobs = list(
        db.scalars(
            select(Job)
            .where(Job.company_id == company.id)
            .order_by(Job.posted_at.desc().nullslast(), Job.crawled_at.desc(), Job.id.desc())
            .limit(JOBS_ON_DETAIL + 1)
        )
    )
    base = _as_out(company, counts)
    return CompanyDetailOut(
        **base.model_dump(),
        contacts=[HrContactOut.model_validate(c) for c in company.contacts],
        jobs=[JobOut.model_validate(j) for j in jobs[:JOBS_ON_DETAIL]],
        # Asked for one more than shown, so "there are more" is a fact rather
        # than an inference from `len(jobs) == limit` — which is wrong exactly
        # when the count lands on the limit.
        jobs_truncated=len(jobs) > JOBS_ON_DETAIL,
    )
