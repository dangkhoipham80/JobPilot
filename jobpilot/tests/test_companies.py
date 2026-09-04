"""Employers as rows, and the people at them.

The assertions worth having here are about identity and about not losing things:
which spellings fold onto one employer and — more importantly — which ones must
not, that linking runs on every write path rather than only in a backfill, that
re-running the backfill cannot subtract, and that an HR email is *offered* as an
apply target and never written to one.
"""

from __future__ import annotations

import pytest

from jobpilot.api.deps import get_db
from jobpilot.apply.dispatcher import resolve_channel
from jobpilot.api.main import app
from jobpilot.companies.service import company_key, link_all_jobs, resolve_company
from jobpilot.config import get_config, get_secrets
from jobpilot.crawler.persist import persist_jobs
from jobpilot.crawler.types import RawJob
from jobpilot.crawler.normalize import normalize
from jobpilot.store.models import Application, Company, HrContact, Job, JobStatus
from jobpilot.tests.conftest import api_client

AUTH = {"X-API-Token": get_secrets().jobpilot_api_token}


@pytest.fixture
def client(session_factory):
    db = session_factory()
    app.dependency_overrides[get_db] = lambda: db
    with api_client(app) as c:
        yield c, db
    app.dependency_overrides.clear()
    db.close()


def _nj(*, source: str, native_id: str, title: str, company: str, apply_channel: str = "portal"):
    """A crawled posting, normalized the way the pipeline normalizes one.

    ``apply_channel`` defaults to ``portal`` because that is what the real
    scrapers do — every one of them hard-codes ``portal`` or ``external`` and
    none ever emits ``email``. A helper that left it ``None`` would quietly test
    the hand-added case instead, which is the accident that hid the channel bug.
    """
    return normalize(
        RawJob(
            source=source,
            native_id=native_id,
            url=f"https://{source}.example/{native_id}",
            title=title,
            company=company,
            apply_channel=apply_channel,
        ),
        get_config(),
    )


def _job(db, job_id: str, company: str, **kw) -> Job:
    job = Job(id=job_id, source="manual", title="Backend Engineer", company=company, **kw)
    db.add(job)
    db.flush()
    return job


# --------------------------------------------------------------------------- #
# The fold
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "a, b",
    [
        # Case only — the pair that is actually in the corpus.
        ("GitLab", "gitlab"),
        # A legal form written the English way, trailing.
        ("Tinhvan Software JSC.", "Tinhvan Software"),
        ("FPT Software Co., Ltd", "FPT Software"),
        # …and the Vietnamese way, leading.
        ("Công ty TNHH Foo", "Foo"),
        ("Công ty Cổ phần Tinhvan", "Tinhvan"),
        # Accents are folded, as everywhere else in the app.
        ("Việt Nam Post", "Viet Nam Post"),
    ],
)
def test_one_employer_written_two_ways_folds_to_one_key(a, b):
    assert company_key(a) == company_key(b) != ""


@pytest.mark.parametrize(
    "a, b",
    [
        # The dangerous direction. A legal-form word that *starts* a name is
        # part of the name: strip it and two employers share one HR contact
        # list, which is how a CV reaches a stranger.
        ("SA Group", "Group"),
        ("Co-op Bank", "Bank"),
        # A country suffix is not a legal form. DXC Vietnam and DXC are
        # different enough to keep apart until somebody says otherwise.
        ("DXC Technology Vietnam", "DXC Technology"),
        # Different employers that merely share a word.
        ("Axon Active", "Axon"),
    ],
)
def test_different_employers_do_not_fold_together(a, b):
    assert company_key(a) != company_key(b)


def test_mtv_is_only_a_legal_form_after_another_one():
    """"MTV" is "một thành viên" and always follows "Công ty TNHH". Standing
    first it is an ordinary name, and stripping it turned "MTV Networks" into
    "networks" — generic enough to collide with a different employer."""
    assert company_key("MTV Networks") == "mtv networks"
    assert company_key("Công ty TNHH MTV Foo") == "foo"


