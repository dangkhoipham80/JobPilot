"""Cover letter generation (SKILL.md §2 step 4).

Same truthfulness problem as the CV, with one extra wrinkle: SKILL.md explicitly
*allows* the letter to acknowledge a missing skill as something the candidate is
willing to learn. A single free-text blob would make "I am experienced with
Kafka" and "I have not used Kafka yet but I am keen to" indistinguishable to any
checker, so the schema separates them:

* ``paragraphs`` — claims about the candidate. Checked strictly against the
  Master CV's vocabulary; a technology that isn't already on the CV is rejected.
* ``learning_note`` — the one place a MISSING requirement may be named, and only
  the requirements the tailor already classified as MISSING for this job.

That split is what makes the honest sentence expressible and the dishonest one
not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from jobpilot.cv.schema import CvDocument
from jobpilot.llm.base import Completion, LlmError, StructuredClient
from jobpilot.llm.usage import call_log
from jobpilot.store.models import Job
from jobpilot.tailor.engine import TailorError
from jobpilot.tailor.guard import (
    GuardrailViolation,
    PlanReport,
    master_text,
    numbers_in,
    terms_in,
    unknown_numbers,
    unknown_terms,
    vocabulary,
)
from jobpilot.tailor.schema import TailorPlan

MAX_WORDS = 300  # SKILL.md §2 step 4


class _LetterBody(BaseModel):
    """The parts of a letter every job has, gaps or not.

    Shared rather than copied into both models: with two hand-written copies, a
    field added to one and forgotten in the other would be dropped in silence by
    ``to_letter()`` if it had a default, or raise a confusing TypeError at apply
    time if it did not. Inheriting means a new field lands in both by default.
    """

    model_config = ConfigDict(extra="forbid")

    greeting: str = Field(description='e.g. "Dear Hiring Team at ACME Corp,"')
    paragraphs: list[str] = Field(
        default_factory=list,
        description="Two or three short paragraphs. Every claim must be backed by "
        "the Master CV — name only technologies that already appear on it.",
    )
    closing: str = Field(default="Best regards,", description='e.g. "Best regards,"')


class CoverLetter(_LetterBody):
    learning_note: str = Field(
        default="",
        description="Optional single sentence acknowledging a requirement the "
        "candidate does not yet have, framed as willingness to learn. This is the "
        "only field allowed to name a MISSING requirement, and it must never claim "
        "the skill. Leave empty when there is no important gap.",
    )

    @classmethod
    def schema_for(cls, has_gaps: bool) -> type[BaseModel]:
        """The schema to ask the model for, given whether this job has gaps.

        With no MISSING requirement, *anything* in ``learning_note`` is a
        violation by construction — the field may only name a gap, and there is
        none. Telling the model that in the prompt was not enough: it kept
        writing one anyway, and three applies in a row died on a note naming
        Apache, then NoSQL, after the retry as well.

        So the field is removed from the schema instead of argued about. This is
        the same move as the index-based tailor plan: make the wrong answer
        unrepresentable rather than detectable, because a rule the model can
        physically not break needs no enforcement.
        """
        if has_gaps:
            return cls
        return _GaplessCoverLetter

    def body(self) -> str:
        """The letter as plain text — this is what an email actually carries."""
        parts = [self.greeting, "", *self._flow(), "", self.closing]
        return "\n".join(parts).strip()

    def _flow(self) -> list[str]:
        blocks = [p.strip() for p in self.paragraphs if p.strip()]
        if self.learning_note.strip():
            blocks.append(self.learning_note.strip())
        # Blank line between paragraphs.
        out: list[str] = []
        for i, block in enumerate(blocks):
            if i:
                out.append("")
            out.append(block)
        return out

    def word_count(self) -> int:
        return len(self.body().split())


class _GaplessCoverLetter(_LetterBody):
    """A letter for a job the CV already covers — with no ``learning_note`` field.

    A sibling of ``CoverLetter`` rather than ``CoverLetter`` with the field
    excluded: ``exclude`` only affects serialization, so the model would still
    be shown the field in the JSON schema and would still fill it in. It has to
    be genuinely absent from the schema to be unrepresentable.
    """

    def to_letter(self) -> CoverLetter:
        """Back to the one type the rest of the pipeline knows.

        Built from ``model_dump()`` rather than field by field, so a field added
        to ``_LetterBody`` later is carried across without anyone remembering to
        edit this line.
        """
        return CoverLetter(**self.model_dump(), learning_note="")


# --------------------------------------------------------------------------- #
# Guardrail
# --------------------------------------------------------------------------- #
def _tokens(*values: str | None) -> set[str]:
    """Proper nouns the letter must be able to name: the company, the location.

    Delegates to the guard's own tokenizer. Splitting on whitespace here looked
    equivalent and was not: it yielded ``r&d`` for "Panasonic R&D Center Vietnam"
    while the checker looks for ``r`` and ``d`` (``_TOKEN_RE`` has no ``&``). The
    company name was therefore in the vocabulary under a spelling that could
    never match, and every letter to a company with an ampersand in its name was
    rejected for "claiming experience with R, D" — both real language names —
    for doing nothing but addressing the employer.
    """
    return terms_in(*values)


def check_letter(
    letter: CoverLetter, master: CvDocument, job: Job, plan: TailorPlan | None = None
) -> PlanReport:
    """Claims are checked against the CV; only the learning note may name a gap."""
    violations: list[str] = []

    # The employer's name and city are facts about the job, not claims about the
    # candidate, so the letter is allowed to say them.
    claim_vocab = vocabulary(master) | _tokens(job.company, job.location)
    # Numbers get the same treatment as names, and need their own check: the
    # term check only sees tokens that start with a letter, so "cut latency by
    # 40%" passed it untouched. A figure is allowed if the CV states it, or if
    # it is part of the employer's name ("Studio 6677").
    #
    # Deliberately NOT the job's title or location. A title like "Java Developer
    # (5+ years)" would license "with 5+ years of experience", and an address
    # like "12 Ton Dan" would license "a team of 12" — the same hole, reopened
    # on the one path where nobody reads the text before it is sent. The cost is
    # that repeating "Java 17 Developer" from a title takes a retry.
    claim_numbers = numbers_in(master_text(master), job.company)

    for i, para in enumerate(letter.paragraphs):
        invented = unknown_terms(para, claim_vocab)
        if invented:
            violations.append(
                f"paragraph {i + 1} claims experience with {', '.join(invented)}, which the "
                "Master CV does not support — move it to learning_note or drop it"
            )
        figures = unknown_numbers(para, claim_numbers)
        if figures:
            violations.append(
                f"paragraph {i + 1} states the number(s) {', '.join(figures)}, which the "
                "Master CV never states — drop them or use a figure the CV gives"
            )

    if letter.learning_note.strip():
        gaps = {g.text for g in plan.gaps()} if plan else set()
        note_vocab = claim_vocab | _tokens(*gaps)
        invented = unknown_terms(letter.learning_note, note_vocab)
        if invented:
            violations.append(
                f"learning_note names {', '.join(invented)}, which is neither on the CV nor "
                "a MISSING requirement of this job"
            )
        figures = unknown_numbers(letter.learning_note, claim_numbers | numbers_in(*gaps))
        if figures:
            violations.append(
                f"learning_note states the number(s) {', '.join(figures)}, which neither the "
                "CV nor a MISSING requirement of this job states"
            )

    if letter.word_count() > MAX_WORDS:
        violations.append(f"letter is {letter.word_count()} words; keep it under {MAX_WORDS}")
    if not letter.paragraphs:
        violations.append("letter has no body paragraphs")

    return PlanReport(violations=violations)


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #
_LEARNING_NOTE_RULE = """\
- If the job needs something the candidate does not have and it matters, put a
  single honest sentence in `learning_note` — willingness to learn, never a
  claim of experience. That field is the only place a missing skill may appear.
  Leave it empty if there is no important gap.
