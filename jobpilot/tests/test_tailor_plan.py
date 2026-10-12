"""Phase 5: the truthfulness guardrails, plan application, and the review diff."""

from __future__ import annotations

import pytest

from jobpilot.cv.schema import CvDocument, ParagraphSection
from jobpilot.cv.sample import sample_document
from jobpilot.tailor.apply import apply_plan
from jobpilot.tailor.diff import diff_documents
from jobpilot.tailor.guard import (
    GuardrailViolation,
    check_plan,
    master_text,
    numbers_in,
    unknown_terms,
    vocabulary,
)
from jobpilot.tailor.prompt import render_master, system_prompt
from jobpilot.tailor.schema import EntryPlan, Requirement, SectionPlan, TailorPlan


@pytest.fixture
def master() -> CvDocument:
    return sample_document()


def _plan(**kw) -> TailorPlan:
    return TailorPlan(match_score=kw.pop("match_score", 0.7), **kw)


# --------------------------------------------------------------------------- #
# Vocabulary / summary guard — the anti-fabrication core
# --------------------------------------------------------------------------- #
def test_vocabulary_covers_tech_stacks_and_bullets(master):
    vocab = vocabulary(master)
    for word in ("java", "spring", "jacoco", "grafana", "leetcode", "fastapi"):
        assert word in vocab
    assert "kafka" in vocab  # from the Lumen tech stack


def test_vocabulary_splits_compound_tokens(master):
    """ "CI/CD" and "Node.js"-style tokens are indexed whole and in parts."""
    vocab = vocabulary(master)
    assert "ci" in vocab and "cd" in vocab


def test_unknown_terms_flags_invented_tech(master):
    vocab = vocabulary(master)
    assert unknown_terms("Experienced with Java and Spring Boot.", vocab) == []
    assert unknown_terms("Experienced with Java and Kubernetes.", vocab) == []  # in Skills
    assert unknown_terms("Also proficient in Golang and Terraform.", vocab) == [
        "Golang",
        "Terraform",
    ]


def test_unknown_terms_strips_sentence_final_punctuation(master):
    """ "...Spring Boot." must not read as an unknown term called "Boot."."""
    assert unknown_terms("Built services with Spring Boot.", vocabulary(master)) == []


def test_unknown_terms_ignores_ordinary_prose(master):
    vocab = vocabulary(master)
    text = "Backend engineer focused on reliable, well-tested services. Comfortable in a team."
    assert unknown_terms(text, vocab) == []


def test_unknown_terms_ignores_sentence_initial_capitals(master):
    """A capitalised first word is grammar, not a skill claim."""
    assert unknown_terms("Passionate about clean code.", vocabulary(master)) == []


def test_unknown_terms_catches_internal_caps_anywhere(master):
    """Internal capitals mark a product name even at the start of a sentence."""
    assert unknown_terms("RabbitMQ is used daily.", vocabulary(master)) == ["RabbitMQ"]


def test_summary_with_invented_skill_is_rejected(master):
    report = check_plan(
        _plan(summary="Backend engineer using `Java` and `Kafka` and Elasticsearch."), master
    )
    assert not report.ok
    assert "Elasticsearch" in report.violations[0]
    with pytest.raises(GuardrailViolation):
        report.raise_if_bad()


def test_summary_reusing_master_vocabulary_is_accepted(master):
    plan = _plan(
        summary="Backend engineer building **RESTful APIs** with `Spring Boot` and `JUnit`."
    )
    assert check_plan(plan, master).ok


def test_summary_with_an_invented_metric_is_rejected(master):
    """The term check starts every token at a letter, so it never sees a number.
    This summary names no technology at all and used to pass untouched."""
    report = check_plan(
        _plan(summary="Backend engineer who improved throughput by 40% and led a team of 12."),
        master,
    )
    assert not report.ok
    assert "40" in report.violations[0] and "12" in report.violations[0]
    with pytest.raises(GuardrailViolation):
        report.raise_if_bad()


def test_summary_with_a_spelled_out_metric_is_rejected(master):
    """ "twelve" is exactly as unbacked as "12"."""
    report = check_plan(_plan(summary="Backend engineer who led a team of twelve."), master)
    assert not report.ok and "twelve" in report.violations[0]


def test_summary_may_repeat_a_number_the_cv_states(master):
    stated = sorted(numbers_in(master_text(master)), key=len)[-1]  # a year, e.g. "2024"
    assert check_plan(_plan(summary=f"Backend engineer since {stated}."), master).ok


def test_summary_small_number_words_are_deliberately_not_checked(master):
    """one..ten are ordinary English ("one of the two services"); checking them
    would reject prose that claims no metric. Same trade-off as the edit guard."""
    plan = _plan(summary="Backend engineer on one of the two core services of the team.")
    assert check_plan(plan, master).ok


def test_a_digit_inside_a_name_counts_as_a_number():
    """ "S3" copied from the CV carries its "3" with it; "S3" from nowhere does not."""
    assert numbers_in("stored in S3 and EC2") == {"3", "2"}