def test_a_company_key_fits_the_column_that_stores_it(session_factory):
    """Clamped in `company_key`, not at the insert: every lookup selects on this
    value, so a key longer than the column means the SELECT never matches, the
    INSERT trips the unique constraint, and the re-read after that comes back
    empty — `resolve_company` returning None for a company that exists."""
    width = Company.__table__.c.normalized_name.type.length
    key = company_key("Z" * 400)
    assert len(key) == width

    db = session_factory()
    first = resolve_company(db, "Z" * 400)
    db.commit()
    assert first is not None and len(first.name) <= Company.__table__.c.name.type.length
    # The second call must find the first row, not fail to.
    assert resolve_company(db, "Z" * 400).id == first.id


def test_fold_never_strips_a_name_down_to_nothing():
    # An employer called "Company Ltd" must not fold to "", and must land on the
    # same key as one called "Company" rather than falling back to its own
    # unstripped spelling and quietly becoming a second row.
    assert company_key("Company Ltd") == company_key("Company") == "company"
    assert company_key("Ltd") == "ltd"


def test_a_nameless_employer_gets_no_row(session_factory):
    db = session_factory()
    assert company_key("") == ""
    assert resolve_company(db, "") is None
    assert resolve_company(db, "   ") is None
    assert db.query(Company).count() == 0


# --------------------------------------------------------------------------- #
# Linking on the write paths
# --------------------------------------------------------------------------- #
def test_crawled_jobs_link_to_one_company(session_factory):
    db = session_factory()
    jobs = [
        _nj(source="itviec", native_id="1", title="Backend Engineer", company="GitLab"),
        _nj(source="topcv", native_id="2", title="Data Engineer", company="gitlab"),
    ]
    persist_jobs(db, jobs, dedup_days=0)
    db.commit()

    rows = db.query(Job).all()
    assert len(rows) == 2
    assert rows[0].company_id == rows[1].company_id is not None
    assert db.query(Company).count() == 1
    # The string each board printed is untouched — the link is an opinion about
    # it, never a replacement for it.
    assert {r.company for r in rows} == {"GitLab", "gitlab"}


def test_recrawl_relinks_a_corrected_employer_name(session_factory):
    db = session_factory()
    persist_jobs(
        db,
        [_nj(source="itviec", native_id="1", title="Backend", company="Acme")],
        dedup_days=0,
    )
    db.commit()
    first = db.get(Job, "itviec:1").company_id

    # Same posting, employer now spelled properly by the board.
    persist_jobs(
        db,
        [_nj(source="itviec", native_id="1", title="Backend", company="Beta Corp")],
        dedup_days=0,
    )
    db.commit()

    job = db.get(Job, "itviec:1")
    assert job.company_id != first
    assert db.get(Company, job.company_id).normalized_name == "beta"


def test_hand_added_job_is_linked_on_post_and_relinked_on_patch(client):
    c, db = client
    created = c.post(
        "/jobs",
        json={
            "title": "Backend Engineer",
            "company": "Tinhvan Software JSC.",
            "url": "https://x/1",
        },
        headers=AUTH,
    )
    assert created.status_code == 201, created.text
    company_id = created.json()["company_id"]
    assert company_id is not None
    assert db.get(Company, company_id).normalized_name == "tinhvan software"

    patched = c.patch(f"/jobs/{created.json()['id']}", json={"company": "Beta Corp"}, headers=AUTH)
    assert patched.status_code == 200, patched.text
    assert patched.json()["company_id"] != company_id


def test_editing_something_else_never_unlinks_a_job(client):
    """The shape of bug this repo keeps paying for: an unrelated edit clearing a
    derived field. Patching a description must not disturb the company link."""
    c, db = client
    created = c.post(
        "/jobs", json={"title": "Backend", "company": "Acme", "url": "https://x/1"}, headers=AUTH
    ).json()
    before = created["company_id"]
    after = c.patch(
        f"/jobs/{created['id']}", json={"description_md": "A much longer JD."}, headers=AUTH
    ).json()
    assert after["company_id"] == before is not None


