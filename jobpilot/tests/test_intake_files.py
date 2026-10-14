"""Adding a job from a screenshot or a PDF, and saying where it was found.

Two small additions to the paste flow, and the assertions are again mostly about
what they refuse to do: a file is turned into *text* and nothing else (the
fields are read from that text by the same call a paste makes), a PDF that
carries its own text never reaches a model, and the source a user picks changes
the ``source`` column without ever changing which row the job is.

Every posting here is invented.
"""

from __future__ import annotations

import base64
from datetime import timedelta

import pytest

from jobpilot.api.deps import get_db
from jobpilot.api.main import app
from jobpilot.api.routes.intake import get_engine
from jobpilot.api.schemas import HAND_SOURCES
from jobpilot.config import get_config, get_secrets
from jobpilot.cv import importer
from jobpilot.intake import service
from jobpilot.intake.engine import FixtureIntakeEngine, IntakeError, ModelIntakeEngine
from jobpilot.intake.prompt import MAX_JD_CHARS
from jobpilot.intake.schema import JdExtract, JdSections, JdTranscript
from jobpilot.llm.base import Attachment, Completion, LlmError, Usage
from jobpilot.crawler.normalize import normalize
from jobpilot.crawler.persist import persist_jobs
from jobpilot.crawler.types import RawJob
from jobpilot.store.models import Job, Run
from jobpilot.timeutil import vn_now
from jobpilot.tests.conftest import api_client
from jobpilot.tests.test_cv_import import HEIC, JPEG, PNG, text_pdf

AUTH = {"X-API-Token": get_secrets().jobpilot_api_token}

POST_LINES = (
    "WE ARE HIRING - BACKEND ENGINEER - NORTHWIND LABS",
    "Northwind Labs builds logistics software for retailers across Southeast Asia.",
    "Requirements",
    "- 2+ years of Java and Spring Boot",
    "- REST APIs and SQL in production",
    "Benefits",
    "- 13th month salary and 15 days of leave",
    "Send your CV to careers@northwind.example",
)
POST_TEXT = "\n".join(POST_LINES)
assert len(POST_TEXT) >= 200

EXTRACT = JdExtract(
    title="Backend Engineer",
    company="Northwind Labs",
    location="",
    salary="",
    level="",
    employment_type="",
    work_mode="",
    skills=["Java", "Spring Boot"],
    apply_email="careers@northwind.example",
    language="en",
)
SECTIONS = JdSections(
    role="",
    responsibilities=[],
    must_have=["2+ years of Java and Spring Boot"],
    nice_to_have=[],
    soft_skills=[],
    outputs=[],
    benefits=["13th month salary and 15 days of leave"],
    how_to_apply="Send your CV to careers@northwind.example",
)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _upload(*files: bytes) -> dict:
    return {"files": [{"name": f"page-{n}", "data": _b64(data)} for n, data in enumerate(files, 1)]}


@pytest.fixture
def intake_engine() -> FixtureIntakeEngine:
    return FixtureIntakeEngine(
        extracted=EXTRACT,
        parsed=SECTIONS,
        transcript=JdTranscript(text=POST_TEXT, unreadable=[]),
    )


@pytest.fixture
def client(session_factory, intake_engine):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_engine] = lambda: intake_engine
    c = api_client(app)
    c.headers.update(AUTH)
    yield c
    app.dependency_overrides.clear()


