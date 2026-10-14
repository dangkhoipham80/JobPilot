"""Pick the projects a tailored CV shows — the Master's projects are a pool.

The Master CV is the place to keep **every** project worth mentioning (CV Studio
is the store), so it grows past what one page can hold. A tailored CV should show
only the few that speak to the job: a Godot game says nothing to a Java backend
role, and a Spring Boot service says little to a game studio.

The model is asked to make that choice (``tailor/prompt.py``), and usually does.
This module is the floor under it, applied after the guard passed:

- the model chose an order → keep its first ``cap`` entries, in its order;
- the model left the order empty → rank by overlap with the job and keep the top
  ``cap``, ties broken by the Master's own order (the owner's priority).

Either way the cut is written into ``plan.changes``, so the review diff says
which projects were left out and why. Nothing here adds content: it only shortens
an index list, so the plan still passes ``check_plan``.
"""

from __future__ import annotations

import re

from jobpilot.cv.schema import CvDocument, Entry, ProjectsSection
from jobpilot.store.models import Job
from jobpilot.tailor.schema import Change, SectionPlan, TailorPlan

_MARKUP_RE = re.compile(r"[`*]")
_PAREN_RE = re.compile(r"\s*\(.*?\)\s*$")


def job_text(job: Job) -> str:
    """Everything in the posting a project could match against, lowercased."""
    payload = job.payload or {}
    skills = " ".join(payload.get("skills") or [])
    return " ".join([job.title or "", skills, payload.get("description_md") or ""]).lower()


def _mentions(text: str, term: str) -> bool:
    """Whole-term match, so "Java" does not count inside "JavaScript" and "C#"
    or "Next.js" still match despite their punctuation."""
    term = term.strip().lower()
    if not term:
        return False
    return re.search(rf"(?<![\w.#+]){re.escape(term)}(?![\w#+])", text) is not None


def relevance(entry: Entry, text: str) -> int:
    """How many of the project's technologies the posting names.

    The tech stack is the signal on purpose: it is the part of an entry that is
    a list of terms rather than prose, so a match means the job and the project
    share a technology, not a common English word.
    """
    return sum(1 for tech in entry.tech_stack if _mentions(text, tech))


def _name(entry: Entry) -> str:
    """ "Lumen -- Generative Lesson Platform (5 members, `Java`)" → "Lumen"."""
    title = _MARKUP_RE.sub("", entry.title)
    return _PAREN_RE.sub("", title).split(" -- ")[0].strip() or title.strip()


def limit_projects(plan: TailorPlan, master: CvDocument, job: Job, cap: int) -> TailorPlan:
    """Return ``plan`` with every projects section cut to at most ``cap`` entries.

    ``cap <= 0`` turns the limit off. A section the plan hides is left alone.
    """
    if cap <= 0:
        return plan

    text = job_text(job)
    plan = plan.model_copy(deep=True)
    by_key = {sp.key: sp for sp in plan.sections}

    for section in master.sections:
        if not isinstance(section, ProjectsSection) or len(section.entries) <= cap:
            continue
        sp = by_key.get(section.key)
        if sp is not None and not sp.enabled:
            continue

        if sp is not None and sp.entry_order:
            if len(sp.entry_order) <= cap:
                continue
            chosen = sp.entry_order[:cap]
            how = f"kept the {cap} the plan ranked highest"
        else:
            scores = [relevance(e, text) for e in section.entries]
            ranked = sorted(range(len(section.entries)), key=lambda i: (-scores[i], i))
            chosen = ranked[:cap]
            how = f"kept the {cap} whose tech stack overlaps the posting most"

        if sp is None:
            sp = SectionPlan(key=section.key)
            plan.sections.append(sp)
            by_key[section.key] = sp
        dropped = [i for i in range(len(section.entries)) if i not in chosen]
        sp.entry_order = chosen

        # Per-entry edits for a dropped project would point at nothing on the page.
        plan.entries = [
            ep
            for ep in plan.entries
            if not (ep.section_key == section.key and ep.entry_index in dropped)
        ]
        names = ", ".join(_name(section.entries[i]) for i in dropped)
        plan.changes.append(
            Change(
                section=section.key,
                what=f"Left out {len(dropped)} less relevant project(s): {names}",
                reason=f"project limit ({cap}); {how}",
            )
        )
    return plan