# --------------------------------------------------------------------------- #
# The backfill
# --------------------------------------------------------------------------- #
def test_backfill_links_existing_jobs_and_is_idempotent(session_factory):
    db = session_factory()
    _job(db, "manual:a", "GitLab")
    _job(db, "manual:b", "gitlab")
    _job(db, "manual:c", "Binance")
    db.commit()

    first = link_all_jobs(db)
    db.commit()
    assert (first.created, first.linked, first.unlinkable) == (2, 3, 0)

    second = link_all_jobs(db)
    db.commit()
    # Nothing created, nothing re-linked — and, above all, nothing cleared.
    assert (second.created, second.linked) == (0, 0)
    assert db.query(Job).filter(Job.company_id.is_(None)).count() == 0


def test_backfill_names_a_company_after_its_commonest_spelling(session_factory):
    db = session_factory()
    for i in range(3):
        _job(db, f"manual:{i}", "GitLab")
    _job(db, "manual:x", "gitlab")
    db.commit()

    link_all_jobs(db)
    db.commit()
    assert db.query(Company).one().name == "GitLab"


def test_a_tied_display_name_shows_the_name_not_the_paperwork(session_factory):
    """One job each way. Alphabetical alone put the legal form first, so a row
    read "Cong ty TNHH Foo" when "Foo" was equally attested."""
    db = session_factory()
    _job(db, "manual:a", "Cong ty TNHH Foo")
    _job(db, "manual:b", "Foo")
    db.commit()
    link_all_jobs(db)
    db.commit()
    assert db.query(Company).one().name == "Foo"


def test_backfill_leaves_a_renamed_company_alone(session_factory):
    """A backfill that overwrites a correction is a backfill nobody can trust."""
    db = session_factory()
    _job(db, "manual:a", "gitlab")
    db.commit()
    link_all_jobs(db)
    db.commit()

    company = db.query(Company).one()
    company.name = "GitLab Inc"
    db.commit()

    link_all_jobs(db)
    db.commit()
    assert db.query(Company).one().name == "GitLab Inc"


def test_backfill_counts_but_does_not_invent_a_row_for_a_nameless_job(session_factory):
    db = session_factory()
    _job(db, "manual:a", "")
    db.commit()
    result = link_all_jobs(db)
    db.commit()
    assert (result.created, result.linked, result.unlinkable) == (0, 0, 1)
    assert db.query(Company).count() == 0


# --------------------------------------------------------------------------- #
# The API
# --------------------------------------------------------------------------- #
def test_list_counts_jobs_applications_and_contacts(client):
    c, db = client
    _job(db, "manual:a", "Acme")
    _job(db, "manual:b", "Acme")
    _job(db, "manual:c", "Acme")
    db.commit()
    link_all_jobs(db)
    db.commit()

    company = db.query(Company).one()
    db.add(HrContact(company_id=company.id, name="Nguyen A", email="a@acme.example"))
    # Two applications against ONE job: an application that failed and was
    # retried is one job you applied to, not two.
    db.add(Application(job_id="manual:a", result="success", channel="email"))
    db.add(Application(job_id="manual:a", result="success", channel="email"))
    # A portal/external application is handed off for you to submit and lands as
    # `awaiting_user`. Every other part of the app treats that as sent — the
    # board shows it, the follow-up clock starts, inbox sync matches replies to
    # it — so counting only "success" here would report 0 for the employers you
    # are actually chasing, and `order=applied` would bury them.
    db.add(Application(job_id="manual:b", result="awaiting_user", channel="portal"))
    # A dry run never left the machine, and a failed send is an attempt.
    db.add(Application(job_id="manual:c", result="dry_run", channel="email"))
    db.commit()

    body = c.get("/companies", headers=AUTH).json()
    assert body["total"] == 1
    row = body["items"][0]
    assert (row["job_count"], row["applied_count"], row["contact_count"]) == (3, 2, 1)