def _save(client, **overrides) -> dict:
    body = {
        "url": "https://social.example.com/groups/it-jobs/posts/1001",
        "title": "Backend Engineer",
        "company": "Northwind Labs",
        "description_md": POST_TEXT,
    }
    body.update(overrides)
    r = client.post("/jobs", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# a picture becomes text, and only text
# --------------------------------------------------------------------------- #
def test_a_screenshot_is_typed_out_and_nothing_is_saved(client, intake_engine, session_factory):
    intake_engine.transcript = JdTranscript(text=POST_TEXT, unreadable=["the salary line is cropped", " "])

    r = client.post("/jobs/intake/file", json=_upload(PNG, JPEG))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"] == POST_TEXT and body["transcribed"] is True
    assert body["unreadable"] == ["the salary line is cropped"]
    assert [f["media_type"] for f in body["files"]] == ["image/png", "image/jpeg"]

    # One call, both pages — and no field was read: that is the paste's call.
    assert [len(call) for call in intake_engine.transcribe_calls] == [2]
    assert intake_engine.extract_calls == [] and intake_engine.section_calls == []
    with session_factory() as s:
        assert s.query(Job).count() == 0


def test_a_pdf_with_its_own_text_never_reaches_a_model(client, intake_engine):
    r = client.post("/jobs/intake/file", json=_upload(text_pdf(*POST_LINES)))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transcribed"] is False and body["unreadable"] == []
    # The publisher's words, line for line.
    assert [line.strip() for line in body["text"].splitlines() if line.strip()] == list(POST_LINES)
    assert intake_engine.transcribe_calls == []


def test_a_pdf_whose_text_is_only_a_stamp_is_read_by_the_model(client, intake_engine):
    r = client.post("/jobs/intake/file", json=_upload(text_pdf("Page 1 of 1")))
    assert r.status_code == 200 and r.json()["transcribed"] is True
    assert r.json()["text"] == POST_TEXT
    assert len(intake_engine.transcribe_calls) == 1


def test_a_page_of_caption_does_not_stand_in_for_the_poster_beside_it(client, intake_engine):
    """The floor is per page. A printed post is a page of caption and a page
    that is one picture; passed on the strength of the caption, the box would
    hold the page chrome under a note saying no model was needed."""
    r = client.post(
        "/jobs/intake/file", json=_upload(text_pdf(*POST_LINES), text_pdf("Page 2 of 2"))
    )
    assert r.status_code == 200 and r.json()["transcribed"] is True
    assert [len(call) for call in intake_engine.transcribe_calls] == [2]


def test_a_file_of_the_wrong_kind_is_not_told_how_to_import_a_cv(client, intake_engine):
    detail = client.post("/jobs/intake/file", json=_upload(HEIC)).json()["detail"]
    assert "pasted straight into the box" in detail and "CV" not in detail


def test_a_pdf_beside_a_photo_is_read_as_a_whole_not_half_from_each(client, intake_engine):
    r = client.post("/jobs/intake/file", json=_upload(text_pdf(*POST_LINES), PNG))
    assert r.status_code == 200 and r.json()["transcribed"] is True
    assert [len(call) for call in intake_engine.transcribe_calls] == [2]


def test_a_page_break_in_a_transcript_stays_a_line_break(client, intake_engine):
    intake_engine.transcript = JdTranscript(text="Requirements\x0c- Java\r\n- SQL\x00", unreadable=[])
    r = client.post("/jobs/intake/file", json=_upload(PNG))
    assert r.json()["text"] == "Requirements\n- Java\n- SQL"


def test_a_picture_with_no_posting_in_it_is_refused_with_what_it_showed(client, intake_engine):
    intake_engine.transcript = JdTranscript(text="  \n", unreadable=["a photo of a restaurant menu"])
    r = client.post("/jobs/intake/file", json=_upload(PNG))
    assert r.status_code == 422
    assert "no job posting could be read" in r.json()["detail"]
    assert "restaurant menu" in r.json()["detail"]


def test_a_transcript_the_size_of_a_careers_site_is_refused(client, intake_engine):
    intake_engine.transcript = JdTranscript(text="x" * (MAX_JD_CHARS + 1), unreadable=[])
    r = client.post("/jobs/intake/file", json=_upload(PNG))
    assert r.status_code == 422 and f"{MAX_JD_CHARS:,}" in r.json()["detail"]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"files": []}, "no file was uploaded"),
        (_upload(HEIC), "not a PNG, JPEG, WebP or PDF"),
        ({"files": [{"name": "x", "data": "not base64 !!"}]}, "did not arrive intact"),
        (_upload(*[PNG] * (importer.MAX_FILES + 1)), "at most 6 files"),
    ],
)
def test_an_unusable_upload_is_a_422_with_a_sentence(client, intake_engine, body, message):
    r = client.post("/jobs/intake/file", json=body)
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str) and message in r.json()["detail"]
    assert intake_engine.transcribe_calls == []