# --------------------------------------------------------------------------- #
# Structural guard
# --------------------------------------------------------------------------- #
def test_out_of_range_entry_index_rejected(master):
    plan = _plan(entries=[EntryPlan(section_key="experience", entry_index=9)])
    assert "out of range" in check_plan(plan, master).violations[0]


def test_duplicate_indices_rejected(master):
    plan = _plan(sections=[SectionPlan(key="projects", entry_order=[0, 0, 1])])
    assert "duplicate" in check_plan(plan, master).violations[0]


def test_unknown_section_key_rejected(master):
    assert not check_plan(_plan(sections=[SectionPlan(key="nope")]), master).ok


def test_section_order_must_be_complete(master):
    plan = _plan(section_order=["summary", "skills"])
    assert "missing" in check_plan(plan, master).violations[0]


def test_item_order_on_entry_section_rejected(master):
    plan = _plan(sections=[SectionPlan(key="experience", item_order=[0])])
    assert "item_order" in check_plan(plan, master).violations[0]


def test_missing_requirement_may_not_cite_evidence(master):
    plan = _plan(
        requirements=[
            Requirement(text="Kafka", kind="must_have", status="MISSING", evidence="experience")
        ]
    )
    assert "must not cite evidence" in check_plan(plan, master).violations[0]


def test_empty_plan_is_valid(master):
    """A job that already matches needs no edits — that must be expressible."""
    assert check_plan(_plan(), master).ok


# --------------------------------------------------------------------------- #
# apply_plan
# --------------------------------------------------------------------------- #
def test_apply_empty_plan_is_identity(master):
    assert apply_plan(master, _plan()).model_dump() == master.model_dump()


def test_apply_does_not_mutate_master(master):
    before = master.model_dump()
    apply_plan(master, _plan(sections=[SectionPlan(key="projects", entry_order=[2, 0, 1])]))
    assert master.model_dump() == before


def test_apply_reorders_and_drops_entries(master):
    out = apply_plan(master, _plan(sections=[SectionPlan(key="projects", entry_order=[2, 0])]))
    projects = next(s for s in out.sections if s.key == "projects")
    assert [e.title.split(" --")[0] for e in projects.entries] == ["Roundtable", "Lumen"]


def test_apply_reorders_tech_stack_within_an_entry(master):
    plan = _plan(
        entries=[EntryPlan(section_key="experience", entry_index=0, tech_stack_order=[3, 0])]
    )
    exp = next(s for s in apply_plan(master, plan).sections if s.key == "experience")
    assert exp.entries[0].tech_stack == ["JUnit", "Java"]


def test_apply_entry_edits_survive_a_section_reorder(master):
    """Entry edits are keyed by master index, so they must land before the shuffle."""
    plan = _plan(
        sections=[SectionPlan(key="projects", entry_order=[2, 1, 0])],
        entries=[EntryPlan(section_key="projects", entry_index=2, tech_stack_order=[1, 0])],
    )
    projects = next(s for s in apply_plan(master, plan).sections if s.key == "projects")
    assert projects.entries[0].title.startswith("Roundtable")
    assert projects.entries[0].tech_stack[:2] == ["Firebase", "FastAPI"]


def test_apply_hides_a_section(master):
    out = apply_plan(master, _plan(sections=[SectionPlan(key="honors", enabled=False)]))
    assert next(s for s in out.sections if s.key == "honors").enabled is False
    assert "resume/honors.tex" not in {s.key for s in out.active_sections()}


def test_apply_reorders_sections(master):
    order = ["summary", "skills", "experience", "projects", "education", "honors"]
    assert [s.key for s in apply_plan(master, _plan(section_order=order)).sections] == order


def test_apply_replaces_the_summary(master):
    out = apply_plan(master, _plan(summary="Backend engineer with `Java` and `Spring Boot`."))
    para = next(s for s in out.sections if isinstance(s, ParagraphSection))
    assert para.text == "Backend engineer with `Java` and `Spring Boot`."


def test_apply_validates_by_default(master):
    with pytest.raises(GuardrailViolation):
        apply_plan(master, _plan(sections=[SectionPlan(key="ghost")]))


# --------------------------------------------------------------------------- #
# diff
# --------------------------------------------------------------------------- #
def test_diff_of_identical_documents_is_empty(master):
    diff = diff_documents(master, master.model_copy(deep=True))
    assert not diff.changed
    assert all(s.status == "unchanged" for s in diff.sections)


def test_diff_reports_section_reorder(master):
    order = ["summary", "skills", "experience", "projects", "education", "honors"]
    diff = diff_documents(master, apply_plan(master, _plan(section_order=order)))
    assert diff.order_changed
    assert diff.order_after == order


def test_diff_reports_hidden_section(master):
    tailored = apply_plan(master, _plan(sections=[SectionPlan(key="honors", enabled=False)]))
    honors = next(s for s in diff_documents(master, tailored).sections if s.key == "honors")
    assert honors.status == "hidden"


