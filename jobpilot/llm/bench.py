"""Measuring a backend against a known answer, instead of arguing about it.

Phase 20 compared two backends by driving five emails with known labels and four
real jobs, then writing the result into a document. The numbers were good; the
method was a person doing it once. This is the same method as a command, so the
next backend can be judged the same way rather than on how it feels.

Three benchmarks, because the calls fail differently:

* **classify** has a right answer, so it is scored against one. The fixtures
  below are fictional employer mail — no real correspondence, for the same
  reason ``cv/sample.py`` is a made-up CV.
* **intake** also has a right answer, and the interesting half of it is the
  *blanks*. A model that fills every field looks better and is worse, so the
  fixtures below assert on fields the posting deliberately never states, and on
  the "similar jobs" panel whose salaries belong to other postings entirely.
* **tailor** has no single right answer; a plan can be good or bad without being
  wrong. What it has is a *floor*: the guardrails. So it is scored on how often
  the model clears the floor, and on whether it needs the corrective round to do
  it. Phase 20's local 7B scored 0/4 here — not on truthfulness, but on
  navigating the schema.

Neither writes anything. Bench runs cost money on a paid backend and produce
nothing but a number, which is the point.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jobpilot.crawler.mailbox import MailMessage

# --------------------------------------------------------------------------- #
# classify: five messages with known labels
# --------------------------------------------------------------------------- #
#: (message, expected verdict). Chosen to cover the distinctions that actually
#: get confused: an automated receipt is *not* a reply, and a rejection that
#: opens politely is still a rejection.
CLASSIFY_FIXTURES: list[tuple[MailMessage, str]] = [
    (
        MailMessage(
            uid="bench-1",
            subject="We received your application",
            sender="no-reply@acme-careers.example",
            date=None,
            html="",
            text=(
                "Thank you for applying to ACME. This is an automated confirmation "
                "that your application has been received. Please do not reply to "
                "this message."
            ),
        ),
        "auto_ack",
    ),
    (
        MailMessage(
            uid="bench-2",
            subject="Re: Backend Engineer application",
            sender="linh@acme.example",
            date=None,
            html="",
            text=(
                "Hi, thanks for getting in touch. I have passed your CV to the "
                "hiring manager and will come back to you next week."
            ),
        ),
        "replied",
    ),
    (
        MailMessage(
            uid="bench-3",
            subject="Technical interview — scheduling",
            sender="talent@acme.example",
            date=None,
            html="",
            text=(
                "We would like to invite you to a 60-minute technical interview. "
                "Are you available on Tuesday or Thursday afternoon?"
            ),
        ),
        "interview",
    ),
    (
        MailMessage(
            uid="bench-4",
            subject="Your application to ACME",
            sender="talent@acme.example",
            date=None,
            html="",
            text=(
                "Thank you for the time you spent with us. After careful "
                "consideration we have decided to move forward with another "
                "candidate for this position. We wish you the best."
            ),
        ),
        "rejected",
    ),
    (
        MailMessage(
            uid="bench-5",
            subject="Offer of employment — Backend Engineer",
            sender="hr@acme.example",
            date=None,
            html="",
            text=(
                "We are delighted to offer you the position of Backend Engineer. "
                "The formal offer letter is attached for your review."
            ),
        ),
        "offer",
    ),
]


# --------------------------------------------------------------------------- #
# intake: postings with known fields, and known blanks
# --------------------------------------------------------------------------- #
#: (label, pasted text, expected fields). Only the listed fields are checked, so
#: a case can assert on the two things it was written for without pinning the
#: seven it has no opinion about. ``""`` is an assertion like any other, and the
#: most important one here: the whole failure mode of this call is a model that
#: fills a blank in plausibly.
#:
#: Fictional employers throughout, same rule as ``cv/sample.py``.
INTAKE_FIXTURES: list[tuple[str, str, dict]] = [
    (
        # The trap that motivated the fixture: a "similar jobs" panel carrying
        # two other postings' salaries. Picking one of those up is the failure
        # that reads as success — a job row with a wrong, confident salary.
        "vi-with-similar-jobs-panel",
        """Senior Backend Engineer (Java/Spring Boot)