def test_applied_count_uses_the_app_s_one_definition_of_sent(client):
    """Pinned against the constant, not against a copy of its contents: this
    number has to mean the same thing on /companies as on the board."""
    from jobpilot.apply.followup import SENT_RESULTS

    c, db = client
    for i, result in enumerate(sorted(SENT_RESULTS)):
        _job(db, f"manual:{i}", "Acme")
        db.add(Application(job_id=f"manual:{i}", result=result, channel="email"))
    db.commit()
    link_all_jobs(db)
    db.commit()

    row = c.get("/companies", headers=AUTH).json()["items"][0]
    assert row["applied_count"] == len(SENT_RESULTS)


def test_list_is_a_page_and_caps_its_window(client):
    c, db = client
    for i in range(5):
        _job(db, f"manual:{i}", f"Company {i}")
    db.commit()
    link_all_jobs(db)
    db.commit()

    page = c.get("/companies?limit=2&offset=0", headers=AUTH).json()
    assert page["total"] == 5 and len(page["items"]) == 2
    assert c.get("/companies?limit=500", headers=AUTH).status_code == 422

    # Every row appears exactly once across the pages — the property a tie in
    # the ORDER BY silently breaks, and every company here ties at zero applied.
    seen = []
    for offset in (0, 2, 4):
        seen += [
            r["id"]
            for r in c.get(f"/companies?limit=2&offset={offset}", headers=AUTH).json()["items"]
        ]
    assert sorted(seen) == sorted({r for r in seen}) and len(seen) == 5


def test_default_order_floats_the_employers_you_applied_to(client):
    c, db = client
    _job(db, "manual:a", "Applied Co")
    for i in range(4):
        _job(db, f"manual:b{i}", "Busy Co")
    db.commit()
    link_all_jobs(db)
    db.commit()
    db.add(Application(job_id="manual:a", result="success", channel="email"))
    db.commit()

    names = [r["name"] for r in c.get("/companies", headers=AUTH).json()["items"]]
    assert names[0] == "Applied Co"
    # …while ordering by jobs answers the other question.
    names = [r["name"] for r in c.get("/companies?order=jobs", headers=AUTH).json()["items"]]
    assert names[0] == "Busy Co"


def test_search_matches_the_fold_as_well_as_the_display_name(client):
    c, db = client
    _job(db, "manual:a", "GitLab")
    db.commit()
    link_all_jobs(db)
    db.commit()
    assert c.get("/companies?q=gitlab", headers=AUTH).json()["total"] == 1
    assert c.get("/companies?q=GitLab", headers=AUTH).json()["total"] == 1
    assert c.get("/companies?q=nothing", headers=AUTH).json()["total"] == 0


def test_with_contacts_filter(client):
    c, db = client
    _job(db, "manual:a", "Has Contact")
    _job(db, "manual:b", "No Contact")
    db.commit()
    link_all_jobs(db)
    db.commit()
    target = db.query(Company).filter(Company.normalized_name == "has contact").one()
    db.add(HrContact(company_id=target.id, name="Nguyen A"))
    db.commit()

    body = c.get("/companies?with_contacts=true", headers=AUTH).json()
    assert [r["name"] for r in body["items"]] == ["Has Contact"]
    assert body["total"] == 1


def test_creating_a_company_that_already_exists_returns_it(client):
    c, _ = client
    first = c.post("/companies", json={"name": "gitlab"}, headers=AUTH)
    assert first.status_code == 201
    # Typing the name you know it by must land on the row you meant, not a 409
    # sending you to hunt for a row spelled differently.
    second = c.post("/companies", json={"name": "GitLab"}, headers=AUTH)
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]


def test_a_rename_cannot_move_a_company_s_jobs_or_contacts(client):
    c, db = client
    _job(db, "manual:a", "gitlab")
    db.commit()
    link_all_jobs(db)
    db.commit()
    company = db.query(Company).one()

    body = c.patch(f"/companies/{company.id}", json={"name": "GitLab Inc"}, headers=AUTH).json()
    assert body["name"] == "GitLab Inc"
    # Identity is the fold, and the fold is derived from the jobs — untouched.
    assert body["normalized_name"] == "gitlab"
    assert body["job_count"] == 1