def test_diff_reports_rewritten_summary(master):
    tailored = apply_plan(master, _plan(summary="Backend engineer with `Java`."))
    summary = next(s for s in diff_documents(master, tailored).sections if s.key == "summary")
    assert summary.status == "rewritten"
    assert summary.after == "Backend engineer with `Java`."
    assert summary.before and summary.before != summary.after


def test_diff_reports_dropped_entries_as_trimmed(master):
    tailored = apply_plan(master, _plan(sections=[SectionPlan(key="projects", entry_order=[0])]))
    projects = next(s for s in diff_documents(master, tailored).sections if s.key == "projects")
    assert projects.status == "trimmed"
    assert any("dropped entries" in n for n in projects.notes)


def test_diff_reports_tech_stack_reorder(master):
    plan = _plan(
        entries=[EntryPlan(section_key="experience", entry_index=0, tech_stack_order=[3, 0])]
    )
    exp = next(
        s
        for s in diff_documents(master, apply_plan(master, plan)).sections
        if s.key == "experience"
    )
    assert exp.status == "trimmed"  # indices were dropped as well as reordered
    assert any("tech stack" in n for n in exp.notes)


# --------------------------------------------------------------------------- #
# The plan schema must be usable as a structured-output format
# --------------------------------------------------------------------------- #
def test_plan_schema_is_structured_output_compatible():
    """Every object needs additionalProperties:false, and numeric/string
    constraints are unsupported — the API would reject or silently drop them."""
    import json

    schema = TailorPlan.model_json_schema()

    def objects(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                yield node
            for value in node.values():
                yield from objects(value)
        elif isinstance(node, list):
            for value in node:
                yield from objects(value)

    assert all(o.get("additionalProperties") is False for o in objects(schema))
    dumped = json.dumps(schema)
    for unsupported in ("minimum", "maximum", "minLength", "maxLength", "multipleOf"):
        assert unsupported not in dumped


def test_match_score_is_clamped_rather_than_rejected():
    assert TailorPlan(match_score=1.4).match_score == 1.0
    assert TailorPlan(match_score=-0.2).match_score == 0.0


# --------------------------------------------------------------------------- #
# prompt
# --------------------------------------------------------------------------- #
def test_outline_indices_match_the_plan_address_space(master):
    outline = render_master(master)
    assert "SECTION experience" in outline
    assert "entry[0] Example Software" in outline
    assert "tech[0] Java" in outline
    assert "item[0] Languages & Frameworks:" in outline


def test_system_prompt_carries_the_truthfulness_rule(master):
    text = system_prompt(master)
    assert "Never claim a skill" in text
    assert "MASTER CV" in text


# --------------------------------------------------------------------------- #
# Vendor qualifiers (found when an apply failed twice on a real cover letter)
# --------------------------------------------------------------------------- #
def test_a_vendor_prefix_is_not_a_separate_claim():
    """A CV listing "Kafka" made "Apache Kafka" -- the product's own full name --
    a rejected claim, while the bare "Kafka" passed."""
    from jobpilot.tailor.guard import unknown_terms

    vocab = {"kafka", "spring", "boot"}
    assert unknown_terms("I am eager to learn Apache Kafka.", vocab) == []
    assert unknown_terms("Built with Spring Boot.", vocab) == []


def test_the_qualifier_is_only_forgiven_in_front_of_something_known():
    """This is what keeps it from being a hole. The distinctive half still has
    to be on the CV; only the vendor name riding in front of it is excused."""
    from jobpilot.tailor.guard import unknown_terms

    vocab = {"kafka"}
    # Spark is not on the CV, so the claim is still caught.
    assert "Spark" in unknown_terms("I am eager to learn Apache Spark.", vocab)
    # And a bare vendor name claims something of its own -- the HTTP server.
    assert unknown_terms("I have experience with Apache.", vocab) == ["Apache"]
    assert "S3" in unknown_terms("I use Amazon S3 daily.", vocab)


def test_a_qualifier_needs_a_distinctive_word_after_it():
    """The first version of this fix opened a real hole. Allowing any vocabulary
    word after the qualifier meant a CV saying "database" or "cloud" -- which
    says nothing about a vendor -- let "Oracle Database", "Google Cloud" and even
    "Microsoft Java" through on a CV naming none of them. That trades a false
    positive, which costs a retry, for a false negative, which puts a fabricated
    product on a letter to an employer."""
    from jobpilot.tailor.guard import unknown_terms

    vocab = {"kafka", "database", "cloud", "java"}
    assert unknown_terms("Experience with Oracle Database.", vocab) == ["Oracle"]
    assert unknown_terms("Built on Google Cloud.", vocab) == ["Google"]
    # And the case the fix exists for still works, because Kafka is distinctive.
    assert unknown_terms("Eager to learn Apache Kafka.", vocab) == []


def test_multi_word_vendors_are_not_split_into_qualifiers():
    """"Red Hat" as two tokens would let "Hat" qualify anything that follows."""
    from jobpilot.tailor.guard import _QUALIFIERS

    assert "hat" not in _QUALIFIERS and "red" not in _QUALIFIERS
