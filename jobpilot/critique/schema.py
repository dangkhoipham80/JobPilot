"""What the critique model returns — an opinion about the Master CV.

Advisory, like the intake fit report (``jobpilot/intake/CLAUDE.md``): nothing
here is ever written to the CV or read by the tailor, and that boundary is what
lets it go without a truthfulness guard. If this output ever starts flowing into
a CV, write the guard first.

Entries are addressed **by index** into the same outline the tailor sees
(``tailor/prompt.render_master``). The service checks every index and resolves it
to a title at the time of the critique, so a later edit that reorders the CV
cannot make a verdict point at the wrong project.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SectionVerdictKind = Literal["ok", "improve", "trim"]
EntryVerdictKind = Literal["keep", "improve", "trim", "cut"]
RoleFitKind = Literal["strong", "possible", "stretch"]
SkillAdviceKind = Literal["learn", "optional", "skip"]


class _Model(BaseModel):
    # Structured outputs require additionalProperties:false on every object.
    model_config = ConfigDict(extra="forbid")


class RoleFit(_Model):
    role: str = Field(description="A role title as job ads write it, e.g. 'Backend Engineer'.")
    verdict: RoleFitKind = Field(
        description="strong = the CV already reads as this role; possible = credible "
        "with the changes suggested; stretch = the CV does not support it yet."
    )
    reason: str = Field(description="One or two sentences, citing the CV and the snapshot.")


class SectionVerdict(_Model):
    key: str = Field(description="Section key from the outline.")
    verdict: SectionVerdictKind = Field(
        description="ok = leave it; improve = worth rewriting; trim = shorten or cut."
    )
    reason: str = Field(description="Why, in one or two sentences.")
    suggestions: list[str] = Field(
        default_factory=list,
        description="Concrete edits the user could make. Never 'add skill X' for a "
        "skill the CV does not show.",
    )


class EntryVerdict(_Model):
    section_key: str = Field(description="Key of an experience or projects section.")
    entry_index: int = Field(description="entry[i] index from the outline.")
    verdict: EntryVerdictKind = Field(
        description="keep = strong as written; improve = worth rewriting; trim = "
        "shorten; cut = drop from the Master or keep only for niche roles."
    )
    reason: str = Field(description="Why, in one sentence.")
    suggestion: str = Field(default="", description="One concrete edit, or empty.")


class SkillAdvice(_Model):
    skill: str = Field(description="A skill from the snapshot that is NOT on the CV.")
    advice: SkillAdviceKind = Field(
        description="learn = worth gaining for the target role; optional = nice to "
        "have; skip = not worth it for this target."
    )
    reason: str = Field(description="One sentence.")


class CvCritique(_Model):
    headline: str = Field(
        description="The role and seniority the CV reads as today, in a few words, "
        "e.g. 'Junior backend engineer (Java)'."
    )
    summary: str = Field(description="Two or three sentences: the overall read.")
    strengths: list[str] = Field(default_factory=list, description="What already works.")
    role_fits: list[RoleFit] = Field(default_factory=list)
    sections: list[SectionVerdict] = Field(default_factory=list)
    entries: list[EntryVerdict] = Field(default_factory=list)
    skills: list[SkillAdvice] = Field(default_factory=list)
    priorities: list[str] = Field(
        default_factory=list, description="The three to five changes worth making first."
    )
