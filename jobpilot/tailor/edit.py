"""Editing the **Master CV** by instruction (SKILL.md §0, with a different owner).

Tailoring and editing look alike and are governed by opposite rules, so the
difference is worth stating once:

* **Tailoring** answers "how should my real CV be presented for this job?" The
  Master CV is the entire universe of truth, and ``TailorPlan`` is index-based so
  that inventing content is not a rule the model is asked to follow but a shape
  it cannot express.
* **Editing** answers "what is true about me now?" New facts are the *point* — a
  project finished last week is not on the CV yet, and refusing it for not being
  there already would make the feature useless. But the *user* is entitled to
  introduce them; the model is not.

So the guardrail here is **provenance, not vocabulary**: every word and every
number in new text must trace either to the Master CV (for ops that only rework
existing content) or to a ``source_quote`` that genuinely appears in the user's
instruction (for ops that add). See ``tailor/edit_guard.py``.

### Why one list per operation, and why nothing is optional

Two schema shapes were tried against the real API before this one:

1. A single flat ``EditOp`` with an ``op`` discriminator and every field any op
   might need. Anthropic rejected it outright — ``400 Schema is too complex``.
2. The same five ops split into five lists, but with Python defaults on most
   fields. **Also rejected**, at 3291 bytes, while ``TailorPlan`` passes at 4682.

Size was never the problem: an *optional* field becomes an ``anyOf``/nullable
branch, and enough of those blow the provider's complexity budget however small
the schema reads. Making every field required brought the identical structure to
3260 bytes and it passed. Hence: no defaults here, ever. A field that does not
apply to an op is not omitted, it is not *on* that op — which is the stronger
design anyway, since a ``drop`` can no longer carry a title.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from jobpilot.cv.schema import (
    BulletItem,
    BulletsSection,
    CvDocument,
    EducationSection,
    Entry,
    ExperienceSection,
    ParagraphSection,
    ProjectsSection,
)
from jobpilot.llm.base import Completion, LlmError, StructuredClient
from jobpilot.llm.usage import call_log
from jobpilot.tailor.guard import GuardrailViolation

EDIT_PLAN_VERSION = 1

#: Sentinel for "this op does not address an entry / an item". A plain ``-1``
#: rather than ``None`` because a nullable int is exactly the optional-field
#: shape the provider charges for (see the module docstring).
NA = -1


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Rewrite(_Model):
    """Replace the text of one bullet, or of a paragraph section."""

    section_key: str = Field(description="Section key from the master outline.")
    entry_index: int = Field(description="Entry holding the bullet, or -1 for the section itself.")
    item_index: int = Field(description="Bullet to replace, or -1 for a paragraph's own text.")
    text: str = Field(description="The new text, in CV inline markup. Never raw LaTeX.")
    source_quote: str = Field(
        description="Empty unless the user supplied a new fact or number here; then "
        "quote their words for it, exactly."
    )
    reason: str = Field(description="One short sentence for the review diff.")


class Merge(_Model):
    """Combine several bullets into one. The first index keeps the merged text."""

    section_key: str = Field(description="Section key from the master outline.")
    entry_index: int = Field(description="Entry holding the bullets, or -1 for the section itself.")
    item_indices: list[int] = Field(description="Bullets to combine, at least two.")
    text: str = Field(description="The combined text, drawn from what those bullets already say.")
    source_quote: str = Field(description="Empty unless the user supplied something new.")
    reason: str = Field(description="One short sentence for the review diff.")


class Drop(_Model):
    """Remove bullets."""

    section_key: str = Field(description="Section key from the master outline.")
    entry_index: int = Field(description="Entry holding the bullets, or -1 for the section itself.")
    item_indices: list[int] = Field(description="Bullets to remove.")
    reason: str = Field(description="One short sentence for the review diff.")


class NewBullet(_Model):
    """Append a bullet. Adds a fact, so the quote is mandatory."""

    section_key: str = Field(description="Section key from the master outline.")
    entry_index: int = Field(description="Entry to append to, or -1 for a bullets section.")
    text: str = Field(description="The new bullet, in CV inline markup.")
    source_quote: str = Field(
        description="REQUIRED. The words of the instruction stating this fact, copied "
        "exactly. Checked mechanically; a paraphrase is rejected."
    )
    reason: str = Field(description="One short sentence for the review diff.")


class NewEntry(_Model):
    """Append a job or project. Adds facts, so the quote is mandatory."""

    section_key: str = Field(description="Experience or projects section key.")
    title: str = Field(description="Entry title.")
    date: str = Field(description="Date range, or empty if the user did not give one.")
    role: str = Field(description="The user's role, or empty if not stated.")
    tech_stack: str = Field(
        description="Technologies, comma separated (e.g. 'FastAPI, React'). Empty if "
        "the user named none."
    )
    items: list[str] = Field(description="The entry's bullets. May be empty.")
    source_quote: str = Field(
        description="REQUIRED. The words of the instruction describing this, copied exactly."
    )
    reason: str = Field(description="One short sentence for the review diff.")


class MasterEditPlan(_Model):
    """The model's complete answer to one instruction.

    One list per kind rather than one list of tagged ops: it keeps every nested
    object small, and it makes a nonsensical combination unrepresentable instead
    of merely invalid.
    """

    rewrites: list[Rewrite] = Field(description="Bullets or paragraphs to reword.")
    merges: list[Merge] = Field(description="Bullets to combine.")
    drops: list[Drop] = Field(description="Bullets to remove.")
    new_bullets: list[NewBullet] = Field(description="Bullets to append. Each needs a quote.")
    new_entries: list[NewEntry] = Field(description="Entries to append. Each needs a quote.")
    note: str = Field(
        description="What you did NOT do and why — above all, any part of the "
        "instruction too vague to act on without inventing detail. Never guess here."
    )

    def labelled(self) -> list[tuple[str, _Model]]:
        """Every op with its kind, in a stable order — one loop for guard and apply."""
        return (
            [("rewrite", o) for o in self.rewrites]
            + [("merge", o) for o in self.merges]
            + [("drop", o) for o in self.drops]
            + [("add_bullet", o) for o in self.new_bullets]
            + [("add_entry", o) for o in self.new_entries]
        )

    def count(self) -> int:
        return len(self.labelled())


def empty_plan() -> MasterEditPlan:
    """A plan that changes nothing — every field is required, so spell it out."""
    return MasterEditPlan(
        rewrites=[], merges=[], drops=[], new_bullets=[], new_entries=[], note=""
    )


# --------------------------------------------------------------------------- #
# Applying a plan
# --------------------------------------------------------------------------- #
class EditApplyError(RuntimeError):
    """A plan that passed the guard still could not be applied."""


class EditError(RuntimeError):
    """The engine could not produce a usable edit plan."""


def _target_key(op) -> tuple[str, int]:
    return (op.section_key, getattr(op, "entry_index", NA))


def _rebuild(originals: list, plan: MasterEditPlan, key: tuple[str, int], set_text, make_new):
    """Apply every op addressing ``key`` to one list of items.

    Indices all refer to the master *as printed in the prompt*, so they are
    resolved against the original positions before anything shifts: dropping
    items 0 and 1 must not silently turn a rewrite of item 2 into a rewrite of
    the wrong line.
    """
    dropped: set[int] = set()
    replaced: dict[int, str] = {}
    added: list = []

    for op in plan.drops:
        if _target_key(op) == key:
            dropped.update(op.item_indices)
    for op in plan.merges:
        if _target_key(op) == key and op.item_indices:
            head, *rest = op.item_indices
            replaced[head] = op.text
            dropped.update(rest)
    for op in plan.rewrites:
        if _target_key(op) == key:
            replaced[op.item_index] = op.text
    for op in plan.new_bullets:
        if _target_key(op) == key:
            added.append(make_new(op.text))

    kept = [
        set_text(item, replaced[i]) if i in replaced else item
        for i, item in enumerate(originals)
        if i not in dropped
    ]
    return kept + added


def apply_edits(master: CvDocument, plan: MasterEditPlan) -> CvDocument:
    """Return a new document with ``plan`` applied. ``master`` is never mutated."""
    doc = master.model_copy(deep=True)
    by_key = {s.key: s for s in doc.sections}

    for key in {op.section_key for _, op in plan.labelled()}:
        if key not in by_key:
            raise EditApplyError(f"unknown section {key!r}")

    for op in plan.new_entries:
        section = by_key[op.section_key]
        if not isinstance(section, (ExperienceSection, ProjectsSection)):
            raise EditApplyError(f"cannot add an entry to section {op.section_key!r}")
        section.entries.append(
            Entry(
                title=op.title,
                date=op.date,
                items=list(op.items),
                role=op.role or None,
                tech_stack=[t.strip() for t in op.tech_stack.split(",") if t.strip()],
            )
        )

    for key, section in by_key.items():
        if isinstance(section, ParagraphSection):
            for op in plan.rewrites:
                if op.section_key == key:
                    section.text = op.text
        elif isinstance(section, BulletsSection):
            section.items = _rebuild(
                section.items,
                plan,
                (key, NA),
                set_text=lambda it, t: it.model_copy(update={"text": t}),
                make_new=lambda t: BulletItem(text=t),
            )
        elif isinstance(section, (ExperienceSection, ProjectsSection, EducationSection)):
            for idx, entry in enumerate(section.entries):
                # Both Entry.items and EducationEntry.items are list[str].
                entry.items = _rebuild(
                    entry.items,
                    plan,
                    (key, idx),
                    set_text=lambda _old, t: t,
                    make_new=lambda t: t,
                )
    return doc


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
@dataclass
class EditResult:
    plan: MasterEditPlan
    attempts: int = 1
    retried_for: list[str] = dataclass_field(default_factory=list)


class MasterEditEngine(Protocol):
    """Produces a validated edit plan for one instruction."""

    def edit(self, master: CvDocument, instruction: str) -> EditResult: ...


@dataclass
class ModelEditEngine:
    """Ask a model for an edit plan; accept it only if the provenance guard does.

    Deliberately the same shape as ``ModelTailorEngine``: one corrective round
    with the exact violations, then refuse. The retry is what keeps an
    unsupported claim out of the Master CV — and because the Master CV is the
    corpus every later tailor is checked against, a lie accepted here would be
    laundered into "already on the CV" for every job that follows.
    """

    client: StructuredClient

    def _ask(self, system: str, messages: list[dict]) -> Completion[MasterEditPlan]:
        try:
            return self.client.structured(system=system, messages=messages, schema=MasterEditPlan)
        except LlmError as exc:
            raise EditError(str(exc)) from exc

    def edit(self, master: CvDocument, instruction: str) -> EditResult:
        from jobpilot.tailor import prompt as prompts
        from jobpilot.tailor.edit_guard import check_edit_plan

        system = prompts.edit_system_prompt(master)
        messages: list[dict] = [{"role": "user", "content": prompts.edit_user_prompt(instruction)}]

        with call_log("cv_edit") as usage:
            plan = usage.add_from(self._ask(system, messages))
            report = check_edit_plan(plan, master, instruction)
            if report.ok:
                usage.succeeded()
                return EditResult(plan=plan)

            messages += [
                {"role": "assistant", "content": plan.model_dump_json()},
                {
                    "role": "user",
                    "content": prompts.retry_prompt(report.violations, remedies=prompts.EDIT_REMEDIES),
                },
            ]
            retried = usage.add_from(self._ask(system, messages))
            second = check_edit_plan(retried, master, instruction)
            if not second.ok:
                raise GuardrailViolation(
                    "edit plan still violates the CV guardrails after one retry: "
                    + "; ".join(second.violations)
                )
            usage.succeeded()
            return EditResult(plan=retried, attempts=2, retried_for=report.violations)


@dataclass
class FixtureEditEngine:
    """Returns a canned plan — used by tests and the CLI's dry run."""

    plan: MasterEditPlan
    calls: list[str] = dataclass_field(default_factory=list)

    def edit(self, master: CvDocument, instruction: str) -> EditResult:
        from jobpilot.tailor.edit_guard import check_edit_plan

        self.calls.append(instruction)
        check_edit_plan(self.plan, master, instruction).raise_if_bad()
        return EditResult(plan=self.plan)


def default_edit_engine() -> MasterEditEngine:
    """The engine ``llm.tailor`` (or ``llm.provider``) asks for."""
    from jobpilot.llm.registry import client_for

    return ModelEditEngine(client_for("tailor"))
