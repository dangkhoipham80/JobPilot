"""What the intake model is allowed to return.

Two schemas, both flat. ``llm/CLAUDE.md`` records the measurement behind that:
a schema is rejected by provider strict mode because of *optional* fields
multiplying into ``anyOf`` branches, not because of its size — so every field
here is required, and "the posting doesn't say" is expressed as ``""`` rather
than by leaving a field out. The prompts say so in as many words.

:class:`FitReport` reuses :class:`~jobpilot.tailor.schema.Requirement` on
purpose. The fit check and the tailor plan answer the same question at
different prices, and two vocabularies for "does the CV cover this" would
eventually disagree about the same job — the reader would have no way to tell
which one was wrong.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from jobpilot.crawler.normalize import LEVELS, WORK_MODES
from jobpilot.tailor.schema import Requirement

#: Spelled into the prompt so the model is asked for the vocabulary the column
#: actually uses, rather than being corrected afterwards. Sorted for a stable
#: prompt — an unordered frozenset would reword the system prompt between runs
#: and defeat prompt caching for no reason.
LEVEL_WORDS: str = ", ".join(sorted(LEVELS))

#: How the fit check summarises itself in one word. Three buckets, not five:
#: this is a decision aid for "is it worth a tailor round", and a scale fine
#: enough to agonise over is a scale that stops being read.
Verdict = Literal["strong", "fair", "weak"]


class _Model(BaseModel):
    # Structured outputs require additionalProperties:false on every object.
    model_config = ConfigDict(extra="forbid")


class JdExtract(_Model):
    """The fields a job posting states, lifted out of pasted text.

    Note what is *not* here: the description. The JD stored on the job is the
    user's own paste, never a model's retelling of it — see the module docstring
    of :mod:`jobpilot.intake`.
    """

    title: str = Field(description="The role title, as the posting words it. '' if absent.")
    company: str = Field(description="The hiring company. '' if the posting never names one.")
    location: str = Field(
        description="Where the job is, as stated (city, or 'Remote'). '' if absent."
    )
    salary: str = Field(
        description="The pay, copied as the posting words it ('20 - 30 triệu', "
        "'up to $3000', 'Thoả thuận'). '' if the posting does not say. Never a "
        "figure you worked out yourself."
    )
    level: str = Field(
        description=f"Seniority, one of: {LEVEL_WORDS}. '' when the posting does "
        "not say — do not infer it from the years of experience asked for."
    )
    employment_type: str = Field(
        description="full-time, part-time, contract, internship, or '' if unstated."
    )
    work_mode: str = Field(
        description=f"How the work happens, one of: {', '.join(WORK_MODES)}. '' when "
        "the posting does not say — an office address is not a statement that the "
        "job is onsite."
    )
    skills: list[str] = Field(
        description="Technologies and tools the posting names, as short tags "
        "('Java', 'Spring Boot', 'PostgreSQL'). Empty list if it names none."
    )
    apply_email: str = Field(
        description="The address the posting says to send a CV to, if it gives one. "
        "'' otherwise — never the recruiter's personal address inferred from a name."
    )
    language: str = Field(description="'vi' or 'en' — the language the posting is written in.")

    @field_validator("work_mode")
    @classmethod
    def _known_work_mode(cls, value: str) -> str:
        """Same rule as ``level``: a word off the list is no answer at all."""
        # "On-site", "on site" and "ONSITE" all mean the same thing and models
        # write all three, so hyphens and spaces go before the lookup.
        cleaned = value.strip().lower().replace("-", "").replace(" ", "")
        return cleaned if cleaned in WORK_MODES else ""

    @field_validator("level")
    @classmethod
    def _known_level(cls, value: str) -> str:
        """Anything off the list becomes ''.

        The field feeds ``Job.level``, which the Jobs page filters on and the
        Market page facets by. A model answering "mid-senior" would quietly
        create a bucket of one that no filter ever selects — and an empty level
        is already a state the UI knows how to show.
        """
        cleaned = value.strip().lower()
        return cleaned if cleaned in LEVELS else ""


class JdSections(_Model):
    """The body of a posting, split into the parts a person reads separately.

    Every list holds the posting's **own lines**, tidied but not rewritten — the
    same rule as ``description_md``. This is a *table of contents* over text the
    user can still read in full underneath; it is not a summary, and nothing
    here is allowed to say something the posting did not.

    Kept apart from :class:`JdExtract` rather than folded into it. They are
    different readings: that one copies six short facts, this one organises
    prose, and one prompt doing both does neither well. Splitting also keeps
    both schemas small, which ``llm/CLAUDE.md`` records as the thing that
    decides whether a provider accepts them at all.
    """

    role: str = Field(
        description="What the role is, in one or two sentences drawn from the "
        "posting's own overview. '' if it only lists tasks."
    )
    responsibilities: list[str] = Field(
        description="What the person will do day to day, one entry per item the "
        "posting lists. Empty list if it never says."
    )
    must_have: list[str] = Field(
        description="Technical and professional requirements stated as required "
        "— years, technologies, domains, qualifications. Not personality traits."
    )
    nice_to_have: list[str] = Field(
        description="Stated as a plus, an advantage, preferred, 'ưu tiên'. "
        "Anything the posting marks as optional belongs here, not in must_have."
    )
    soft_skills: list[str] = Field(
        description="Character and working-style asks — communication, ownership, "
        "teamwork, English level as a working language. Kept separate because a "
        "CV cannot evidence most of them."
    )
    outputs: list[str] = Field(
        description="Deliverables, targets or KPIs the posting names as what "
        "success looks like. Usually []; many postings never say."
    )
    benefits: list[str] = Field(
        description="Pay-adjacent and non-pay benefits: 13th month, bonus, "
        "insurance, leave days, equipment, training budget."
    )
    how_to_apply: str = Field(
        description="What the posting says to do to apply — an address, a form, "
        "a deadline, a subject line to use. '' if it gives no instructions."
    )


class FitReport(_Model):
    """Whether this posting is worth a tailor round, and what is missing.

    Advisory in the strict sense: nothing here is ever written to a CV, quoted
    in a cover letter, or passed into the tailor prompt. That boundary is what
    lets the report be a plain opinion — the guardrails that stop a fabricated
    skill reaching a PDF sit downstream of it, untouched, and a wrong fit report
    costs the user a wasted read rather than a false claim to an employer.
    """

    match_score: float = Field(
        description="Weighted share of requirements satisfied, between 0 and 1: "
        "(HAVE + 0.5*PARTIAL) / total, with must_have weighted double."
    )
    # Still asked for, and then recomputed — see `_score_from_requirements`. The
    # model is kept on the hook for it because a model that has to produce a
    # number reads its own list more carefully than one that does not.
    #
    # This is deliberately NOT described anywhere as comparable to
    # `TailorPlan.match_score`. That one keeps whatever number its model
    # returned (clamped only), while this one is derived; the 0.50/0.32/0.31
    # spread below is the evidence that models do not in fact apply the stated
    # formula. Two numbers produced by different rules, shown on the same
    # screen, should not invite comparison.
    verdict: Verdict = Field(
        description="strong = apply, the CV already answers the must-haves; "
        "fair = worth applying but there are real gaps; "
        "weak = the CV cannot answer what this role is asking for."
    )
    summary: str = Field(
        description="One or two plain sentences saying why, addressed to the "
        "candidate. No markup."
    )
    requirements: list[Requirement] = Field(
        description="Every requirement the posting states, classified against the "
        "Master CV. Empty list only if the posting states none."
    )
    dealbreakers: list[str] = Field(
        description="Hard conditions the candidate cannot meet at all and cannot "
        "close by rewording a CV — a degree they do not hold, a work language they "
        "do not speak, a years-of-experience floor they are under, an on-site "
        "location they are not in. Empty list when there are none."
    )
    concerns: list[str] = Field(
        description="Things wrong with the *posting*, not the candidate: no named "
        "employer, a JD too vague to tell what the job is, an agency listing "
        "standing in for an undisclosed client, pay-to-apply or training-fee "
        "language. Empty list when the posting looks ordinary."
    )

    @field_validator("match_score")
    @classmethod
    def _clamp_score(cls, value: float) -> float:
        # Clamped rather than rejected, exactly as `TailorPlan.match_score` is:
        # structured outputs carry no minimum/maximum, and a score of 1.04 is a
        # display glitch, not something worth a second API call.
        return min(1.0, max(0.0, value))

    @model_validator(mode="after")
    def _recompute_score(self) -> "FitReport":
        """Derive the score from the list, rather than trusting the model's own.

        Measured on one real posting across three backends: the same prompt and
        the same job produced 0.50, 0.32 and 0.31, and the spread came almost
        entirely from *how many requirements got filed as must_have*, not from
        any disagreement about what the CV contains. A number that swings by 20
        points while the list underneath it barely moves is not a measurement.

        Computing it here fixes two things at once. The score now always agrees
        with the requirements shown beside it — the rule ``crawler/quality.py``
        already follows, where an explanation that contradicts the number it
        explains is worse than no explanation. And it makes ``soft`` cost
        nothing, which matters because models classify it unreliably: the same
        model filed four traits as ``soft`` on one run and zero on the next.
        With a weight of 0, that inconsistency stops moving the headline number.

        Falls back to the model's own answer only when there is no list to work
        from, which is the one case where there is nothing better to use.

        ``verdict`` follows the score for the same reason: it is rendered right
        next to it, and "Strong match · 31%" is a card that teaches the reader
        to trust neither half. A dealbreaker overrides both — no percentage is
        encouraging when the posting requires a degree the candidate does not
        hold.
        """
        if self.requirements:
            self.match_score = _score_from_requirements(self.requirements)
        self.verdict = _verdict_for(self.match_score, self.dealbreakers)
        return self

    def gaps(self) -> list[Requirement]:
        """Requirements the CV cannot back up — the same accessor ``TailorPlan`` has."""
        return [r for r in self.requirements if r.status == "MISSING"]


#: What each kind of requirement is worth in the score. ``soft`` is 0 on
#: purpose: a CV cannot evidence "high growth drive" or "product thinking", so
#: counting those against it measures the posting's prose style rather than the
#: candidate. They stay in the list — a posting that is mostly personality
#: traits is worth seeing — they just do not move the number.
_WEIGHTS: dict[str, float] = {"must_have": 2.0, "nice_to_have": 1.0, "soft": 0.0}

#: How much credit each status earns of its weight.
_CREDIT: dict[str, float] = {"HAVE": 1.0, "PARTIAL": 0.5, "MISSING": 0.0}


#: Score at or above which each verdict applies. Three buckets over a continuous
#: number, so the boundaries are arbitrary by construction — they are set where
#: the advice changes rather than at round numbers: below 0.4 the CV is missing
#: most of what the posting asks for, above 0.7 it answers the must-haves.
STRONG_AT = 0.7
FAIR_AT = 0.4


def _verdict_for(score: float, dealbreakers: list[str]) -> Verdict:
    if dealbreakers:
        return "weak"
    return "strong" if score >= STRONG_AT else "fair" if score >= FAIR_AT else "weak"


def _score_from_requirements(requirements: list[Requirement]) -> float:
    total = sum(_WEIGHTS.get(r.kind, 1.0) for r in requirements)
    if not total:
        # Every requirement was soft. Not 0.0 — that would read as "your CV
        # covers none of this", when what happened is that the posting asked for
        # nothing a CV can answer. The honest headline is the middle.
        return 0.5
    earned = sum(_WEIGHTS.get(r.kind, 1.0) * _CREDIT.get(r.status, 0.0) for r in requirements)
    return min(1.0, max(0.0, earned / total))