def test_a_provider_failure_is_a_502(client, intake_engine):
    intake_engine.transcript = None
    assert client.post("/jobs/intake/file", json=_upload(PNG)).status_code == 502


def test_a_backend_with_no_key_is_a_409_before_the_upload_is_read(client, monkeypatch):
    app.dependency_overrides.pop(get_engine)
    monkeypatch.setattr("jobpilot.llm.blocker", lambda task: f"no key for {task}")
    r = client.post("/jobs/intake/file", json=_upload(PNG))
    assert r.status_code == 409 and r.json()["detail"] == "no key for intake"


def test_the_file_endpoint_needs_the_token(client):
    r = client.post("/jobs/intake/file", json=_upload(PNG), headers={"X-API-Token": "wrong"})
    assert r.status_code == 401


def test_what_is_stored_is_the_text_that_passed_through_the_form(client, intake_engine):
    """The whole flow: picture -> text -> fields -> row. The description the job
    ends up with is the transcript the form showed, not a second reading."""
    text = client.post("/jobs/intake/file", json=_upload(PNG)).json()["text"]
    fields = client.post("/jobs/intake", json={"text": text}).json()
    assert fields["title"] == "Backend Engineer" and fields["description_md"] == POST_TEXT

    job = _save(
        client,
        title=fields["title"],
        company=fields["company"],
        description_md=fields["description_md"],
        source="facebook",
    )
    assert job["source"] == "facebook" and job["description_md"] == POST_TEXT


# --------------------------------------------------------------------------- #
# the engine call
# --------------------------------------------------------------------------- #
class _Client:
    provider = "fake"
    model = "fake-1"

    def __init__(self, reply=None, error: Exception | None = None):
        self.reply, self.error, self.calls = reply, error, []

    def structured(self, *, system, messages, schema):
        self.calls.append({"system": system, "messages": messages, "schema": schema})
        if self.error:
            raise self.error
        return Completion(value=self.reply, usage=Usage(provider="fake", model="fake-1"))


@pytest.fixture
def recorded(monkeypatch):
    rows: list = []
    monkeypatch.setattr("jobpilot.llm.usage.record", rows.append)
    return rows


IMAGE = Attachment(media_type="image/png", data=PNG, name="post.png")


def test_the_transcription_is_one_call_with_the_files_attached(recorded):
    reply = JdTranscript(text=POST_TEXT, unreadable=[])
    llm_client = _Client(reply=reply)
    assert ModelIntakeEngine(llm_client).transcribe([IMAGE, IMAGE]) == reply

    (call,) = llm_client.calls
    assert call["schema"] is JdTranscript
    (turn,) = call["messages"]
    assert turn["attachments"] == [IMAGE, IMAGE] and "2 files" in turn["content"]
    # The two rules a transcription lives or dies by.
    assert "DO NOT WRITE" in call["system"] and "Do not translate" in call["system"]
    # Under its own name, so a picture's cost is not hidden among the pastes.
    assert [(r.task, r.accepted) for r in recorded] == [("intake_file", True)]


def test_a_dead_backend_is_an_intake_error_and_is_still_logged(recorded):
    engine = ModelIntakeEngine(_Client(error=LlmError("rate limited")))
    with pytest.raises(IntakeError, match="rate limited"):
        engine.transcribe([IMAGE])
    assert [(r.task, r.accepted) for r in recorded] == [("intake_file", False)]


