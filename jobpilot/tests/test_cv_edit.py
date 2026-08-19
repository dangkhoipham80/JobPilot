"""Editing the Master CV by instruction, and the provenance guard behind it.

The rule under test is not "is this on the CV?" — that would reject every real
new project — but "does every word and number trace to something the *user*
said?". The interesting cases are the ones where those two answers differ.

Every field of every op is required (see ``tailor/edit.py`` for why the provider
forced that), so these helpers fill them in rather than each test spelling out
six empty strings.
"""

from __future__ import annotations

import pytest

from jobpilot.cv.sample import sample_document
from jobpilot.cv.schema import BulletsSection, CvDocument, Entry, Header, ProjectsSection
from jobpilot.tailor.edit import (
    Drop,
    MasterEditPlan,
    Merge,
    NewBullet,
    NewEntry,
    Rewrite,
    apply_edits,
    empty_plan,
)
from jobpilot.tailor.edit_guard import check_edit_plan

INSTRUCTION = (
    "Add a project called JobPilot: a job crawler built with FastAPI and React "
    "that tailors my CV. I worked on it from Jan 2026 to Mar 2026."
)
QUOTE = "a job crawler built with FastAPI and React that tailors my CV"


def plan(**kw) -> MasterEditPlan:
    """A plan with everything empty except what the test supplies."""
    return empty_plan().model_copy(update=kw)


def rewrite(section_key="summary", entry_index=-1, item_index=-1, text="", quote="") -> Rewrite:
    return Rewrite(
        section_key=section_key,
        entry_index=entry_index,
        item_index=item_index,
        text=text,
        source_quote=quote,
        reason="test",
    )


def new_entry(section_key="projects", title="JobPilot", date="", role="", tech="", items=None, quote=QUOTE) -> NewEntry:
    return NewEntry(
        section_key=section_key,
        title=title,
        date=date,
        role=role,
        tech_stack=tech,
        items=list(items or []),
        source_quote=quote,
        reason="test",
    )


def _check(p: MasterEditPlan, instruction: str = INSTRUCTION, master: CvDocument | None = None):
    return check_edit_plan(p, master or sample_document(), instruction)


# --------------------------------------------------------------------------- #
# The new boundary: user-supplied facts are allowed, invented ones are not
# --------------------------------------------------------------------------- #
def test_a_new_project_the_user_described_is_accepted():
    """The whole point of the feature: a real project not yet on the CV."""
    report = _check(
        plan(
            new_entries=[
                new_entry(
                    date="Jan 2026 - Mar 2026",
                    tech="FastAPI, React",
                    items=["A job crawler that tailors my CV."],
                )
            ]
        )
    )
    assert report.ok, report.violations


def test_adding_without_a_quote_is_refused():
    report = _check(plan(new_entries=[new_entry(quote="")]))
    assert not report.ok
    assert "requires source_quote" in " ".join(report.violations)


def test_a_paraphrased_quote_is_refused():
    """Matched as a substring, so 'close enough' is not enough."""
    report = _check(plan(new_entries=[new_entry(quote="he built a crawler using FastAPI")]))
    assert not report.ok
    assert "does not appear in the instruction" in " ".join(report.violations)


def test_a_real_quote_does_not_license_unrelated_technology():
    """The quote buys the instruction as a source — not carte blanche."""
    report = _check(plan(new_entries=[new_entry(items=["Deployed on Terraform."])]))
    assert not report.ok
    assert "Terraform" in " ".join(report.violations)


def test_an_invented_metric_is_refused():
    """The hole the tailor guard cannot see: digits are not 'technology-looking'."""
    report = _check(plan(new_entries=[new_entry(items=["Crawled 50000 jobs per day."])]))
    assert not report.ok
    assert "50000" in " ".join(report.violations)


def test_a_number_the_user_gave_is_accepted():
    report = _check(
        plan(
            rewrites=[
                rewrite(
                    text="Backend engineer with 3 years of experience.",
                    quote="I have 3 years of experience",
                )
            ]
        ),
        instruction="Rewrite my summary. I have 3 years of experience now.",
    )
    assert report.ok, report.violations


def test_a_rewrite_may_not_invent_a_metric():
    """No quote, so nothing beyond the Master CV is licensed — including numbers."""
    report = _check(plan(rewrites=[rewrite(text="Improved throughput by 40%.")]))
    assert not report.ok
    assert "40" in " ".join(report.violations)


def test_a_rewrite_from_master_content_is_accepted():
    report = _check(
        plan(rewrites=[rewrite(text="Backend engineer working with `Java Spring Boot` and RESTful APIs.")])
    )
    assert report.ok, report.violations


def test_merging_two_bullets_needs_no_quote():
    report = _check(
        plan(
            merges=[
                Merge(
                    section_key="experience",
                    entry_index=0,
                    item_indices=[0, 1],
                    text="Built and migrated RESTful APIs in a microservices environment.",
                    source_quote="",
                    reason="test",
                )
            ]
        )
    )
    assert report.ok, report.violations


