"""The Master's projects are a pool: a tailored CV keeps the few that fit the job."""

from __future__ import annotations

import pytest

from jobpilot.cv.sample import sample_document
from jobpilot.cv.schema import CvDocument, Entry, ProjectsSection
from jobpilot.store.models import Job
from jobpilot.tailor.apply import apply_plan
from jobpilot.tailor.guard import check_plan
from jobpilot.tailor.projects import limit_projects, relevance
from jobpilot.tailor.prompt import system_prompt
from jobpilot.tailor.schema import EntryPlan, SectionPlan, TailorPlan

# Sample projects: 0 Lumen (Spring Boot, FastAPI, Kafka...), 1 Pathfinder (Java,
# Spring Boot...), 2 Roundtable (FastAPI, React...). Two more are appended below.
GAME = 3
MOBILE = 4


@pytest.fixture
def master() -> CvDocument:
    doc = sample_document()
    projects = _projects(doc)
    projects.entries += [
        Entry(title="Lantern -- Detective Game (`C#`)", tech_stack=["C#", "Godot 4", "xUnit"]),
        Entry(
            title="Tilefield -- Puzzle App",
            tech_stack=["React Native", "Expo", "TypeScript"],
        ),
    ]
    return doc


def _projects(doc: CvDocument) -> ProjectsSection:
    return next(s for s in doc.sections if isinstance(s, ProjectsSection))


def _job(description: str, skills: list[str] | None = None, title: str = "Engineer") -> Job:
    return Job(
        id="itviec:1",
        source="itviec",
        title=title,
        company="ACME",
        payload={"description_md": description, "skills": skills or []},
    )


def _titles(doc: CvDocument) -> list[str]:
    return [e.title.split(" -- ")[0] for e in _projects(doc).entries]


def test_relevance_matches_whole_terms_only(master):
    game = _projects(master).entries[GAME]
    assert relevance(game, "we write c# and ship on godot 4") == 2
    # "Java" must not light up inside "JavaScript", nor "C#" inside "C#-like".
    pathfinder = _projects(master).entries[1]
    assert relevance(pathfinder, "javascript frontend") == 0


def test_empty_order_is_ranked_by_overlap_with_the_job(master):
    job = _job("Mobile developer: React Native, Expo, TypeScript. C# and Godot 4 a plus.")
    plan = limit_projects(TailorPlan(match_score=0.5), master, job, cap=2)

    doc = apply_plan(master, plan)
    assert _titles(doc) == ["Tilefield", "Lantern"]
    assert check_plan(plan, master).ok


def test_ties_keep_the_masters_own_order(master):
    """No overlap at all → the owner's ordering decides, not chance."""
    plan = limit_projects(TailorPlan(match_score=0.5), master, _job("Rust, Go"), cap=3)
    assert _titles(apply_plan(master, plan)) == ["Lumen", "Pathfinder", "Roundtable"]


def test_the_models_choice_is_cut_not_reranked(master):
    plan = TailorPlan(
        match_score=0.5, sections=[SectionPlan(key="projects", entry_order=[1, 0, 2, GAME])]
    )
    out = limit_projects(plan, master, _job("Godot, C#"), cap=3)
    assert _titles(apply_plan(master, out)) == ["Pathfinder", "Lumen", "Roundtable"]


def test_a_choice_within_the_cap_is_left_alone(master):
    plan = TailorPlan(match_score=0.5, sections=[SectionPlan(key="projects", entry_order=[2])])
    assert limit_projects(plan, master, _job("x"), cap=3) == plan


def test_the_cut_is_explained_in_changes(master):
    plan = limit_projects(TailorPlan(match_score=0.5), master, _job("Java, Spring Boot"), cap=2)
    note = [c for c in plan.changes if c.section == "projects"]
    assert len(note) == 1
    assert "Lantern" in note[0].what and "Tilefield" in note[0].what


def test_entry_plans_for_dropped_projects_are_removed(master):
    plan = TailorPlan(
        match_score=0.5,
        entries=[
            EntryPlan(section_key="projects", entry_index=GAME, bullet_order=[]),
            EntryPlan(section_key="projects", entry_index=1, tech_stack_order=[1, 0]),
        ],
    )
    out = limit_projects(plan, master, _job("Java, Spring Boot"), cap=2)
    assert [(e.section_key, e.entry_index) for e in out.entries] == [("projects", 1)]


def test_hidden_section_and_small_pool_and_no_limit_are_untouched(master):
    hidden = TailorPlan(match_score=0.5, sections=[SectionPlan(key="projects", enabled=False)])
    assert limit_projects(hidden, master, _job("Java"), cap=2) == hidden

    small = sample_document()  # three projects
    plan = TailorPlan(match_score=0.5)
    assert limit_projects(plan, small, _job("Java"), cap=3) == plan
    assert limit_projects(plan, master, _job("Java"), cap=0) == plan


def test_master_is_not_mutated(master):
    before = master.model_dump()
    limit_projects(TailorPlan(match_score=0.5), master, _job("C#"), cap=1)
    assert master.model_dump() == before


def test_prompt_tells_the_model_the_limit(master):
    assert "(3 at most)" in system_prompt(master)
    assert "(2 at most)" in system_prompt(master, max_projects=2)
    unlimited = system_prompt(master, max_projects=0)
    assert "{max_projects}" not in unlimited and "as many as fit" in unlimited


def test_prompt_ranks_projects_by_strength_before_overlap(master):
    """A coursework project that shares the job's language must not outrank a
    production one in another language — the model was told to rank by overlap
    and did exactly that (PHASES.md, tailor-project-strength)."""
    prompt = system_prompt(master)
    assert prompt.index("**Strength**") < prompt.index("**Relevance**")
    assert "Never fill the limit with a weak project" in prompt
    assert "Judge relevance by shared technologies" not in prompt