def test_every_field_of_the_transcript_schema_is_required():
    schema = JdTranscript.model_json_schema()
    assert sorted(schema["required"]) == sorted(schema["properties"])
    assert "anyOf" not in str(schema) and "default" not in str(schema)


def test_read_files_refuses_before_calling_the_engine():
    engine = FixtureIntakeEngine(transcript=JdTranscript(text=POST_TEXT, unreadable=[]))
    with pytest.raises(service.IntakeRefused, match="not a PNG, JPEG, WebP or PDF"):
        service.read_files([("photo.heic", HEIC)], engine)
    assert engine.transcribe_calls == []


# --------------------------------------------------------------------------- #
# where the user found it
# --------------------------------------------------------------------------- #
def test_a_job_added_by_hand_is_manual_until_the_user_says_where_it_was(client):
    job = _save(client)
    assert job["source"] == "manual" and job["id"].startswith("manual:")


@pytest.mark.parametrize("source", [s for s in HAND_SOURCES if s != "manual"])
def test_the_source_is_what_the_user_picked_and_the_id_does_not_move(client, source):
    job = _save(client, source=source)
    assert job["source"] == source
    # Same id whatever the source: it is what makes a re-paste land on this row.
    assert job["id"] == _save(client)["id"] and job["id"].startswith("manual:")


def test_a_job_found_on_facebook_is_listed_under_facebook(client):
    _save(client, source="facebook")
    _save(client, url="https://careers.example.com/2", title="Data Engineer")

    found = client.get("/jobs", params={"source": "facebook"}).json()
    assert [j["title"] for j in found["items"]] == ["Backend Engineer"]
    assert client.get("/stats").json()["by_source"] == {"facebook": 1, "manual": 1}


def test_re_pasting_without_a_source_keeps_the_one_it_has(client, session_factory):
    first = _save(client, source="facebook")
    again = _save(client, salary="20 - 30 triệu")
    assert again["id"] == first["id"] and again["source"] == "facebook"

    changed = _save(client, source="zalo")
    assert changed["id"] == first["id"] and changed["source"] == "zalo"
    with session_factory() as s:
        assert s.query(Job).count() == 1


def test_a_source_off_the_list_is_a_422_not_a_new_bar_on_every_chart(client, session_factory):
    r = client.post(
        "/jobs", json={"title": "Backend Engineer", "company": "Northwind Labs", "source": "fb"}
    )
    assert r.status_code == 422
    with session_factory() as s:
        assert s.query(Job).count() == 0


def test_the_source_of_a_hand_added_job_can_be_corrected(client):
    job = _save(client)
    r = client.patch(f"/jobs/{job['id']}", json={"source": "linkedin"})
    assert r.status_code == 200 and r.json()["source"] == "linkedin"
    assert r.json()["id"] == job["id"]


def test_a_crawled_jobs_source_is_not_up_for_correction(client, session_factory):
    with session_factory() as s:
        s.add(Job(id="itviec:backend-engineer-northwind", source="itviec", title="Backend Engineer"))
        s.commit()

    r = client.patch("/jobs/itviec:backend-engineer-northwind", json={"source": "facebook"})
    assert r.status_code == 422 and "crawled" in r.json()["detail"]
    with session_factory() as s:
        assert s.get(Job, "itviec:backend-engineer-northwind").source == "itviec"


# --------------------------------------------------------------------------- #
# what a source the user picked must not be mistaken for
# --------------------------------------------------------------------------- #
def test_a_job_filed_under_linkedin_by_hand_is_not_reported_as_taken_down(client, session_factory):
    """Its `last_seen_at` is the moment it was pasted; no crawl ever looked for
    it. Two LinkedIn passes later it must not read "not seen — possibly gone"."""
    job = _save(client, url="https://www.linkedin.com/jobs/view/4000000001", source="linkedin")
    with session_factory() as s:
        for days in (1, 2, 3):
            s.add(
                Run(
                    kind="crawl",
                    started_at=vn_now() + timedelta(days=days),
                    stats={"sites": {"linkedin": {"ok": True, "fetched": 5}}},
                )
            )
        s.commit()

    detail = client.get(f"/jobs/{job['id']}").json()
    assert detail["source"] == "linkedin"
    assert "not_seen" not in detail["quality"]["flags"]