Fintech Sao Việt · Ho Chi Minh City, Vietnam · Hybrid

Mức lương: 40 - 60 triệu

Yêu cầu công việc
- Tối thiểu 5 năm kinh nghiệm phát triển backend với Java
- Thành thạo Spring Boot, Spring Cloud
- Kinh nghiệm với PostgreSQL, tối ưu truy vấn
- Tốt nghiệp Đại học chuyên ngành CNTT

Ứng tuyển: gửi CV về tuyendung@saoviet.example

Việc làm tương tự
- Frontend Developer (ReactJS) - Công ty A - 25 - 35 triệu
- DevOps Engineer - Công ty B - 35 - 50 triệu""",
        {
            "salary": "40 - 60 triệu",
            "level": "senior",
            "apply_email": "tuyendung@saoviet.example",
            "language": "vi",
        },
    ),
    (
        # Nothing is stated: no pay, no seniority, no address to apply to. Every
        # expected value here is a blank, and a model that "helpfully" derives
        # `senior` from "5+ years" fails on purpose.
        "en-states-almost-nothing",
        """Backend Engineer — Northwind Data

We're looking for a backend engineer to join our platform team. You'll work on
our ingestion pipeline in Go, backed by ClickHouse.

What we're after: 5+ years building production services, comfort with
distributed systems, and an appetite for on-call.

Apply through the form on this page.""",
        {"salary": "", "level": "", "apply_email": "", "language": "en"},
    ),
    (
        # An internship, which the level vocabulary does hold — so here the
        # right answer is *not* a blank. A fixture set made only of blanks would
        # be passed by a model that returns nothing at all.
        "en-internship-with-stipend",
        """Software Engineering Intern (Summer)
Bluefin Labs · Da Nang · Internship

Stipend: 8,000,000 VND / month

