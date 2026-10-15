"""Parked entries: tagged entries the owner keeps in the Master but off every CV."""

from __future__ import annotations

import pytest

from jobpilot.cv import store as cv_store
from jobpilot.cv.render import render_document
from jobpilot.cv.sample import sample_document
from jobpilot.cv.schema import CvDocument, ProjectsSection
from jobpilot.store.models import Job, JobStatus
from jobpilot.tailor import service
from jobpilot.tailor.engine import TailorResult
from jobpilot.tailor.schema import TailorPlan


def _projects(doc: CvDocument) -> ProjectsSection:
    return next(s for s in doc.sections if isinstance(s, ProjectsSection))


@pytest.fixture
def doc() -> CvDocument:
    d = sample_document()
    entries = _projects(d).entries
    assert len(entries) >= 3
    entries[1].tags = ["Game"]
    entries[2].tags = ["school", "java"]
    return d


def test_untagged_hiding_changes_nothing(doc):
    assert doc.visible() is doc  # no hidden tags: no copy, nothing filtered


def test_visible_drops_entries_with_a_hidden_tag_case_insensitively(doc):
    doc.hidden_tags = [" game "]
    kept = _projects(doc.visible()).entries
    titles = [e.title for e in _projects(doc).entries]
    assert [e.title for e in kept] == [titles[0]] + titles[2:]


def test_visible_leaves_the_document_itself_alone(doc):
    doc.hidden_tags = ["game", "school"]
    before = doc.model_dump()
    doc.visible()
    assert doc.model_dump() == before


def test_parked_entry_is_not_rendered(doc):
    parked = _projects(doc).entries[1].title.split(" -- ")[0].strip("`*")
    assert parked in render_document(doc)["resume/projects.tex"]
    doc.hidden_tags = ["game"]
    assert parked not in render_document(doc)["resume/projects.tex"]


def test_tags_round_trip_and_old_documents_still_load():
    raw = sample_document().model_dump()
    for section in raw["sections"]:
        for entry in section.get("entries", []):
            entry.pop("tags", None)
    raw.pop("hidden_tags")
    loaded = CvDocument.model_validate(raw)  # a version saved before tags existed
    assert loaded.hidden_tags == [] and _projects(loaded).entries[0].tags == []


class _Recorder:
    """An engine that remembers the Master it was shown."""

    def __init__(self) -> None:
        self.seen: CvDocument | None = None

    def tailor(self, master, job, instruction=None, previous=None):
        self.seen = master
        return TailorResult(plan=TailorPlan(match_score=0.5))


@pytest.fixture
def db(session_factory, doc):
    with session_factory() as s:
        doc.hidden_tags = ["game"]
        cv_store.save_version(s, cv_store.MASTER_SCOPE, doc, author="user")
        s.add(
            Job(
                id="itviec:9",
                source="itviec",
                title="Backend Engineer",
                company="ACME",
                status=JobStatus.SHORTLISTED,
                payload={"description_md": "Java, Spring Boot"},
            )
        )
        s.commit()
        yield s


def test_tailor_never_sees_a_parked_entry_and_master_keeps_it(db, doc):
    parked = _projects(doc).entries[1].title
    engine = _Recorder()
    service.tailor_job(db, "itviec:9", engine, compile_pdf=False)

    assert parked not in [e.title for e in _projects(engine.seen).entries]
    tailored = cv_store.get_document(db, "itviec:9")
    assert parked not in [e.title for e in _projects(tailored).entries]
    master = cv_store.get_document(db, cv_store.MASTER_SCOPE)
    assert parked in [e.title for e in _projects(master).entries]