def test_the_boards_own_copy_of_a_hand_added_posting_is_still_a_copy(client, session_factory):
    """Filed under `linkedin` by hand, then the same role arrives from the
    LinkedIn source with the title worded the board's way. One job, not two —
    the same-board rule is about a board's listings, and this row is not one."""
    _save(
        client,
        url="https://www.linkedin.com/jobs/view/4000000001",
        source="linkedin",
        title="Backend Engineer (Java)",
    )
    cfg = get_config()
    raw = RawJob(
        source="linkedin",
        native_id="4000000001",
        url="https://www.linkedin.com/jobs/view/4000000001",
        title="Backend Engineer",
        company="Northwind Labs",
        posted_raw="2 days ago",
        skills=["Java"],
        description_md=POST_TEXT,
    )
    with session_factory() as s:
        now = vn_now()
        report = persist_jobs(s, [normalize(raw, cfg, now)], dedup_days=14, now=now)
        s.commit()
        assert (report.inserted, report.duplicates) == (0, 1)
        assert s.query(Job).count() == 1


def test_the_market_page_counts_a_hand_added_job_under_its_source(client):
    _save(client, source="facebook")
    _save(client, url="https://careers.example.com/jobs/2", title="Data Engineer", source="zalo")
    job = _save(client, url="https://careers.example.com/jobs/3", title="QA Engineer")
    client.patch(f"/jobs/{job['id']}", json={"source": "linkedin"})

    rows = client.get("/analytics/market").json()["sources"]["rows"]
    assert {row["key"]: row["count"] for row in rows} == {"facebook": 1, "zalo": 1, "linkedin": 1}


# --------------------------------------------------------------------------- #
# which row a pasted address lands on
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("first", "second"),
    [
        # A photo viewer: the post is in the query, the path is the word "photo".
        (
            "https://www.facebook.com/photo/?fbid=1000000000000001&set=gm.2000000000000001",
            "https://www.facebook.com/photo/?fbid=1000000000000002&set=gm.2000000000000002",
        ),
        # A notification link: the path ends in the *group*.
        (
            "https://www.facebook.com/groups/3000000000000001/?multi_permalinks=4000000000000001",
            "https://www.facebook.com/groups/3000000000000001/?multi_permalinks=4000000000000002",
        ),
        (
            "https://www.facebook.com/permalink.php?story_fbid=5000000000000001&id=1",
            "https://www.facebook.com/permalink.php?story_fbid=5000000000000002&id=1",
        ),
        (
            "https://www.facebook.com/groups/3000000000000001/posts/6000000000000001/",
            "https://www.facebook.com/groups/3000000000000001/posts/6000000000000002/",
        ),
        # No post in the address at all: a group, a chat invite.
        ("https://www.facebook.com/groups/3000000000000001", "https://www.facebook.com/groups/3000000000000001/"),
        ("https://zalo.me/g/abcdef123", "https://zalo.me/g/abcdef123"),
        # A page that lists every job the company has.
        ("https://northwind.example/careers", "https://southwind.example/careers"),
    ],
)
def test_two_postings_never_share_a_row_because_their_addresses_look_alike(
    client, session_factory, first, second
):
    one = _save(client, url=first, source="facebook")
    two = _save(client, url=second, title="Data Analyst", company="Southwind Studio")

    assert one["id"] != two["id"]
    kept = client.get(f"/jobs/{one['id']}").json()
    # The first job is still the first job: nothing of the second was written on it.
    assert (kept["title"], kept["company"], kept["source"]) == (
        "Backend Engineer",
        "Northwind Labs",
        "facebook",
    )
    with session_factory() as s:
        assert s.query(Job).count() == 2