"""


def letter_rules(has_gaps: bool = True) -> str:
    """The system rules, minus any rule about a field that is not in the schema.

    Sending the ``learning_note`` rule alongside a schema with no such field is
    an instruction the model cannot follow. Harmless for correctness — the
    schema decides — but a contradiction between the rules and the shape is
    exactly the kind of thing that makes a model improvise somewhere else.
    """
    return f"""\
Write a cover letter for one job application, on behalf of the candidate whose
CV appears below.

# Rules
- Never claim a skill, technology, employer, metric, or achievement the CV does
  not already show. The body paragraphs are claims about the candidate and are
  checked against the CV word by word — and number by number: any figure you
  give must be one the CV states.
{_LEARNING_NOTE_RULE if has_gaps else ""}\
- Two or three short paragraphs: why this role, then two concrete strengths
  drawn from the CV with evidence, then a brief close.
- Under {MAX_WORDS} words in total. Plain prose — no markdown, no bullet points,
  no LaTeX. Professional, specific, and free of filler.
"""


#: The full rules, for callers that do not know about gaps (tests, fixtures).
LETTER_RULES = letter_rules()


def letter_prompt(job: Job, plan: TailorPlan | None) -> str:
    payload = job.payload or {}
    parts = [
        "JOB",
        f"title: {job.title}",
        f"company: {job.company}",
        f"location: {job.location or 'unspecified'}",
        "",
        "description:",
        (payload.get("description_md") or "").strip() or "(empty)",
    ]
    if plan is not None:
        strengths = [r for r in plan.requirements if r.status in ("HAVE", "PARTIAL")]
        if strengths:
            parts += ["", "REQUIREMENTS THE CV SUPPORTS (use these as your evidence):"]
            parts += [f"  - {r.text} — {r.evidence or 'see CV'}" for r in strengths]
            # The requirement text is the employer's wording. "3+ years of Java"
            # marked HAVE is an invitation to write "3+ years", which the CV may
            # never say — and that is a rejected letter.
            parts += [
                "",
                "Any number in the requirements above is the employer's wording, not a "
                "fact about the candidate. Do not repeat a figure — years, team sizes, "
                "percentages — unless the CV itself states it.",
            ]
        gaps = plan.gaps()
        if gaps:
            parts += ["", "REQUIREMENTS THE CANDIDATE DOES NOT HAVE:"]
            parts += [f"  - {g.text}" for g in gaps]
            parts += [
                "",
                "Only these may appear in learning_note, and only as something to learn.",
            ]
        else:
            # Said out loud, because saying nothing here loses. The general rule
            # ("leave it empty if there is no important gap") competes with the
            # model's instinct to sound humble, and the model kept winning: three
            # applies in a row failed on a learning_note naming Apache, then
            # NoSQL, for a plan whose requirements were all HAVE. There was
            # nothing it could legitimately name, so anything it wrote was a
            # violation — and the prompt never told it so.
            parts += [
                "",
                "The candidate meets every requirement listed above. There is no gap to "
                "acknowledge, so `learning_note` MUST be an empty string. Do not invent a "
                "weakness to sound modest.",
            ]
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# Engines
# --------------------------------------------------------------------------- #
@dataclass
class LetterResult:
    letter: CoverLetter
    attempts: int = 1


class LetterEngine(Protocol):
    def write(
        self, master: CvDocument, job: Job, plan: TailorPlan | None = None
    ) -> LetterResult: ...


@dataclass
class ModelLetterEngine:
    """One letter, one corrective round, whichever backend is configured.

    Same shape as ``ModelTailorEngine`` and for the same reason: the retry is
    what stops an unsupported claim reaching an employer, so it cannot be
    something each backend gets its own copy of. Until Phase 20b this file held
    two near-identical copies of the loop below — one per provider — which is
    the arrangement ``tailor/diff.py`` was refactored to avoid two phases
    earlier.

    The letter is the call where model quality shows most: it is free prose a
    person will judge you on rather than a permutation of numbered items. The
    vocabulary guardrail still holds — no backend can claim a technology the CV
    lacks — but "true" and "well written" are different bars and only the first
    is enforceable. Read it before sending; the approval gate is already there.
    """

    client: StructuredClient

    def _ask(self, system: str, messages: list[dict], schema) -> Completion:
        try:
            return self.client.structured(system=system, messages=messages, schema=schema)
        except LlmError as exc:
            raise TailorError(str(exc)) from exc

    def write(self, master: CvDocument, job: Job, plan: TailorPlan | None = None) -> LetterResult:
        from jobpilot.tailor.prompt import render_master

        # No gaps means learning_note has nothing it may legitimately name, so
        # the field is left out of the schema entirely rather than argued about
        # in the prompt — which was tried, and lost three times running. The
        # rules drop the matching instruction for the same reason.
        has_gaps = bool(plan and plan.gaps())
        system = f"{letter_rules(has_gaps)}\n\n{render_master(master)}"
        messages: list[dict] = [{"role": "user", "content": letter_prompt(job, plan)}]
        schema = CoverLetter.schema_for(has_gaps)

        def ask() -> CoverLetter:
            # The gapless schema returns its own type; normalise straight away so
            # the checker, the retry and the PDF all see one class.
            answer = usage.add_from(self._ask(system, messages, schema))
            return answer.to_letter() if isinstance(answer, _GaplessCoverLetter) else answer

        with call_log("letter", job_id=job.id) as usage:
            letter = ask()
            report = check_letter(letter, master, job, plan)
            if report.ok:
                usage.succeeded()
                return LetterResult(letter=letter)

            messages += [
                {"role": "assistant", "content": letter.model_dump_json()},
                {
                    "role": "user",
                    "content": "That letter was rejected:\n"
                    + "\n".join(f"  - {v}" for v in report.violations)
                    + "\n\nRewrite it within the rules.",
                },
            ]
            retried = ask()
            second = check_letter(retried, master, job, plan)
            if not second.ok:
                raise GuardrailViolation(
                    "cover letter still unsupported after one retry: "
                    + "; ".join(second.violations)
                )
            usage.succeeded()
            return LetterResult(letter=retried, attempts=2)


@dataclass
class FixtureLetterEngine:
    """Canned letter for tests and offline runs."""

    letter: CoverLetter
    calls: list[str] = field(default_factory=list)

    def write(self, master: CvDocument, job: Job, plan: TailorPlan | None = None) -> LetterResult:
        self.calls.append(job.id)
        check_letter(self.letter, master, job, plan).raise_if_bad()
        return LetterResult(letter=self.letter)


def default_letter_engine() -> LetterEngine:
    """The engine `llm.letter` (or `llm.provider`) asks for."""
    from jobpilot.llm.registry import client_for

    return ModelLetterEngine(client_for("letter"))