You'll work alongside our backend team on internal tooling in Python.
Requirements: currently enrolled in a CS degree, familiar with Git.""",
        {"salary": "8,000,000 VND / month", "level": "intern", "language": "en"},
    ),
]


@dataclass
class BenchResult:
    task: str
    provider: str
    model: str
    total: int = 0
    correct: int = 0
    #: Only meaningful for tailor: accepted without a corrective round.
    first_try: int = 0
    failed: int = 0
    notes: list[str] = field(default_factory=list)


def resolve(task: str, provider: str = "", model: str = ""):
    """The client to benchmark: the configured one, or an explicit override.

    Overrides exist so that sweeping candidate models is a loop rather than a
    sequence of config edits. "Which is the cheapest model that still works" is
    a question with a numeric answer, and asking it should not cost a commit.
    """
    from jobpilot.config import get_config
    from jobpilot.llm.registry import api_key, provider_for

    cfg = get_config().llm
    name = provider or cfg.for_task(task)  # type: ignore[arg-type]
    entry = provider_for(name)
    chosen = model or (cfg.model_for(task) if not provider else entry.default_model)  # type: ignore[arg-type]
    return entry.build(chosen, api_key(name), task), name


def bench_classify(limit: int = 0, provider: str = "", model: str = "") -> BenchResult:
    """Score a classifier against the fixtures above."""
    from jobpilot.apply.inbox import Applied, ModelClassifier, check_verdict
    from jobpilot.tailor.engine import TailorError

    client, name = resolve("classify", provider, model)
    result = BenchResult(task="classify", provider=name, model=client.model)
    engine = ModelClassifier(client)
    app = Applied(0, "bench:1", "ACME", "Backend Engineer")

    cases = CLASSIFY_FIXTURES[: limit or len(CLASSIFY_FIXTURES)]
    for mail, expected in cases:
        result.total += 1
        try:
            verdict = engine.classify(mail, app)
        except TailorError as exc:
            result.failed += 1
            result.notes.append(f"{mail.uid}: call failed - {exc}")
            continue
        if verdict.verdict == expected:
            result.correct += 1
        else:
            result.notes.append(f"{mail.uid}: expected {expected}, got {verdict.verdict}")
        # The quote guard runs outside the engine in production, so it runs here
        # too — a right label with an invented quote is dropped in real use and
        # should not score as a win.
        problems = check_verdict(verdict, mail)
        if problems:
            result.notes.append(f"{mail.uid}: verdict would be dropped - {'; '.join(problems)}")
    return result


def bench_intake(limit: int = 0, provider: str = "", model: str = "") -> BenchResult:
    """Score an extractor on the fixtures above, field by field.

    ``total`` counts *fields checked*, not postings, so three cases asserting
    four fields each is a score out of eleven rather than out of three. A model
    that gets the salary right and invents a seniority should not read as 2/3.

    Comparison is case-insensitive and whitespace-collapsed but otherwise exact:
    the contract is that the model copies what the posting says, so "40-60
    triệu" for "40 - 60 triệu" counts, and "up to 60 million VND" does not.
    """
    from jobpilot.intake.engine import IntakeError, ModelIntakeEngine
    from jobpilot.intake.service import clean_paste

    client, name = resolve("intake", provider, model)
    result = BenchResult(task="intake", provider=name, model=client.model)
    engine = ModelIntakeEngine(client)

    cases = INTAKE_FIXTURES[: limit or len(INTAKE_FIXTURES)]
    for label, text, expected in cases:
        try:
            got = engine.extract(clean_paste(text))
        except IntakeError as exc:
            result.failed += 1
            result.total += len(expected)
            result.notes.append(f"{label}: call failed - {exc}")
            continue
        for field_name, want in expected.items():
            result.total += 1
            have = getattr(got, field_name, "")
            if _same(have, want):
                result.correct += 1
            else:
                # Blanks get their own wording. "expected '', got 'senior'" is
                # the finding this benchmark exists for, and it deserves to read
                # as invention rather than as a near miss.
                result.notes.append(
                    f"{label}.{field_name}: invented {have!r} - the posting never says"
                    if want == ""
                    else f"{label}.{field_name}: expected {want!r}, got {have!r}"
                )
    return result


def _same(have: str, want: str) -> bool:
    return " ".join(str(have).split()).casefold() == " ".join(want.split()).casefold()


def bench_tailor(db, limit: int = 4, provider: str = "", model: str = "") -> BenchResult:
    """Run the configured tailor over real jobs and score it on the guardrails.

    Real jobs and the real Master CV, because a benchmark on fixtures measures
    the fixtures. Nothing is written: no version row, no PDF.
    """
    from sqlalchemy import select

    from jobpilot.cv.store import MASTER_SCOPE, get_document
    from jobpilot.store.models import Job
    from jobpilot.tailor.engine import ModelTailorEngine, TailorError
    from jobpilot.tailor.guard import GuardrailViolation

    client, name = resolve("tailor", provider, model)
    result = BenchResult(task="tailor", provider=name, model=client.model)

    master = get_document(db, MASTER_SCOPE)
    jobs = [
        job
        for job in db.execute(select(Job).order_by(Job.crawled_at.desc()).limit(limit * 5))
        .scalars()
        .all()
        if (job.payload or {}).get("description_md")
    ][:limit]

    if not jobs:
        result.notes.append("no crawled jobs with a description - run a crawl first")
        return result

    engine = ModelTailorEngine(client)
    for job in jobs:
        result.total += 1
        try:
            outcome = engine.tailor(master, job)
        except GuardrailViolation as exc:
            result.failed += 1
            result.notes.append(f"{job.id}: guardrail - {exc}")
            continue
        except TailorError as exc:
            result.failed += 1
            result.notes.append(f"{job.id}: call failed - {exc}")
            continue
        result.correct += 1
        if outcome.attempts == 1:
            result.first_try += 1
        else:
            result.notes.append(f"{job.id}: needed a retry - {'; '.join(outcome.retried_for)}")
    return result