@pytest.mark.parametrize(
    "url",
    [
        "https://www.linkedin.com/jobs/view/4000000001",
        "https://www.linkedin.com/jobs/search/?currentJobId=4000000001&keywords=backend",
        "linkedin.com/jobs/view/4000000001",
    ],
)
def test_a_linkedin_job_number_is_the_posting_whatever_the_form_says(client, session_factory, url):
    """The one address trusted outright: the number belongs to exactly one
    posting, so correcting the title between pastes must not fork the row."""
    first = _save(client, url=url)
    again = _save(client, url=url, title="Senior Platform Engineer", salary="30 triệu")
    assert first["id"] == again["id"] == "manual:linkedin-4000000001"
    assert again["title"] == "Senior Platform Engineer"
    with session_factory() as s:
        assert s.query(Job).count() == 1


@pytest.mark.parametrize(
    ("first", "second", "titles"),
    [
        # The address bar while browsing LinkedIn: the job is in the query.
        (
            "https://www.linkedin.com/jobs/search/?currentJobId=4000000011",
            "https://www.linkedin.com/jobs/search/?currentJobId=4000000012",
            ("Junior Backend Engineer", "Senior Backend Engineer"),
        ),
        (
            "https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4000000021",
            "https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4000000022",
            ("Backend Engineer (Java)", "Backend Engineer (Python)"),
        ),
        # An embedded board: the posting is a query parameter of one careers page.
        (
            "https://northwind.example/careers?gh_jid=7000001",
            "https://northwind.example/careers?gh_jid=7000002",
            ("Junior Backend Engineer", "Senior Backend Engineer"),
        ),
        (
            "https://northwind.example/careers",
            "https://northwind.example/careers",
            ("Backend Engineer Intern", "Lead Backend Engineer"),
        ),
        # One recruiter's post, two roles.
        (
            "https://www.facebook.com/groups/3000000000000001/posts/6000000000000009/",
            "https://www.facebook.com/groups/3000000000000001/posts/6000000000000009/",
            ("Backend Engineer", "QA Tester"),
        ),
    ],
)
def test_two_roles_at_one_company_are_two_jobs_however_alike_they_look(
    client, session_factory, first, second, titles
):
    """Same employer, so the forgiving cross-board key calls them one role:
    it drops "Junior" and "(Java)". Here that would write the second job over
    the first — its status, its tailored CV, its application — and answer 201."""
    one = _save(client, url=first, title=titles[0])
    two = _save(client, url=second, title=titles[1])

    assert one["id"] != two["id"]
    assert client.get(f"/jobs/{one['id']}").json()["title"] == titles[0]
    with session_factory() as s:
        assert s.query(Job).count() == 2


def test_the_same_role_from_the_same_post_is_still_one_job(client, session_factory):
    url = "https://www.facebook.com/groups/3000000000000001/posts/6000000000000009/"
    first = _save(client, url=url, source="facebook")
    again = _save(client, url=url, salary="20 - 30 triệu")
    assert again["id"] == first["id"] == "manual:facebook-6000000000000009"
    assert again["salary"] == "20 - 30 triệu" and again["source"] == "facebook"
    with session_factory() as s:
        assert s.query(Job).count() == 1


@pytest.mark.parametrize(
    "url",
    [
        # No scheme: nothing for a URL parser to call a host.
        "facebook.com/photo/?fbid=1000000000000001",
        "www.facebook.com/groups/3000000000000001",
        # A value that is all punctuation is not a post number.
        "https://www.facebook.com/photo/?fbid=%00%0a",
    ],
)
def test_a_facebook_address_is_read_as_one_however_it_was_copied(client, url):
    job = _save(client, url=url)
    assert job["id"] in {
        "manual:facebook-1000000000000001",
        "manual:northwind-labs-backend-engineer",
    }
    assert "photo" not in job["id"] and not job["id"].endswith(":job")


