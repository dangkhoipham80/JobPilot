"""The critique engine — one structured call, no retry.

No corrective round, for the reason the intake fit has none: there is no
mechanical rule that tells a good opinion from a bad one, so there is nothing to
check and nothing to send back. The structural part (indices that point at real
entries) is cleaned up by the service instead of being argued with the model.

Runs on the `intake` backend: it is the same kind of call (read a document,
return an opinion) and does not deserve its own model setting. It is logged as
`critique` so `llm stats` shows what it costs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from jobpilot.critique import prompt as prompts
from jobpilot.critique.schema import CvCritique
from jobpilot.cv.schema import CvDocument
from jobpilot.llm.base import Completion, LlmError, StructuredClient
from jobpilot.llm.usage import call_log
from jobpilot.timeutil import vn_now


class CritiqueError(RuntimeError):
    """The engine could not produce a critique."""


class CritiqueEngine(Protocol):
    def critique(self, master: CvDocument, market: str, role: str, lang: str) -> CvCritique: ...


@dataclass
class ModelCritiqueEngine:
    client: StructuredClient

    def critique(self, master: CvDocument, market: str, role: str, lang: str) -> CvCritique:
        with call_log("critique") as usage:
            try:
                completion: Completion[CvCritique] = self.client.structured(
                    system=prompts.system_prompt(master, lang),
                    messages=[
                        {
                            "role": "user",
                            "content": prompts.user_prompt(market, role, vn_now().date()),
                        }
                    ],
                    schema=CvCritique,
                )
            except LlmError as exc:
                raise CritiqueError(str(exc)) from exc
            result = usage.add_from(completion)
            usage.succeeded()
            return result


@dataclass
class FixtureCritiqueEngine:
    """Canned answer — used by tests and by anything that must not hit an API."""

    report: CvCritique | None = None
    calls: list[tuple[str, str]] = field(default_factory=list)

    def critique(self, master: CvDocument, market: str, role: str, lang: str) -> CvCritique:
        self.calls.append((role, lang))
        if self.report is None:
            raise CritiqueError("fixture engine has no critique configured")
        return self.report


def default_engine() -> CritiqueEngine:
    from jobpilot.llm.registry import client_for

    return ModelCritiqueEngine(client_for("intake"))