def test_contact_crud_and_field_clamping(client):
    c, db = client
    company = c.post("/companies", json={"name": "Acme"}, headers=AUTH).json()

    made = c.post(
        f"/companies/{company['id']}/contacts",
        json={
            "name": "Nguyen A",
            "phone": " 0900 000 000 ",
            "email": "a@acme.example",
            "note": "met at a meetup",
        },
        headers=AUTH,
    )
    assert made.status_code == 201, made.text
    contact = made.json()
    assert contact["phone"] == "0900 000 000"

    edited = c.patch(
        f"/companies/{company['id']}/contacts/{contact['id']}",
        json={"name": "Nguyen A", "email": "a2@acme.example", "phone": ""},
        headers=AUTH,
    ).json()
    # A blank phone becomes NULL rather than "", so "no number on file" has one
    # spelling and every reader only has to check for one.
    assert edited["email"] == "a2@acme.example" and edited["phone"] is None

    gone = c.delete(f"/companies/{company['id']}/contacts/{contact['id']}", headers=AUTH)
    assert gone.status_code == 200 and gone.json()["contacts"] == []


def test_an_overlong_pasted_signature_does_not_500(client):
    """The scar from the intake batch: SQLite ignores VARCHAR widths and
    Postgres answers an overlong value with a 500 that names no field."""
    c, _ = client
    company = c.post("/companies", json={"name": "Acme"}, headers=AUTH).json()
    made = c.post(
        f"/companies/{company['id']}/contacts",
        json={"name": "N" * 400, "email": "e" * 500, "phone": "0" * 200},
        headers=AUTH,
    )
    assert made.status_code == 201
    body = made.json()
    assert (len(body["name"]), len(body["email"]), len(body["phone"])) == (128, 320, 64)


def test_a_contact_cannot_be_reached_through_another_company(client):
    c, _ = client
    a = c.post("/companies", json={"name": "Acme"}, headers=AUTH).json()
    b = c.post("/companies", json={"name": "Beta"}, headers=AUTH).json()
    contact = c.post(
        f"/companies/{a['id']}/contacts", json={"name": "Nguyen A"}, headers=AUTH
    ).json()

    assert c.get(f"/companies/{b['id']}", headers=AUTH).json()["contacts"] == []
    assert (
        c.patch(
            f"/companies/{b['id']}/contacts/{contact['id']}", json={"name": "Hijack"}, headers=AUTH
        ).status_code
        == 404
    )
    assert (
        c.delete(f"/companies/{b['id']}/contacts/{contact['id']}", headers=AUTH).status_code == 404
    )


def test_contact_needs_a_name(client):
    c, _ = client
    company = c.post("/companies", json={"name": "Acme"}, headers=AUTH).json()
    assert (
        c.post(
            f"/companies/{company['id']}/contacts", json={"name": "  "}, headers=AUTH
        ).status_code
        == 422
    )


def test_detail_says_when_it_truncated_the_job_list(client):
    c, db = client
    from jobpilot.api.routes.companies import JOBS_ON_DETAIL

    for i in range(JOBS_ON_DETAIL + 3):
        _job(db, f"manual:{i}", "Busy Co")
    db.commit()
    link_all_jobs(db)
    db.commit()
    company = db.query(Company).one()

    body = c.get(f"/companies/{company.id}", headers=AUTH).json()
    assert len(body["jobs"]) == JOBS_ON_DETAIL
    assert body["jobs_truncated"] is True
    assert body["job_count"] == JOBS_ON_DETAIL + 3


def test_unknown_company_is_404(client):
    c, _ = client
    assert c.get("/companies/9999", headers=AUTH).status_code == 404


