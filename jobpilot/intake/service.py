"""Reading a pasted posting, and scoring a saved one against the Master CV.

Neither function runs on the task queue, which is a departure from every other
LLM call in the app, so the reasoning is worth writing down.

``tailor`` and ``apply`` were moved off the request path in Phase 10 because
they are a model call *plus* a LaTeX build — tens of seconds to minutes, with a
PDF at the end that the user watches for. These two are one structured call
each, and the user is sitting in front of a form waiting to type. Queueing them
would make the paste flow unusable in the ordinary case, because the queue is a
single worker: a crawl kicked off five minutes ago would leave "read this JD"
sitting in ``queued`` behind it. Being merely slow beats being blocked.

Both are defined as plain ``def`` route handlers upstream, so FastAPI runs them
in its threadpool and a slow provider cannot stall the event loop.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from jobpilot.config import get_config
from jobpilot.crawler.normalize import enrich, parse_work_mode
from jobpilot.crawler.quality import describe
from jobpilot.crawler.text import html_to_markdown
from jobpilot.cv import importer as uploads
from jobpilot.cv import store as cv_store
from jobpilot.cv.schema import CvDocument
from jobpilot.intake.engine import IntakeEngine, IntakeError
from jobpilot.intake.prompt import MAX_JD_CHARS
from jobpilot.intake.schema import FitReport, JdExtract, JdSections
from jobpilot.store.models import Job
from jobpilot.timeutil import vn_now


log = logging.getLogger(__name__)


class IntakeRefused(RuntimeError):
    """The paste, or the job, is not something intake can work with."""


#: Enough of a tag soup to be worth running through the HTML converter. Two
#: signals rather than one ``<``: a JD that says "if x < 10" is not HTML, and
#: converting it would strip the rest of the sentence as an unclosed tag.
_HTML_RE = re.compile(r"<(p|div|br|ul|ol|li|h[1-6]|span|strong|em|table)\b[^>]*>", re.I)

#: Runs of whitespace *within* a line, and non-breaking spaces. Deliberately not
#: ``\s`` — that would match the newline this function is preserving, and the
#: leading indent it is preserving too.
_INLINE_WS = re.compile(r"[^\S\n]+")

#: Cap on indentation carried through. Deep indents come from HTML pasted as
#: text, where a bullet can sit forty columns in; past four levels the nesting
#: is an artefact of the page layout rather than a claim about the content.
_MAX_INDENT = 8


def _tidy_line(line: str) -> str:
    """Collapse runs of spaces inside one line, keeping its indent."""
    body = _INLINE_WS.sub(" ", line.replace("\xa0", " ").expandtabs(4)).strip()
    if not body:
        return ""
    indent = len(line.expandtabs(4)) - len(line.expandtabs(4).lstrip())
    return " " * min(indent, _MAX_INDENT) + body


@dataclass(frozen=True)
class IntakeResult:
    """What one paste yielded, before anything is saved."""

    extract: JdExtract
    #: The posting's body, sorted into buckets. Its entries are the posting's own
    #: lines — a table of contents over ``description_md``, not a replacement for
    #: it, which is why both are stored.
    sections: JdSections
    #: The posting text as it will be stored — the user's paste, converted from
    #: HTML if they pasted HTML, and otherwise exactly theirs. Never the model's.
    description_md: str
    #: Quality flags computed the same way a crawled job's are, so "thin JD"
    #: means the same thing here as it does on any other job.
    flags: list[str]
    #: One actionable line per flag, ready to render.
    notes: list[str]
    #: Province/city, canonicalised through the same table the crawler uses, so
    #: a pasted job lands in the same Market bar as a crawled one.
    city: str | None
    #: onsite / hybrid / remote, or None when nobody said.
    work_mode: str | None


def clean_paste(text: str) -> str:
    """The pasted blob as storable markdown.

    Copying from a rendered page usually yields plain text; copying from
    devtools, an email client, or a "view source" yields HTML. Both are ordinary
    things for a person to do, so both are handled — and neither is rewritten.

    Plain text is tidied **per line**, not with ``clean_text``: that function
    collapses every run of whitespace including newlines, which is right for a
    title or a location and destructive for a body. A JD is mostly a list of
    bullets, and flattening it into one paragraph would hand the tailor a wall
    of text where the posting had structure.

    Leading whitespace survives for the same reason one step down. A posting
    that nests "Spring Boot" and "JPA" under "Java" is saying something about
    how those relate, and ``clean_text`` on each line would strip the indent and
    leave four siblings — the structure gone, silently, in the field that every
    later step reads as evidence.
    """
    if _HTML_RE.search(text):
        return html_to_markdown(text)
    lines = [_tidy_line(line) for line in text.replace("\r\n", "\n").split("\n")]
    # Collapse runs of blank lines to one: pasting from a rendered page tends to
    # leave three or four between sections, and a blank line is a paragraph
    # break whether there is one of them or five.
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()


#: A PDF page carrying less text than this is not a page of a posting: a scan
#: with a stamped page number, an export that kept only its footer — or a page
#: that is one big picture, which is how a poster arrives. Counted **per page**:
#: here the layer *replaces* a reading, so a page of caption next to a page of
#: poster must not pass as the whole posting on the strength of the caption.
#: Below the floor the model reads the upload instead.
_MIN_LAYER_CHARS = 200

_NOT_A_FILE_HINT = "a posting that is already text is pasted straight into the box"


@dataclass
class FileReading:
    """The text of a posting that arrived as a picture or a PDF. Not saved."""

    text: str
    #: True when a model typed the text out of the file. False when it is the
    #: PDF's own text layer — the publisher's words, with no model in between.
    #: The form says which, because only one of them needs proof-reading.
    transcribed: bool
    #: The model's own notes on what it could not read. Empty for a text layer.
    unreadable: list[str]
    #: What was actually sent, after sniffing: name, media type, size.
    files: list[dict]


def read_files(files: list[tuple[str, bytes]], engine: IntakeEngine) -> FileReading:
    """Get the text out of an uploaded posting. Writes nothing, reads no fields.

    Only the text. Title, company and salary are then read from it by the same
    ``extract_jd`` a paste goes through, so a job added from a screenshot and
    one added from a paste differ in nothing but where their text came from —
    and the text passes through the form, where the user can hold it against
    the picture, before it is ever stored.

    A PDF that carries real text on every page is not shown to a model at all:
    the layer is the publisher's own words. What the layer cannot carry is text
    drawn *inside* a picture on such a page — the form says so beside the box.
    """
    try:
        attachments = uploads.load_files(files, text_hint=_NOT_A_FILE_HINT)
    except uploads.CvImportRefused as exc:
        raise IntakeRefused(str(exc)) from exc
    sent = [{"name": a.name, "media_type": a.media_type, "bytes": len(a.data)} for a in attachments]

    layer = uploads.text_layer(attachments)
    if layer is not None and all(
        len(page.strip()) >= _MIN_LAYER_CHARS for page in uploads.pages_of(layer)
    ):
        text, transcribed, unreadable = uploads.plain_text(layer), False, []
    else:
        transcript = engine.transcribe(attachments)
        text = uploads.plain_text(transcript.text)
        transcribed = True
        unreadable = [note.strip() for note in transcript.unreadable if note.strip()]
        if not text:
            # A photo of something else, a blank scan. An empty box that looks
            # like a result would be the worse answer.
            raise IntakeRefused(
                "no job posting could be read in this upload"
                + (f" — {'; '.join(unreadable)}" if unreadable else "")
            )
    if len(text) > MAX_JD_CHARS:
        raise IntakeRefused(
            f"that upload reads as {len(text):,} characters; postings are a few thousand. "
            f"Upload the job description itself (limit {MAX_JD_CHARS:,})."
        )
    return FileReading(text=text, transcribed=transcribed, unreadable=unreadable, files=sent)


def extract_jd(text: str, engine: IntakeEngine, url: str = "") -> IntakeResult:
    """Read a pasted posting into fields. Writes nothing.

    The description that comes back is the user's own text, not the model's:
    every guardrail downstream — the tailor's requirement list, the fit report,
    the cover letter — reads that field as *the evidence*, and a model's retelling
    of a posting would become evidence of itself.
    """
    body = clean_paste(text)
    if not body.strip():
        raise IntakeRefused("nothing to read — paste the job description first")
    if len(body) > MAX_JD_CHARS:
        raise IntakeRefused(
            f"that paste is {len(body):,} characters; postings are a few thousand. "
            f"Trim it to the job description itself (limit {MAX_JD_CHARS:,})."
        )

    # Concurrent, not sequential. They are two independent reads of one text, so
    # running them back to back would double the wait the user sits through for
    # no benefit — measured, the pair costs about what the slower one costs
    # alone. Two threads rather than asyncio because the provider SDKs are
    # blocking and the route is already running in FastAPI's threadpool.
    with ThreadPoolExecutor(max_workers=2) as pool:
        extract_call = pool.submit(engine.extract, body, url)
        sections_call = pool.submit(engine.sections, body)
        # The fields are the point of this call — without them there is no form
        # to fill — so `extract` failing fails the request. `result()` re-raises
        # in this thread, so it still reaches the route as an IntakeError.
        extract = extract_call.result()
        try:
            sections = sections_call.result()
        except IntakeError:
            # The buckets are a convenience over text the user already has, and
            # `JdSections` is the larger schema of the two — the one a provider
            # is likelier to refuse. Failing the whole paste over it would throw
            # away a good `extract` the user has already paid for and leave them
            # with nothing. Empty sections render as "no structured view", which
            # is exactly what happened.
            log.warning("intake: sections read failed, returning fields only", exc_info=True)
            sections = JdSections(
                role="",
                responsibilities=[],
                must_have=[],
                nice_to_have=[],
                soft_skills=[],
                outputs=[],
                benefits=[],
                how_to_apply="",
            )

    cfg = get_config()
    # The flags come from the same function the crawler uses rather than from the
    # model. "Is this JD too thin to tailor against" is a character count with a
    # threshold the rest of the app already agrees on (`THIN_JD_CHARS`); asking a
    # model would buy a second, disagreeing answer to a question arithmetic
    # settles. The model is asked only about things arithmetic cannot see, which
    # is what `FitReport.concerns` is for.
    signals = enrich(
        cfg=cfg,
        title=extract.title,
        location=extract.location,
        salary=extract.salary,
        level=extract.level or None,
        skills=extract.skills,
        description_md=body,
        posted_at=None,
    )
    # `undated` is dropped from the preview, and only from the preview. It is a
    # true statement about the paste — nobody knows when this was published — but
    # `create_job` stamps `posted_at = now` the moment the user saves, so showing
    # it here warns about a condition the very next click removes. A chip that
    # every paste raises and every save clears teaches the user to ignore the
    # chips, which is expensive for the ones that mean something (`thin_jd`).
    flags = [f for f in signals.payload["quality"]["flags"] if f != "undated"]
    return IntakeResult(
        extract=extract,
        sections=sections,
        description_md=body,
        flags=flags,
        notes=[describe(flag) for flag in flags],
        # From the facets `enrich` already computed, not a second lookup — the
        # Market page reads that same field, and two ways of deciding a job's
        # province is one more than there should be.
        city=signals.payload.get("city"),
        # The model's answer wins when it gave one: it read the whole posting,
        # while the fallback only reads the location label. The fallback still
        # matters — "(Hybrid)" lives in that label on every LinkedIn job.
        work_mode=extract.work_mode or parse_work_mode(extract.location),
    )


#: How much text a CV must carry before it is worth assessing against.
#:
#: Measured from the skeleton rather than typed as a number. The empty document
#: is not zero characters — its section titles ("Summary", "Work Experience")
#: are scaffolding the bootstrap writes, and they came to 200 exactly, which a
#: hand-picked 200 would have sat right on top of. Deriving it means a skeleton
#: that gains a section moves the floor with it instead of quietly falling below
#: a constant nobody re-measured.
#:
#: The margin only has to separate "nothing" from "something": the sample CV
#: scores ~2,900. It is not a judgement about whether a CV is good enough.
def _empty_cv_chars() -> int:
    from jobpilot.cv.skeleton import empty_document

    return cv_content_chars(empty_document())


def cv_content_chars(doc: CvDocument) -> int:
    """How much text the document actually carries, ignoring its structure.

    Walks the dumped model rather than each section type by hand. A hand-written
    walk would need editing every time a section type is added, and the failure
    of the version that forgot to would be this guard quietly deciding a full CV
    was empty.
    """
    def walk(node) -> int:
        if isinstance(node, str):
            return len(node.strip())
        if isinstance(node, dict):
            return sum(walk(v) for v in node.values())
        if isinstance(node, list):
            return sum(walk(v) for v in node)
        return 0

    return walk(doc.model_dump(mode="json"))


#: Anything at or below the skeleton plus this much is still an unfilled CV.
EMPTY_CV_MARGIN = 100


def cv_is_unfilled(doc: CvDocument) -> bool:
    """True when the Master CV is still the bootstrap skeleton, or nearly."""
    return cv_content_chars(doc) <= _empty_cv_chars() + EMPTY_CV_MARGIN


@dataclass(frozen=True)
class FitOutcome:
    """A fit report and when it was made.

    The timestamp is part of the answer, not decoration: the report judges a CV
    that the user goes on to edit, so "assessed before or after I added that
    project" is the question that decides whether to trust it.
    """

    report: FitReport
    assessed_at: datetime


def assess_fit(db: Session, job_id: str, engine: IntakeEngine) -> FitOutcome:
    """Score a saved job against the Master CV and record the answer on the job.

    Stored under ``payload["fit"]`` rather than in a column: it is one advisory
    reading that gets replaced wholesale when re-run, never queried across jobs,
    and adding a column for it would mean a migration for something no ``WHERE``
    clause will ever mention.
    """
    job = db.get(Job, job_id)
    if job is None:
        raise IntakeRefused(f"job {job_id!r} not found")

    description = (job.payload or {}).get("description_md") or ""
    if not description.strip():
        raise IntakeRefused(
            "this job has no description yet — paste one in before asking how well it fits"
        )

    master = cv_store.get_document(db, cv_store.MASTER_SCOPE)
    if cv_is_unfilled(master):
        # A fresh database bootstraps an *empty* Master CV (`cv/skeleton.py`), and
        # sending that outline would come back "weak, 0%" — a confident verdict
        # about someone's career when the true answer is "you have not filled in
        # your CV yet". Refusing costs nothing; the alternative is a paid call
        # that produces a discouraging lie. "Don't know" is not "bad".
        raise IntakeRefused(
            "your Master CV is still empty — fill it in under CV Studio (or "
            "`jobpilot cv import`) before asking how well it fits a job"
        )
    report = engine.assess(master, job)

    assessed_at = vn_now()
    job.payload = {
        **(job.payload or {}),
        "fit": {**report.model_dump(mode="json"), "assessed_at": assessed_at.isoformat()},
    }
    # Deliberately not touching `job.match_score`. That column is the crawler's
    # stack-coverage number, which the Jobs list sorts by and every crawled job
    # also has; overwriting it for the handful of jobs that have been assessed
    # would sort two different measurements against each other in one column.
    # The tailor is the one thing allowed to set it, because a tailor round
    # produces the same measurement for every job that reaches it.
    db.commit()
    db.refresh(job)
    return FitOutcome(report=report, assessed_at=assessed_at)