# --------------------------------------------------------------------------- #
# Addressing — same discipline as the tailor guard
# --------------------------------------------------------------------------- #
def test_unknown_section_is_refused():
    report = _check(plan(rewrites=[rewrite(section_key="nope", text="x")]))
    assert not report.ok
    assert "unknown section key" in " ".join(report.violations)


def test_out_of_range_entry_index_is_refused():
    report = _check(
        plan(
            merges=[
                Merge(
                    section_key="experience",
                    entry_index=99,
                    item_indices=[0, 1],
                    text="x",
                    source_quote="",
                    reason="test",
                )
            ]
        )
    )
    assert not report.ok
    assert "out of range" in " ".join(report.violations)


def test_merge_needs_at_least_two_bullets():
    report = _check(
        plan(
            merges=[
                Merge(
                    section_key="experience",
                    entry_index=0,
                    item_indices=[0],
                    text="x",
                    source_quote="",
                    reason="test",
                )
            ]
        )
    )
    assert not report.ok
    assert "at least 2" in " ".join(report.violations)


def test_education_entries_are_not_added_by_instruction():
    """A degree is not the kind of fact worth letting a model append."""
    report = _check(
        plan(new_entries=[new_entry(section_key="education", title="PhD", quote="a job crawler")]),
        instruction="add a job crawler",
    )
    assert not report.ok
    assert "by hand" in " ".join(report.violations)


@pytest.mark.parametrize("kind", ["new_bullets", "new_entries"])
def test_every_additive_op_demands_a_quote(kind):
    """Pinned as a pair: the two ops that create content must not diverge."""
    op = (
        NewBullet(section_key="skills", entry_index=-1, text="X", source_quote="", reason="t")
        if kind == "new_bullets"
        else new_entry(quote="")
    )
    report = _check(plan(**{kind: [op]}))
    assert not report.ok
    assert "requires source_quote" in " ".join(report.violations)


# --------------------------------------------------------------------------- #
# Applying
# --------------------------------------------------------------------------- #
def test_apply_never_mutates_the_master():
    master = sample_document()
    before = master.model_dump_json()
    apply_edits(master, plan(rewrites=[rewrite(text="X")]))
    assert master.model_dump_json() == before


def test_indices_resolve_against_the_original_not_the_running_result():
    """Dropping items 0-1 must not turn 'rewrite item 2' into the wrong line."""
    doc = CvDocument(
        header=Header(first_name="A", last_name="B"),
        sections=[
            BulletsSection(
                key="sk",
                title="Skills",
                items=[{"text": "zero"}, {"text": "one"}, {"text": "two"}],  # type: ignore[list-item]
            )
        ],
    )
    out = apply_edits(
        doc,
        plan(
            drops=[Drop(section_key="sk", entry_index=-1, item_indices=[0, 1], reason="t")],
            rewrites=[rewrite(section_key="sk", item_index=2, text="rewritten")],
        ),
    )
    assert [i.text for i in out.sections[0].items] == ["rewritten"]


def test_merge_keeps_the_first_slot_and_removes_the_rest():
    doc = CvDocument(
        header=Header(first_name="A", last_name="B"),
        sections=[
            ProjectsSection(key="prj", title="Projects", entries=[Entry(title="P", items=["a", "b", "c"])])
        ],
    )
    out = apply_edits(
        doc,
        plan(
            merges=[
                Merge(
                    section_key="prj",
                    entry_index=0,
                    item_indices=[0, 2],
                    text="a and c",
                    source_quote="",
                    reason="t",
                )
            ]
        ),
    )
    assert out.sections[0].entries[0].items == ["a and c", "b"]


def test_two_ops_may_not_claim_the_same_bullet():
    """apply_edits resolves against the original, so the loser vanishes silently."""
    report = _check(
        plan(
            merges=[
                Merge(
                    section_key="experience",
                    entry_index=0,
                    item_indices=[0, 2],
                    text="merged",
                    source_quote="",
                    reason="t",
                )
            ],
            rewrites=[rewrite(section_key="experience", entry_index=0, item_index=0, text="rewritten")],
        )
    )
    assert not report.ok
    assert "already claimed" in " ".join(report.violations)


def test_a_new_entry_splits_its_tech_stack():
    """`tech_stack` is one string in the schema and a list on the CV."""
    doc = CvDocument(
        header=Header(first_name="A", last_name="B"),
        sections=[ProjectsSection(key="prj", title="Projects", entries=[])],
    )
    out = apply_edits(doc, plan(new_entries=[new_entry(section_key="prj", tech="FastAPI, React")]))
    assert out.sections[0].entries[0].tech_stack == ["FastAPI", "React"]