# --------------------------------------------------------------------------- #
# The offer
# --------------------------------------------------------------------------- #
def test_job_detail_carries_the_employer_s_contacts_but_never_applies_one(client):
    """An HR email is *offered* as an apply target, exactly like the address a
    JD prints. Adding a contact must not touch ``apply_target``."""
    c, db = client
    created = c.post(
        "/jobs",
        json={
            "title": "Backend",
            "company": "Acme",
            "url": "https://x/1",
            "apply_target": "https://x/1",
        },
        headers=AUTH,
    ).json()
    company_id = created["company_id"]
    c.post(
        f"/companies/{company_id}/contacts",
        json={"name": "Nguyen A", "email": "hr@acme.example"},
        headers=AUTH,
    )

    detail = c.get(f"/jobs/{created['id']}", headers=AUTH).json()
    assert [x["email"] for x in detail["hr_contacts"]] == ["hr@acme.example"]
    # Offered, not applied.
    assert detail["apply_target"] == "https://x/1"


def test_a_chosen_apply_target_survives_the_next_crawl(session_factory):
    """Found on a live run, not by a test: choosing an HR address held until the
    next crawl of that source and then silently reverted to the board's URL.

    A crawled job is nearly every job, so without this the offer does not
    survive the night — and nothing on screen would show the decision was gone.
    """
    db = session_factory()
    persist_jobs(
        db, [_nj(source="itviec", native_id="1", title="Backend", company="Acme")], dedup_days=0
    )
    db.commit()
    job = db.get(Job, "itviec:1")

    # What the offer button does.
    job.apply_target = "hr@acme.example"
    job.apply_channel = "email"
    job.payload = {**(job.payload or {}), "apply_target_source": "user"}
    db.commit()

    persist_jobs(
        db,
        [_nj(source="itviec", native_id="1", title="Backend Engineer II", company="Acme")],
        dedup_days=0,
    )
    db.commit()
    db.refresh(job)
    assert job.apply_target == "hr@acme.example"
    # The channel too, or the address says one thing and the dispatcher reads
    # the other — the same bug wearing a different hat.
    assert job.apply_channel == "email"
    # …and the provenance itself survives, or it would only hold for one crawl.
    assert job.payload["apply_target_source"] == "user"
    # The rest of the row still refreshes: this is a targeted exception, not a
    # frozen row. Pinned on a field the second crawl actually changed.
    assert job.title == "Backend Engineer II"


def test_an_untouched_apply_target_still_follows_the_board(session_factory):
    """The other half: without a stated target the scraper stays in charge."""
    db = session_factory()
    scraped = _nj(source="itviec", native_id="1", title="Backend", company="Acme")
    persist_jobs(db, [scraped], dedup_days=0)
    db.commit()
    job = db.get(Job, "itviec:1")
    job.apply_target = "https://stale.example/old"
    db.commit()

    persist_jobs(
        db, [_nj(source="itviec", native_id="1", title="Backend", company="Acme")], dedup_days=0
    )
    db.commit()
    db.refresh(job)
    assert job.apply_target == scraped.apply_target


def test_choosing_an_hr_email_actually_makes_the_job_apply_by_email(client):
    """The blocker the review caught: recording the address is not enough.

    Every scraper hard-codes ``apply_channel`` to portal/external and
    ``resolve_channel`` trusts the declared column first, so setting an HR
    address left the job on the handoff path — "open the link and submit it
    yourself", with an email address as the link.
    """
    c, db = client
    persist_jobs(
        db, [_nj(source="itviec", native_id="1", title="Backend", company="Acme")], dedup_days=0
    )
    db.commit()
    assert db.get(Job, "itviec:1").apply_channel == "portal"

    c.patch("/jobs/itviec:1", json={"apply_target": "hr@acme.example"}, headers=AUTH)
    db.expire_all()
    job = db.get(Job, "itviec:1")
    assert job.apply_channel == "email"
    assert resolve_channel(job) == "email"


def test_a_stated_url_target_leaves_the_channel_where_the_board_put_it(client):
    """Promotion is one-directional. A board that said "portal" knows more about
    its own URLs than a guess made here does."""
    c, db = client
    persist_jobs(
        db, [_nj(source="itviec", native_id="1", title="Backend", company="Acme")], dedup_days=0
    )
    db.commit()

    c.patch("/jobs/itviec:1", json={"apply_target": "https://acme.example/apply"}, headers=AUTH)
    db.expire_all()
    assert db.get(Job, "itviec:1").apply_channel == "portal"


