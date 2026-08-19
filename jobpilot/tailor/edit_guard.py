"""Provenance guardrail for Master CV edits (SKILL.md §0).

The tailor guard asks *"is this already on the CV?"*, which is the right question
when the CV is the whole universe of truth. Editing the Master CV is where new
truth legitimately enters, so asking the same question there would reject every
real project the user just finished — and answering it by widening the
vocabulary would license the model to invent freely with the user's words as
cover. The question here is different:

    Does every new word and every new number trace to something the *user* said?

Hence two sources, and an op may draw only on the one its kind allows:

* ``rewrite`` / ``merge`` / ``drop`` rework existing content, so their text must
  trace to the **Master CV**.
* ``add_bullet`` / ``add_entry`` introduce facts, so they must cite a
  ``source_quote`` that genuinely appears in the **instruction** — the same
  mechanism inbox sync uses for email (``apply/inbox.check_verdict``), sharing
  one normaliser via ``jobpilot.textnorm``.

A ``rewrite`` may also carry a quote, for when the user corrects a fact in place
("my GPA is now 3.7"). The rule is one sentence: *anything not traceable to the
Master CV must be traceable to a verified quote.*

### Why numbers get their own check

``guard.unknown_terms`` only sees technology-*looking* tokens, and ``_TOKEN_RE``
requires a token to start with a letter — so "increased throughput by 40%" and
"led a team of 12 engineers" contain nothing it can see. That is survivable in
tailoring, where the schema forbids writing such a sentence at all, but here the
model does write prose, and an invented metric is the single most damaging thing
it could put on a CV. Digits are therefore checked directly, against the same
two sources.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from jobpilot.cv.schema import (
    BulletsSection,
    CvDocument,
    EducationSection,
    ExperienceSection,
    ParagraphSection,
    ProjectsSection,
)
from jobpilot.tailor.edit import NA, MasterEditPlan
from jobpilot.tailor.guard import GuardrailViolation, PlanReport, terms_in, unknown_terms, vocabulary
from jobpilot.textnorm import quote_appears_in

#: Ops that put a *new* claim on the CV and therefore must cite the instruction.
ADDITIVE_OPS = frozenset({"add_bullet", "add_entry"})

#: Maximal runs of digits. Decimal points and separators are deliberately not
#: joined: "3.7" yields {"3", "7"}, so a rewrite claiming 3.7 when the CV says
#: 3.5 is caught on the "7".
_DIGITS = re.compile(r"\d+")

__all__ = ["check_edit_plan", "GuardrailViolation", "PlanReport"]


@dataclass
class _Sources:
    """What this edit is allowed to draw on."""

    master_vocab: set[str]
    master_digits: set[str]
    instruction: str
    instruction_vocab: set[str]
    instruction_digits: set[str]


def _digits(text: str) -> set[str]:
    return set(_DIGITS.findall(text or ""))


def _master_text(doc: CvDocument) -> str:
    """Everything the master says, as one blob — for digit provenance."""
    parts: list[str] = []
    for s in doc.sections:
        parts.append(s.title)
        if isinstance(s, ParagraphSection):
            parts.append(s.text)
        elif isinstance(s, BulletsSection):
            for it in s.items:
                parts += [it.label or "", it.text, it.date or ""]
        elif isinstance(s, EducationSection):
            for e in s.entries:
                parts += [e.degree, e.institution, e.location, e.date, *e.items]
        elif isinstance(s, (ExperienceSection, ProjectsSection)):
            for e in s.entries:
                parts += [e.title, e.date, e.role or "", *e.items, *e.tech_stack]
    return " ".join(parts)


def _check_text(label: str, text: str, op, src: _Sources, out: list[str]) -> None:
    """Every term and every number in ``text`` must trace to an allowed source.

    Once an op has earned the instruction as a source, it draws on the *whole*
    instruction rather than only the quoted span. Licensing from the span alone
    was tried first and is wrong in practice: one entry's facts are spread across
    a sentence, so "add a project called JobPilot: a crawler built with FastAPI"
    quoted at the clause about the crawler rejected the project's own *name*. The
    quote's job is to be a citation a human can check in the diff; the user's
    words as a whole are what licenses content.
    """
    if not text.strip():
        return

    quote_ok = bool(op.source_quote.strip()) and quote_appears_in(op.source_quote, src.instruction)
    vocab = set(src.master_vocab)
    allowed_digits = set(src.master_digits)
    if quote_ok:
        vocab |= src.instruction_vocab
        allowed_digits |= src.instruction_digits

    invented = unknown_terms(text, vocab)
    if invented:
        out.append(
            f"{label}: mentions {', '.join(invented)}, which is neither in the Master CV "
            "nor in the quoted instruction — remove it or quote the user saying it"
        )

    new_numbers = sorted(_digits(text) - allowed_digits)
    if new_numbers:
        out.append(
            f"{label}: introduces the number(s) {', '.join(new_numbers)} that the user "
            "never gave — a metric the CV cannot back up is exactly what SKILL.md §0 forbids"
        )


def _section_index(doc: CvDocument):
    return {s.key: s for s in doc.sections}


def check_edit_plan(plan: MasterEditPlan, master: CvDocument, instruction: str) -> PlanReport:
    """Validate an edit plan. Empty violations means it is safe to apply."""
    out: list[str] = []
    by_key = _section_index(master)
    src = _Sources(
        master_vocab=vocabulary(master),
        master_digits=_digits(_master_text(master)),
        instruction=instruction,
        instruction_vocab=terms_in(instruction),
        instruction_digits=_digits(instruction),
    )

    for n, (kind, op) in enumerate(plan.labelled()):
        label = f"{kind}[{n}]"
        section = by_key.get(op.section_key)
        if section is None:
            out.append(f"{label}: unknown section key {op.section_key!r}")
            continue

        quote = getattr(op, "source_quote", "")
        # --- provenance: an additive op without a real quote is refused outright
        if kind in ADDITIVE_OPS:
            if not quote.strip():
                out.append(
                    f"{label}: adding to the Master CV requires source_quote — copy the "
                    "words of the instruction that state this fact"
                )
                continue
            if not quote_appears_in(quote, instruction):
                out.append(
                    f"{label}: source_quote {quote!r} does not appear in the "
                    "instruction; quote it word for word instead of paraphrasing"
                )
                continue
        elif quote.strip() and not quote_appears_in(quote, instruction):
            out.append(f"{label}: source_quote does not appear in the instruction")

        _check_target(label, kind, op, section, out)
        for field_label, text in _texts_of(kind, op):
            _check_text(f"{label} {field_label}", text, op, src, out)

    _check_conflicts(plan, out)
    return PlanReport(violations=out)


def _check_conflicts(plan: MasterEditPlan, out: list[str]) -> None:
    """Two ops may not claim the same bullet.

    ``apply_edits`` resolves every index against the original list, so a plan
    that both merges bullet 0 and rewrites bullet 0 has a *silent* winner — the
    merged text simply vanishes, and the diff shows a change the user never sees
    the other half of. Nothing about that is visible after the fact, so it is
    refused here rather than resolved by ordering.
    """
    claimed: dict[tuple[str, int, int], str] = {}
    for kind, op in plan.labelled():
        if kind not in ("rewrite", "merge", "drop"):
            continue
        indices = [op.item_index] if kind == "rewrite" else list(op.item_indices)
        for i in indices:
            slot = (op.section_key, getattr(op, "entry_index", NA), i)
            if slot in claimed:
                out.append(
                    f"{kind}: bullet {i} of {op.section_key!r} is already claimed by a "
                    f"{claimed[slot]} — one change per bullet, or the other one is lost"
                )
            else:
                claimed[slot] = kind


def _texts_of(kind: str, op) -> list[tuple[str, str]]:
    """Every piece of free text an op would put on the CV."""
    if kind == "add_entry":
        out = [("title", op.title), ("date", op.date), ("role", op.role)]
        out += [("tech_stack", op.tech_stack)]
        out += [(f"items[{i}]", t) for i, t in enumerate(op.items)]
        return out
    if kind == "drop":
        return []
    return [("text", op.text)]


def _entries_of(section):
    return getattr(section, "entries", None)


def _check_target(label: str, kind: str, op, section, out: list[str]) -> None:
    """The indices must address content that exists (same discipline as the tailor guard)."""
    entries = _entries_of(section)

    if kind == "add_entry":
        if entries is None:
            out.append(f"{label}: {op.section_key!r} has no entries to add to")
        elif isinstance(section, EducationSection):
            out.append(f"{label}: education entries are edited by hand, not by instruction")
        return

    if isinstance(section, ParagraphSection):
        if kind != "rewrite":
            out.append(f"{label}: a paragraph section supports 'rewrite' only")
        return

    # Resolve which list of items this op addresses.
    if entries is not None:
        if not 0 <= op.entry_index < len(entries):
            out.append(
                f"{label}: entry_index {op.entry_index} out of range "
                f"(0..{len(entries) - 1}) for section {op.section_key!r}"
            )
            return
        items = entries[op.entry_index].items
    else:
        if op.entry_index != NA:
            out.append(f"{label}: section {op.section_key!r} has no entries; entry_index must be -1")
            return
        items = getattr(section, "items", [])

    size = len(items)
    if kind == "rewrite" and not 0 <= op.item_index < size:
        out.append(f"{label}: item_index {op.item_index} out of range (0..{size - 1})")
    if kind in ("merge", "drop"):
        idx = op.item_indices
        if len(idx) < (2 if kind == "merge" else 1):
            out.append(f"{label}: needs at least {2 if kind == 'merge' else 1} item_indices")
        if len(set(idx)) != len(idx):
            out.append(f"{label}: duplicate item_indices {idx}")
        bad = [i for i in idx if not 0 <= i < size]
        if bad:
            out.append(f"{label}: item_indices {bad} out of range (0..{size - 1})")
