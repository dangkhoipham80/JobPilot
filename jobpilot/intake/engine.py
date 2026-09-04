"""The intake engine — one model call per question, no retry loop.

Deliberately thinner than ``tailor/engine.py``. That engine's corrective round
exists because a bad plan reaches a PDF an employer will read, so a violation
has to be caught and fixed before it lands. Neither call here has that property:

* ``extract`` produces a pre-filled form. The user is looking straight at it and
  will fix a wrong company name in two seconds. Spending a second API call to
  correct something a human is already correcting would be paying for nothing.
* ``assess`` produces an opinion. There is no mechanical rule that separates a
  right opinion from a wrong one, so there is nothing to check and nothing to
  send back.

The empty-guardrail claim is only safe because of where the output goes: an
extract becomes editable form fields, a fit report becomes text on a page. If
either ever starts feeding the tailor prompt or the CV, this file needs a
guardrail before that happens, not after.

Both calls are still recorded through ``llm.usage.call_log`` — telemetry is not
about whether the answer needed checking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from jobpilot.cv.schema import CvDocument
from jobpilot.intake import prompt as prompts
from jobpilot.intake.schema import FitReport, JdExtract, JdSections
from jobpilot.llm.base import Completion, LlmError, StructuredClient
from jobpilot.llm.usage import call_log
from jobpilot.store.models import Job


class IntakeError(RuntimeError):
    """The engine could not read the posting, or could not assess it."""


class IntakeEngine(Protocol):
    """Reads a pasted posting, and scores a saved one against the Master CV."""

    def extract(self, text: str, url: str = "") -> JdExtract: ...

    def sections(self, text: str) -> JdSections: ...

    def assess(self, master: CvDocument, job: Job) -> FitReport: ...


@dataclass
class ModelIntakeEngine:
    """Both intake calls against one :class:`StructuredClient`."""

    client: StructuredClient

    def _ask(self, system: str, user: str, schema):
        try:
            return self.client.structured(
                system=system, messages=[{"role": "user", "content": user}], schema=schema
            )
        except LlmError as exc:
            raise IntakeError(str(exc)) from exc

    def extract(self, text: str, url: str = "") -> JdExtract:
        # No job_id: nothing has been saved yet, and this is the one LLM call in
        # the app that runs before a row exists. `usage.record` would drop the
        # link anyway (foreign key), so not claiming one keeps the cost row
        # honest rather than mysteriously unlinked.
        with call_log("intake") as usage:
            completion: Completion[JdExtract] = self._ask(
                prompts.extract_system_prompt(),
                prompts.extract_user_prompt(text, url),
                JdExtract,
            )
            result = usage.add_from(completion)
            usage.succeeded()
            return result

    def sections(self, text: str) -> JdSections:
        with call_log("intake") as usage:
            completion: Completion[JdSections] = self._ask(
                prompts.sections_system_prompt(), prompts.sections_user_prompt(text), JdSections
            )
            result = usage.add_from(completion)
            usage.succeeded()
            return result

    def assess(self, master: CvDocument, job: Job) -> FitReport:
        with call_log("intake", job_id=job.id) as usage:
            completion: Completion[FitReport] = self._ask(
                prompts.fit_system_prompt(master), prompts.fit_user_prompt(job), FitReport
            )
            result = usage.add_from(completion)
            usage.succeeded()
            return result


@dataclass
class FixtureIntakeEngine:
    """Canned answers — used by tests and by anything that must not hit an API."""

    extracted: JdExtract | None = None
    parsed: JdSections | None = None
    report: FitReport | None = None
    extract_calls: list[tuple[str, str]] = field(default_factory=list)
    section_calls: list[str] = field(default_factory=list)
    assess_calls: list[str] = field(default_factory=list)

    def extract(self, text: str, url: str = "") -> JdExtract:
        self.extract_calls.append((text, url))
        if self.extracted is None:
            raise IntakeError("fixture engine has no extract answer configured")
        return self.extracted

    def sections(self, text: str) -> JdSections:
        self.section_calls.append(text)
        if self.parsed is None:
            raise IntakeError("fixture engine has no sections answer configured")
        return self.parsed

    def assess(self, master: CvDocument, job: Job) -> FitReport:
        self.assess_calls.append(job.id)
        if self.report is None:
            raise IntakeError("fixture engine has no fit report configured")
        return self.report


def default_engine() -> IntakeEngine:
    """The engine `llm.intake` (or `llm.provider`) asks for."""
    from jobpilot.llm.registry import client_for

    return ModelIntakeEngine(client_for("intake"))
