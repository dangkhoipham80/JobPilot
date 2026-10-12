"""Truthfulness guardrails for a tailor plan (SKILL.md §0).

Three layers:

1. **Structural** — every index in the plan must point at real Master CV content,
   with no duplicates. Because the plan can only reorder and drop, a structurally
   valid plan cannot introduce a skill, a metric, or an employer.
2. **Lexical** — the summary is the one free-text field. Any technology-looking
   token in it must already appear somewhere in the Master CV. Ordinary prose is
   left alone, so rewording stays possible while "also experienced with Kafka"
   does not.
3. **Numeric** — every number in the summary must be a number the Master CV
   states. Layer 2 cannot see one: its tokens start with a letter, so "improved
   throughput by 40%" contains nothing it checks. The summary is prose the model
   writes, and an invented metric is the most damaging thing it could put there.

The number primitives (:func:`numbers_in`, :func:`master_text`,
:func:`unknown_numbers`) live here so that the tailor plan, the cover letter and
the Master-CV edit guard all count numbers the same way.

Violations are returned rather than raised so the engine can feed them back to
the model for one corrective retry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from jobpilot.cv.schema import (
    BulletsSection,
    CvDocument,
    EducationSection,
    ExperienceSection,
    ParagraphSection,
    ProjectsSection,
)
from jobpilot.tailor.schema import TailorPlan


class GuardrailViolation(ValueError):
    """A plan that would put unsupported claims on the CV."""


# Words that look like a technology to the heuristic below but are ordinary English.
# Kept deliberately small: a false positive costs one retry, a false negative
# would let a fabricated skill onto the CV.
#
# Months are here because they are capitalised mid-sentence, which is the
# heuristic's whole definition of "looks like a product". A CV writes its dates
# as "Dec. 2024"; a letter writes "since December 2024", and on real data that
# one word rejected a letter twice and failed the application. The year beside
# it is still held to the number check; the month itself is now checked by
# nothing, so "since March 2024" passes too (a limit listed in SKILL.md §0).
#
# Weekdays are deliberately NOT here: "Monday" is a product people put on CVs
# (monday.com), and a letter rarely needs one.
_ALLOWED_TERMS = frozenset("""
    i i'm my me english vietnamese vietnam a an the and or but for with without to from
    in on at by of as is are was were be been being have has had do does did will would
    can could should may might must not no yes if then than that this these those
    software engineer engineering developer development backend frontend fullstack full-stack
    system systems service services application applications platform platforms
    team teams project projects product production code coding clean architecture
    api apis rest restful microservice microservices database databases cloud devops
    test testing unit integration coverage pipeline pipelines deployment agile scrum
    experience experienced familiar comfortable focused building built build develop
    developed developing maintain maintained maintaining implement implemented
    design designed designing scalable reliable reliability quality performance
    computer science bachelor university graduate graduating fresher junior senior
    january february march april may june july august september october november december
    jan feb mar apr jun jul aug sep sept oct nov dec
    """.split())

# A token is "technology-looking" if it has an internal capital (PostgreSQL, JaCoCo),
# contains a digit or a tech punctuation mark (S3, C#, C++, Node.js), or is simply
# capitalised. Plain lowercase prose never trips the check.
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#._-]*")
_INTERNAL_CAPS = re.compile(r"[a-z][A-Z]")
_HAS_TECH_PUNCT = re.compile(r"[0-9+#]")

# Vendor and foundation names that qualify a product rather than being a claim of
# their own — but ONLY when the word they qualify is already on the CV.
#
# A CV saying "Kafka" made "Apache Kafka" — the product's own full name — a
# rejected claim, twice, while the bare "Kafka" passed. The conditional is what
# keeps this from being a hole: "Apache Spark" is still caught when Spark is
# absent, and a bare "experience with Apache" is still caught, because in
# neither case does a known product follow. Only the qualifier is forgiven, and
# only when the distinctive half has already been checked and passed.
#
# The qualified word must also be *distinctive*. Allowing any vocabulary word
# opened a real hole, because a CV saying "database" or "cloud" is saying
# nothing about a vendor: "Oracle Database", "Google Cloud" and even "Microsoft
# Java" all passed on a CV that named none of them. Requiring the next token to
# be absent from _ALLOWED_TERMS — the generic-English list — is what closes it,
# since that is exactly where words like database, cloud and platform live.
#
# Multi-word vendors ("Red Hat") are deliberately absent: they would have to be
# matched as a phrase, and split into tokens they let "Hat" qualify anything.
_QUALIFIERS = frozenset(
    "apache google amazon aws microsoft azure oracle cloudera elastic "
    "jetbrains atlassian hashicorp".split()
)


#: Maximal runs of digits. Decimal points and separators are deliberately not
#: joined: "3.7" yields {"3", "7"}, so a text claiming 3.7 when the CV says 3.5
#: is caught on the "7". A digit inside a name counts too ("S3" yields "3"),
#: which is what lets a name copied from the CV carry its own digits through.
_DIGITS = re.compile(r"\d+")

#: Number words worth checking like digits. Deliberately excludes one..ten and
#: "quarter"/"couple": those double as ordinary English filler ("one of the",
#: "a couple of things") and would false-positive on prose that isn't claiming
#: a metric at all (``_SMALL_WITH_UNIT`` below picks up the cases where they
#: are). What's left still catches "led a team of twelve" or
#: "cut costs by half" written out instead of numerals — the exact way a model
#: could dodge the digit check while still inventing a figure.
#:
#: English only. A figure spelled out in Vietnamese ("mười hai", "gấp đôi") is
#: not seen; numerals are, in any language.
_NUMBER_WORDS = frozenset(
    """
    eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen
    twenty thirty forty fifty sixty seventy eighty ninety
    dozen dozens hundred hundreds thousand thousands million millions billion billions
    half halved double doubled triple tripled quadruple quadrupled
    """.split()
)
_WORD_RE = re.compile(r"[a-zA-Z]+")

#: one..ten are left out of ``_NUMBER_WORDS`` because they are ordinary filler
#: ("one of the two services"). Followed by a unit of time or scale they are not
#: filler, they are a claim — and "over one year of experience" is exactly how a
#: model rewrites "1+ years" once the digit has been rejected. Counted as the
#: digit they spell, so "two years" is backed by a CV that says "2 years".
_SMALL_NUMBERS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
}  # fmt: skip
_SMALL_WITH_UNIT = re.compile(
    r"\b(" + "|".join(_SMALL_NUMBERS) + r")\b(?:\s*\+|\s+plus)?[\s-]+"
    r"(?:years?|yrs?|months?|weeks?|decades?|percent|times)\b"
    r"|\b(" + "|".join(_SMALL_NUMBERS) + r")-?fold\b",
    re.IGNORECASE,
)


def _clean(token: str) -> str:
    """Drop trailing punctuation the token regex swallows (sentence-final ``Boot.``)
    while keeping it inside a name (``Node.js``, ``CI/CD`` halves, ``C++``)."""
    return token.rstrip("._-")


def terms_in(*values: str | None) -> set[str]:
    """Lowercased tokens of ``values``, split exactly the way the checker splits.

    Anything assembling a vocabulary for :func:`unknown_terms` must come through
    here rather than ``str.split()``. The two disagree, and the disagreement
    stays invisible until it isn't: ``_TOKEN_RE`` does not include ``&``, so
    "Panasonic R&D Center" splits to ``r`` and ``d`` here but to ``r&d`` on
    whitespace. A vocabulary built the second way *contains* the employer's name
    under a spelling the checker never produces, and the letter is then rejected
    for "claiming experience with R, D" — both real language names — when all it
    did was address the company by its own name. One tokenizer, both sides.
    """
    out: set[str] = set()
    for value in values:
        for raw in _TOKEN_RE.findall(value or ""):
            token = _clean(raw)
            if token:
                out.add(token.lower())
    return out


@dataclass
class PlanReport:
    """Outcome of checking a plan; ``ok`` means it is safe to apply."""

    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def raise_if_bad(self) -> None:
        if self.violations:
            raise GuardrailViolation("; ".join(self.violations))


# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #
def _iter_text(doc: CvDocument):
    h = doc.header
    yield from (h.first_name, h.last_name, h.position, h.address or "", h.quote or "")
    if h.extra_info:
        yield h.extra_info.label
    for s in doc.sections:
        yield s.title
        if isinstance(s, ParagraphSection):
            yield s.text
        elif isinstance(s, BulletsSection):
            for item in s.items:
                yield item.label or ""
                yield item.text
        elif isinstance(s, EducationSection):
            for e in s.entries:
                yield from (e.degree, e.institution, e.location, *e.items)
        elif isinstance(s, (ExperienceSection, ProjectsSection)):
            for e in s.entries:
                yield from (e.title, e.role or "", *e.items, *e.tech_stack)


def vocabulary(doc: CvDocument) -> set[str]:
    """Every word the Master CV actually contains, lowercased."""
    vocab: set[str] = set()
    for chunk in _iter_text(doc):
        for raw in _TOKEN_RE.findall(chunk or ""):
            token = _clean(raw)
            if not token:
                continue
            lowered = token.lower()
            vocab.add(lowered)
            # "CI/CD" and "Node.js" arrive as one token; also index the parts so a
            # summary saying "CI" or "Node" isn't flagged.
            vocab.update(p for p in re.split(r"[._-]", lowered) if p)
    return vocab


def master_text(doc: CvDocument) -> str:
    """Everything the Master CV's sections say, dates included, as one blob.

    This is the source for number provenance, so unlike :func:`vocabulary` it
    includes the date fields: "2024" in a summary is a fact the CV states. The
    header contributes its headline and quote — free text the user wrote — but
    not the phone number or address, whose digits are not facts about the work.
    """
    parts: list[str] = [doc.header.position, doc.header.quote or ""]
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


def numbers_in(*values: str | None) -> set[str]:
    """Every figure ``values`` state: digit runs, plus spelled-out number words."""
    out: set[str] = set()
    for value in values:
        text = value or ""
        out.update(_DIGITS.findall(text))
        out.update(w.lower() for w in _WORD_RE.findall(text) if w.lower() in _NUMBER_WORDS)
        for m in _SMALL_WITH_UNIT.finditer(text):
            out.add(_SMALL_NUMBERS[(m.group(1) or m.group(2)).lower()])
    return out


def unknown_numbers(text: str, allowed: set[str]) -> list[str]:
    """Figures in ``text`` that none of the allowed sources ever state."""
    return sorted(numbers_in(text) - allowed)


def _is_tech_looking(token: str, at_sentence_start: bool) -> bool:
    if _INTERNAL_CAPS.search(token) or _HAS_TECH_PUNCT.search(token):
        return True
    return token[:1].isupper() and not at_sentence_start


def unknown_terms(text: str, vocab: set[str]) -> list[str]:
    """Technology-looking tokens in ``text`` that the Master CV never mentions."""
    unknown: list[str] = []
    seen: set[str] = set()
    for sentence in re.split(r"(?<=[.!?])\s+", text or ""):
        tokens = [_clean(m.group()) for m in _TOKEN_RE.finditer(sentence)]
        for i, token in enumerate(tokens):
            if not token:
                continue
            lowered = token.lower()
            if lowered in vocab or lowered in _ALLOWED_TERMS or lowered in seen:
                continue
            nxt = tokens[i + 1].lower() if i + 1 < len(tokens) else ""
            if lowered in _QUALIFIERS and nxt in vocab and nxt not in _ALLOWED_TERMS:
                continue
            if _is_tech_looking(token, at_sentence_start=i == 0):
                seen.add(lowered)
                unknown.append(token)
    return unknown


# --------------------------------------------------------------------------- #
# Plan checking
# --------------------------------------------------------------------------- #
def _check_order(order: list[int], size: int, label: str, out: list[str]) -> None:
    """An order must be a duplicate-free subset of the master indices."""
    if not order:
        return
    if len(set(order)) != len(order):
        out.append(f"{label}: duplicate indices {order}")
    bad = [i for i in order if not 0 <= i < size]
    if bad:
        out.append(f"{label}: indices {bad} out of range (0..{size - 1})")


def check_plan(plan: TailorPlan, master: CvDocument) -> PlanReport:
    """Validate a plan against the Master CV. Empty violations means safe to apply."""
    out: list[str] = []
    by_key = {s.key: s for s in master.sections}

    if plan.section_order:
        unknown_keys = [k for k in plan.section_order if k not in by_key]
        if unknown_keys:
            out.append(f"section_order: unknown section keys {unknown_keys}")
        if len(set(plan.section_order)) != len(plan.section_order):
            out.append("section_order: duplicate section keys")
        missing = set(by_key) - set(plan.section_order)
        if missing:
            out.append(f"section_order: must list every section, missing {sorted(missing)}")

    for sp in plan.sections:
        section = by_key.get(sp.key)
        if section is None:
            out.append(f"sections: unknown section key {sp.key!r}")
            continue
        entries = getattr(section, "entries", None)
        items = getattr(section, "items", None)
        if sp.entry_order:
            if entries is None:
                out.append(f"sections[{sp.key}]: entry_order on a section with no entries")
            else:
                _check_order(sp.entry_order, len(entries), f"sections[{sp.key}].entry_order", out)
        if sp.item_order:
            if items is None:
                out.append(f"sections[{sp.key}]: item_order on a section with no items")
            else:
                _check_order(sp.item_order, len(items), f"sections[{sp.key}].item_order", out)

    for ep in plan.entries:
        section = by_key.get(ep.section_key)
        entries = getattr(section, "entries", None) if section else None
        if entries is None:
            out.append(f"entries: {ep.section_key!r} is not a section with entries")
            continue
        if not 0 <= ep.entry_index < len(entries):
            out.append(
                f"entries[{ep.section_key}]: entry_index {ep.entry_index} out of range "
                f"(0..{len(entries) - 1})"
            )
            continue
        entry = entries[ep.entry_index]
        label = f"entries[{ep.section_key}#{ep.entry_index}]"
        _check_order(ep.bullet_order, len(entry.items), f"{label}.bullet_order", out)
        stack = getattr(entry, "tech_stack", [])
        _check_order(ep.tech_stack_order, len(stack), f"{label}.tech_stack_order", out)
        if ep.tech_stack_order and not stack:
            out.append(f"{label}: tech_stack_order on an entry with no tech stack")

    if plan.summary:
        invented = unknown_terms(plan.summary, vocabulary(master))
        if invented:
            out.append(
                "summary mentions technologies absent from the Master CV: "
                + ", ".join(invented)
                + " — remove them (SKILL.md §0: never claim a skill the CV cannot back up)"
            )
        figures = unknown_numbers(plan.summary, numbers_in(master_text(master)))
        if figures:
            out.append(
                "summary states the number(s) "
                + ", ".join(figures)
                + ", which the Master CV never states — remove them (SKILL.md §0: never "
                "claim a metric the CV cannot back up)"
            )

    for req in plan.requirements:
        if req.status == "MISSING" and req.evidence.strip():
            out.append(f"requirement {req.text!r}: MISSING must not cite evidence")

    return PlanReport(violations=out)
