"""Critique the Master CV against the crawled market, and keep the answer.

Two halves with different standing: ``market.snapshot`` is counted and every
figure on the page comes from it; the model's ``CvCritique`` is an opinion.
Both are stored together, so a critique can always be read beside the evidence
it was given.

The model addresses entries by index. Here every index is checked against the
CV it was given and resolved to a **title**, stored with the verdict: the page
must not look an index up in today's CV, which may have been reordered since.
Verdicts that point at nothing are dropped and counted, not passed on.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobpilot.analytics.market import _payloads
from jobpilot.critique import market
from jobpilot.critique.engine import CritiqueEngine
from jobpilot.critique.schema import CvCritique
from jobpilot.cv import store as cv_store
from jobpilot.cv.schema import CvDocument, ExperienceSection, ProjectsSection
from jobpilot.intake.service import cv_is_unfilled
from jobpilot.store.models import CvCritique as CritiqueRow

MAX_ROLE = 64


class CritiqueRefused(RuntimeError):
    """Nothing worth sending to a model — said before paying for the call."""


@dataclass(frozen=True)
class Cleaned:
    report: dict
    dropped: int


def clean(report: CvCritique, doc: CvDocument) -> Cleaned:
    """Keep the verdicts that point at real content, with titles resolved."""
    keys = {s.key: s for s in doc.sections}
    dropped = 0

    sections, seen_sections = [], set()
    for v in report.sections:
        if v.key not in keys or v.key in seen_sections:
            dropped += 1
            continue
        seen_sections.add(v.key)
        sections.append({**v.model_dump(), "title": keys[v.key].title})

    entries, seen_entries = [], set()
    for v in report.entries:
        section = keys.get(v.section_key)
        ok = (
            isinstance(section, (ExperienceSection, ProjectsSection))
            and 0 <= v.entry_index < len(section.entries)
            and (v.section_key, v.entry_index) not in seen_entries
        )
        if not ok:
            dropped += 1
            continue
        seen_entries.add((v.section_key, v.entry_index))
        entries.append({**v.model_dump(), "title": section.entries[v.entry_index].title})

    data = report.model_dump(mode="json")
    data["sections"], data["entries"] = sections, entries
    data["dropped"] = dropped
    return Cleaned(report=data, dropped=dropped)


def critique_master(
    db: Session, engine: CritiqueEngine, role: str = "", lang: str = "vi"
) -> CritiqueRow:
    """Review the current Master CV for ``role`` and store the result."""
    role = role.strip()[:MAX_ROLE]
    lang = lang if lang in ("vi", "en") else "vi"

    doc = cv_store.get_document(db, cv_store.MASTER_SCOPE).visible()
    if cv_is_unfilled(doc):
        # Same reason as the fit check: a review of the empty skeleton would be a
        # confident verdict about a CV that does not exist yet.
        raise CritiqueRefused("your Master CV is still empty — fill it in before asking for a review")
    row = cv_store.latest_version(db, cv_store.MASTER_SCOPE)
    version = row.version if row else 0

    payloads = _payloads(db)
    if not payloads:
        raise CritiqueRefused("no crawled jobs yet — run a crawl so there is a market to compare with")
    snap = market.snapshot(payloads, doc, role)
    if snap["jobs"] == 0:
        raise CritiqueRefused(f"no crawled job title matches the role {role!r} — try a broader one")

    report = engine.critique(doc, market.render(snap), role, lang)
    cleaned = clean(report, doc)

    saved = CritiqueRow(
        cv_version=version, role=role, lang=lang, report=cleaned.report, market=snap
    )
    db.add(saved)
    db.commit()
    db.refresh(saved)
    return saved


def latest(db: Session) -> CritiqueRow | None:
    return db.scalars(select(CritiqueRow).order_by(CritiqueRow.id.desc()).limit(1)).first()