def test_an_explicit_channel_in_the_body_is_not_second_guessed(client):
    c, db = client
    persist_jobs(
        db, [_nj(source="itviec", native_id="1", title="Backend", company="Acme")], dedup_days=0
    )
    db.commit()

    c.patch(
        "/jobs/itviec:1",
        json={"apply_target": "hr@acme.example", "apply_channel": "external"},
        headers=AUTH,
    )
    db.expire_all()
    assert db.get(Job, "itviec:1").apply_channel == "external"


def test_a_pasted_job_with_an_email_target_applies_by_email(client):
    """The Add-job form never sends `apply_channel`, so `JobIn`'s "external"
    default meant even the JD's own `apply_email` offer landed on a handoff."""
    c, db = client
    created = c.post(
        "/jobs",
        json={
            "title": "Backend",
            "company": "Acme",
            "url": "https://x/1",
            "apply_target": "careers@acme.example",
        },
        headers=AUTH,
    ).json()
    assert created["apply_channel"] == "email"
    assert resolve_channel(db.get(Job, created["id"])) == "email"


def test_repasting_a_posting_does_not_undo_a_chosen_apply_target(client):
    """`POST /jobs` upserts, so it can land on a row where a person already
    chose where to apply — and the URL fallback used to overwrite it while the
    payload still claimed a person had decided."""
    c, db = client
    body = {"title": "Backend", "company": "Acme", "url": "https://x/1"}
    created = c.post("/jobs", json=body, headers=AUTH).json()
    c.patch(f"/jobs/{created['id']}", json={"apply_target": "hr@acme.example"}, headers=AUTH)

    again = c.post("/jobs", json=body, headers=AUTH).json()
    assert again["apply_target"] == "hr@acme.example"
    assert again["apply_channel"] == "email"


def test_patching_the_apply_target_records_who_chose_it(client):
    c, db = client
    created = c.post(
        "/jobs", json={"title": "Backend", "company": "Acme", "url": "https://x/1"}, headers=AUTH
    ).json()
    assert (db.get(Job, created["id"]).payload or {}).get("apply_target_source") is None

    c.patch(f"/jobs/{created['id']}", json={"apply_target": "hr@acme.example"}, headers=AUTH)
    db.expire_all()
    assert db.get(Job, created["id"]).payload["apply_target_source"] == "user"


def test_an_unrelated_edit_does_not_claim_the_apply_target(client):
    """Only a caller that actually sends the field gets to claim it — otherwise
    pasting a description would freeze the target against every future crawl."""
    c, db = client
    created = c.post(
        "/jobs", json={"title": "Backend", "company": "Acme", "url": "https://x/1"}, headers=AUTH
    ).json()
    c.patch(f"/jobs/{created['id']}", json={"description_md": "A longer JD."}, headers=AUTH)
    db.expire_all()
    assert (db.get(Job, created["id"]).payload or {}).get("apply_target_source") is None


def test_job_detail_of_an_unlinked_job_has_no_contacts(client):
    c, db = client
    _job(db, "manual:nameless", "")
    db.commit()
    detail = c.get("/jobs/manual:nameless", headers=AUTH).json()
    assert detail["company_id"] is None and detail["hr_contacts"] == []


def test_deleting_a_company_unlinks_its_jobs_rather_than_deleting_them(session_factory):
    """ON DELETE SET NULL, not CASCADE: a mistyped employer must not cost you
    eleven postings."""
    db = session_factory()
    _job(db, "manual:a", "Acme", status=JobStatus.SHORTLISTED)
    db.commit()
    link_all_jobs(db)
    db.commit()

    db.delete(db.query(Company).one())
    db.commit()

    job = db.get(Job, "manual:a")
    assert job is not None and job.company_id is None
    assert job.company == "Acme"


def test_deleting_a_company_removes_its_contacts(session_factory):
    db = session_factory()
    company = resolve_company(db, "Acme")
    db.add(HrContact(company_id=company.id, name="Nguyen A"))
    db.commit()

    db.delete(company)
    db.commit()
    assert db.query(HrContact).count() == 0