def test_a_vague_address_still_updates_the_job_it_was_first_pasted_for(client, session_factory):
    first = _save(client, url="https://northwind.example/careers")
    again = _save(client, url="https://northwind.example/careers", salary="20 - 30 triệu")
    assert again["id"] == first["id"] and again["salary"] == "20 - 30 triệu"
    # ...and the second job at the same address keeps landing on its own row.
    other = _save(client, url="https://northwind.example/careers", title="Data Analyst")
    assert _save(client, url="https://northwind.example/careers", title="Data Analyst")["id"] == other["id"]
    with session_factory() as s:
        assert s.query(Job).count() == 2


@pytest.mark.parametrize(
    "url",
    ["https://www.facebook.com/groups/3000000000000001", "https://zalo.me/g/abcdef123"],
)
def test_a_group_address_does_not_become_the_jobs_identity(client, session_factory, url):
    """The group is where the post was, not which post it was. Named after the
    group, the job would get a twin the first time it is pasted without the
    link — and an id that reads as if the whole group were this one job."""
    with_link = _save(client, url=url)
    without = _save(client, url="")
    assert with_link["id"] == without["id"] == "manual:northwind-labs-backend-engineer"
    with session_factory() as s:
        assert s.query(Job).count() == 1


LONG_NAME = (
    "Northwind Logistics and Electronic Commerce Software Solutions Joint Stock Company of Vietnam"
)


@pytest.mark.parametrize(
    ("company", "url", "titles"),
    [
        # A legal name long enough to fill the slug before the title begins.
        (LONG_NAME, "", ("Backend Engineer", "QA Tester")),
        (LONG_NAME, "https://zalo.me/g/abcdef123", ("Software Engineer (Java)", "Software Engineer (Python)")),
        # Three roles from one post: the first keeps the post's id, the other
        # two both fall back — and must not fall onto each other.
        (
            LONG_NAME,
            "https://www.facebook.com/groups/3000000000000001/posts/6000000000000009/",
            ("Backend Engineer", "QA Tester", "Data Analyst"),
        ),
        # Titles the normalisers reduce to nothing.
        ("Northwind Labs", "", ("招聘工程师", "テスター")),
        ("Northwind Labs", "https://northwind.example/careers", ("招聘工程师", "テスター")),
    ],
)
def test_jobs_the_slug_cannot_tell_apart_still_get_a_row_each(
    client, session_factory, company, url, titles
):
    saved = [_save(client, url=url, company=company, title=title) for title in titles]
    assert len({job["id"] for job in saved}) == len(titles)
    assert all(len(job["id"]) <= 128 for job in saved)
    # Pasted again, each lands on its own row and nowhere else.
    again = [_save(client, url=url, company=company, title=title) for title in titles]
    assert [job["id"] for job in again] == [job["id"] for job in saved]
    with session_factory() as s:
        assert sorted(j.title for j in s.query(Job)) == sorted(titles)


def test_an_id_that_fitted_before_is_the_id_it_still_gets(client):
    """The digest is only for a slug two jobs share. Everything that already
    had a row keeps the id that row was saved under."""
    assert _save(client, url="")["id"] == "manual:northwind-labs-backend-engineer"


@pytest.mark.parametrize("number", ["٣٤", "12²", "abc", ""])
def test_only_ascii_digits_make_a_linkedin_job_number(client, number):
    job = _save(client, url=f"https://www.linkedin.com/jobs/search/?currentJobId={number}")
    assert not job["id"].startswith("manual:linkedin-")


def test_an_address_inside_the_query_is_not_this_addresss_scheme(client):
    job = _save(client, url="facebook.com/groups/3000000000000001?ref=https://example.com/x")
    assert job["id"] == "manual:northwind-labs-backend-engineer"

