"""Importing a CV from page images or a PDF.

Three layers, each tested where it can fail on its own: how a file reaches each
provider (four wire shapes, no network), what the importer does with a reading
(validation, shaping, the one mechanical check), and the endpoint (which must
save nothing). No test here reads a real CV — the reading is the fictional
``cv/sample.py`` person, typed in as the model would return it.
"""

from __future__ import annotations

import base64
import json
import subprocess

import pytest

from jobpilot.api.main import app
from jobpilot.api.deps import get_db
from jobpilot.api.routes.cv import get_reader
from jobpilot.config import get_secrets
from jobpilot.cv import importer
from jobpilot.cv import store as cv_store
from jobpilot.cv.reader import (
    CvRead,
    CvReadError,
    FixtureCvReader,
    ModelCvReader,
    ReadBullet,
    ReadEducation,
    ReadEntry,
    ReadHeader,
    ReadHeadings,
    ReadSection,
)
from jobpilot.cv.sample import sample_document
from jobpilot.cv.schema import BulletsSection, CvDocument, Theme
from jobpilot.llm.base import Attachment, Completion, LlmError, Usage
from jobpilot.tests.conftest import api_client

AUTH = {"X-API-Token": get_secrets().jobpilot_api_token}

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 16
#: What an iPhone hands over by default — an ISO-BMFF box, not one of the four.
HEIC = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32


def text_pdf(*lines: str, pages: int = 1) -> bytes:
    """A real, minimal PDF whose text layer says ``lines`` (on every page).

    Built by hand with correct xref offsets, so both extractors read it the way
    they read a CV exported from a word processor — no LaTeX engine in the test.
    """
    body = "BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(f"({line}) Tj T*" for line in lines) + " ET"
    stream = body.encode("latin-1")
    kids = " ".join(f"{3 + 2 * n} 0 R" for n in range(pages))
    font = 3 + 2 * pages
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode(),
    ]
    for n in range(pages):
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * n} 0 R "
            f"/Resources << /Font << /F1 {font} 0 R >> >> >>".encode()
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def reading(**overrides) -> CvRead:
    """The fictional sample person, as a model would transcribe them."""
    fields = dict(
        header=ReadHeader(
            first_name="Alex",
            last_name="Example",
            position="Fresher Software Engineer",
            address="",
            mobile="(+84) 900 000 000",
            email="alex@example.com",
            homepage="",
            github="alex-example",
            linkedin="",
        ),
        headings=ReadHeadings(
            summary="Summary",
            education="Education",
            experience="Work Experience",
            projects="",
            skills="Skills",
        ),
        order=["summary", "experience", "education", "other", "skills"],
        summary="Software Engineer focused on backend development.",
        education=[
            ReadEducation(
                degree="Bachelor's, Software Engineering",
                institution="Example University",
                location="Ho Chi Minh, Viet Nam",
                date="Oct. 2022 -- Apr. 2026",
                items=["Current GPA: 3.5/4.0.", "  "],
            )
        ],
        experience=[
            ReadEntry(
                title="Example Software, Junior Software Engineer - Backend",
                date="Dec. 2024 -- Present",
                url="",
                role="",
                tech_stack=["Java", "Spring Boot", ""],
                items=["Wrote unit tests with JUnit, achieving over 80% code coverage."],
            )
        ],
        projects=[],
        skills=[ReadBullet(label="Languages", text="Java, Python", date="")],
        other=[
            ReadSection(
                title="Honors & Awards",
                items=[ReadBullet(label="", text="Solved 300+ LeetCode Problems", date="2024")],
            )
        ],
        unreadable=[],
    )
    fields.update(overrides)
    return CvRead(**fields)


#: A text layer that states everything ``reading()`` does.
LAYER = (
    "Alex Example Fresher Software Engineer (+84) 900 000 000 alex@example.com "
    "Summary Software Engineer focused on backend development. "
    "Work Experience Example Software, Junior Software Engineer - Backend Dec. 2024 -- Present "
    "Wrote unit tests with JUnit, achieving over 80% code coverage. Java Spring Boot "
    "Education Bachelor's, Software Engineering Example University Ho Chi Minh, Viet Nam "
    "Oct. 2022 -- Apr. 2026 Current GPA: 3.5/4.0. "
    "Honors & Awards Solved 300+ LeetCode Problems 2024 Skills Languages Java, Python"
)


# --------------------------------------------------------------------------- #
# How a file reaches each provider
# --------------------------------------------------------------------------- #
IMAGE = Attachment(media_type="image/png", data=PNG, name="page-1.png")
PDF = Attachment(media_type="application/pdf", data=b"%PDF-1.4 x", name="")
TURN = {"role": "user", "content": "Transcribe this.", "attachments": [IMAGE, PDF]}


def test_claude_gets_an_image_block_and_a_document_block_ahead_of_the_text():
    from jobpilot.llm.claude import wire_message

    content = wire_message(TURN)["content"]
    assert [b["type"] for b in content] == ["image", "document", "text"]
    assert content[0]["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": base64.b64encode(PNG).decode(),
    }
    assert content[1]["source"]["media_type"] == "application/pdf"
    assert content[2]["text"] == "Transcribe this."


def test_a_text_only_turn_is_sent_to_claude_exactly_as_before():
    from jobpilot.llm.claude import wire_message

    assert wire_message({"role": "assistant", "content": "{}"}) == {
        "role": "assistant",
        "content": "{}",
    }


def test_the_neutral_attachments_key_never_reaches_an_sdk():
    """Each SDK validates its own turn shape; an unknown key is a 400, or worse,
    a field quietly ignored along with the file it carried."""
    from jobpilot.llm import claude, gemini, openai

    for wired in (claude.wire_message(TURN), openai.wire_message(TURN), gemini._turn(TURN)):
        assert "attachments" not in wired


def test_openai_gets_a_data_uri_image_and_a_named_pdf_file_part():
    from jobpilot.llm.openai import wire_message

    image, pdf, text = wire_message(TURN)["content"]
    assert image["type"] == "image_url"
    assert image["image_url"]["url"] == "data:image/png;base64," + base64.b64encode(PNG).decode()
    # A `file` part with no filename is rejected, so a nameless upload gets one.
    assert pdf["type"] == "file" and pdf["file"]["filename"] == "cv.pdf"
    assert pdf["file"]["file_data"].startswith("data:application/pdf;base64,")
    assert text == {"type": "text", "text": "Transcribe this."}


def test_gemini_gets_raw_bytes_not_base64():
    """The SDK encodes ``inline_data`` itself — a pre-encoded string would be
    encoded twice and arrive as a file of base64 text."""
    from jobpilot.llm.gemini import _turn

    turn = _turn(TURN)
    assert turn["role"] == "user"
    assert turn["parts"][0] == {"inline_data": {"mime_type": "image/png", "data": PNG}}
    assert turn["parts"][-1] == {"text": "Transcribe this."}


class _StreamRun:
    """Stands in for ``subprocess.run`` on a stream-json call."""

    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode
        self.calls: list[dict] = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": argv, **kwargs})
        return subprocess.CompletedProcess(argv, self.returncode, stdout=self.stdout, stderr="")


def _stream(structured: dict) -> str:
    events = [
        {"type": "system", "subtype": "init"},
        {"type": "assistant", "message": {"content": []}},
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "structured_output": structured,
            "usage": {"input_tokens": 2867, "output_tokens": 306},
        },
    ]
    # A line that is not JSON at all: the answer two lines later still counts.
    return "\n".join(["warning: something unrelated", *(json.dumps(e) for e in events)]) + "\n"


def test_the_claude_cli_sends_files_as_one_stream_json_user_message():
    from jobpilot.llm.claude_cli import ClaudeCliClient

    run = _StreamRun(_stream(reading().model_dump()))
    done = ClaudeCliClient(model="claude-haiku-4-5", runner=run).structured(
        system="You transcribe.", messages=[TURN], schema=CvRead
    )

    argv = run.calls[0]["argv"]
    # stream-json in drags stream-json out and --verbose with it; the plain
    # `--output-format json` of a text call must not also be there.
    assert argv[argv.index("--input-format") + 1] == "stream-json"
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in argv and argv.count("--output-format") == 1
    # The hardening flags of the text path are all still on.
    assert "--no-session-persistence" in argv and argv[argv.index("--tools") + 1] == ""

    stdin = run.calls[0]["input"]
    assert stdin.endswith("\n") and stdin.count("\n") == 1
    message = json.loads(stdin)
    assert message["type"] == "user"
    blocks = message["message"]["content"]
    assert [b["type"] for b in blocks] == ["image", "document", "text"]
    assert blocks[-1]["text"] == "Transcribe this."
    # The file is on stdin only: argv is readable by every process on the machine.
    assert base64.b64encode(PNG).decode() not in " ".join(argv)

    assert done.value.header.email == "alex@example.com"
    assert done.usage.input_tokens == 2867 and done.usage.cost_usd == 0.0


def test_a_stream_with_no_result_event_is_an_error_not_an_empty_answer():
    from jobpilot.llm.claude_cli import ClaudeCliClient

    run = _StreamRun(json.dumps({"type": "system", "subtype": "init"}) + "\n", returncode=1)
    with pytest.raises(LlmError, match="claude CLI failed"):
        ClaudeCliClient(runner=run).structured(system="s", messages=[TURN], schema=CvRead)


def test_a_failed_stream_does_not_quote_the_document_into_the_error():
    """The last event of a dead stream is often the assistant turn, which quotes
    the CV back. That tail must not reach `llm_calls.error` or a 502 body."""
    from jobpilot.llm.claude_cli import ClaudeCliClient

    event = {"type": "assistant", "message": {"content": [{"text": "Alex Example, (+84) 900"}]}}
    run = _StreamRun(json.dumps(event) + "\n", returncode=1)
    with pytest.raises(LlmError) as caught:
        ClaudeCliClient(runner=run).structured(system="s", messages=[TURN], schema=CvRead)
    assert "Alex Example" not in str(caught.value) and "no output" in str(caught.value)


def test_a_cli_retry_carries_the_file_once_and_the_transcript_as_text():
    from jobpilot.llm.claude_cli import _stream_input

    blocks = json.loads(
        _stream_input(
            [
                {"role": "user", "content": "Transcribe.", "attachments": [IMAGE]},
                {"role": "assistant", "content": "{...}"},
                {"role": "user", "content": "Fix the date."},
            ]
        )
    )["message"]["content"]
    assert [b["type"] for b in blocks] == ["image", "text"]
    assert "Fix the date." in blocks[1]["text"] and "<assistant>" in blocks[1]["text"]


# --------------------------------------------------------------------------- #
# What is accepted as an upload
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("data", "kind"),
    [(PNG, "image/png"), (JPEG, "image/jpeg"), (WEBP, "image/webp"), (b"%PDF-1.7\n", "application/pdf")],
)
def test_the_type_is_read_from_the_bytes(data, kind):
    assert importer.sniff(data) == kind


def test_a_pdf_whose_header_is_not_the_first_byte_is_still_a_pdf():
    """The spec allows it anywhere in the first 1024 bytes; exporters use that."""
    assert importer.sniff(b"\xef\xbb\xbf%PDF-1.7\n") == "application/pdf"
    assert importer.sniff(b"\n%PDF-1.4\n") == "application/pdf"
    assert importer.sniff(b"x" * 2000 + b"%PDF-1.4") is None


def test_a_wrong_extension_does_not_change_what_the_provider_is_told():
    (attachment,) = importer.load_files([("scan.png", JPEG)])
    assert attachment.media_type == "image/jpeg"


def test_a_heic_photo_is_refused_by_name_before_any_model_is_asked():
    reader = FixtureCvReader(answer=reading())
    with pytest.raises(importer.CvImportRefused, match="IMG_0042.heic is not a PNG, JPEG"):
        importer.import_cv([("IMG_0042.heic", HEIC)], reader, CvDocument())
    assert reader.calls == []


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ([], "no file was uploaded"),
        ([("a.png", b"")], "a.png is empty"),
        ([("p.png", PNG)] * (importer.MAX_FILES + 1), "at most 6 files"),
        ([("big.png", PNG + b"\x00" * importer.MAX_IMAGE_BYTES)], "big.png is 3.5 MB"),
    ],
)
def test_an_upload_no_provider_would_take_is_refused_with_its_reason(files, message):
    with pytest.raises(importer.CvImportRefused, match=message):
        importer.load_files(files)


def test_a_pdf_gets_a_larger_allowance_than_an_image():
    padded = text_pdf("x") + b"\n" + b"%" * importer.MAX_IMAGE_BYTES
    (attachment,) = importer.load_files([("cv.pdf", padded)])
    assert attachment.is_pdf


def test_a_book_is_not_a_cv():
    with pytest.raises(importer.CvImportRefused, match="has 11 pages"):
        importer.load_files([("thesis.pdf", text_pdf("x", pages=11))])


def test_a_pdf_whose_pages_cannot_be_counted_is_left_to_the_provider():
    """Unknown is not "too many" — only a count we actually have can refuse."""
    assert importer.pdf_pages(b"%PDF-1.4 not really") is None
    assert importer.load_files([("odd.pdf", b"%PDF-1.4 not really")])[0].is_pdf


# --------------------------------------------------------------------------- #
# CvRead -> CvDocument
# --------------------------------------------------------------------------- #
def test_the_draft_has_the_sections_the_cv_has_in_the_order_it_has_them():
    doc = importer.to_document(reading(), CvDocument())
    assert [(s.key, s.title) for s in doc.sections] == [
        ("summary", "Summary"),
        ("experience", "Work Experience"),
        ("education", "Education"),
        ("honors-awards", "Honors & Awards"),
        ("skills", "Skills"),
    ]
    # No Projects section: the CV has none, and an empty one would be an
    # invitation to fill it.
    assert "projects" not in {s.key for s in doc.sections}


def test_absent_means_none_and_blank_lines_are_dropped():
    doc = importer.to_document(reading(), CvDocument())
    assert doc.header.address is None and doc.header.linkedin is None
    assert doc.header.github == "alex-example"
    by_key = {s.key: s for s in doc.sections}
    assert by_key["education"].entries[0].items == ["Current GPA: 3.5/4.0."]
    entry = by_key["experience"].entries[0]
    assert entry.tech_stack == ["Java", "Spring Boot"]
    assert entry.url is None and entry.role is None
    assert by_key["skills"].items[0].label == "Languages"


@pytest.mark.parametrize(
    ("printed", "kept"),
    [
        ("alex.example.com", "alex.example.com"),
        ("https://alex.example.com/", "alex.example.com"),
        # The label a link was printed under is not an address.
        ("Portfolio", None),
        ("My personal site", None),
        ("", None),
    ],
)
def test_a_homepage_is_kept_only_when_an_address_was_printed(printed, kept):
    read = reading()
    read.header.homepage = printed
    assert importer.to_document(read, CvDocument()).header.homepage == kept


@pytest.mark.parametrize(
    "printed",
    [
        "alex-example",
        "github.com/alex-example",
        "https://github.com/alex-example/",
        "@alex-example",
        "https://github.com/alex-example?tab=repositories",
        "www.linkedin.com/in/alex-example/details/experience/",
        "in/alex-example",
        # Country subdomains: the address a CV printed in Vietnam carries.
        "https://vn.linkedin.com/in/alex-example/",
        "vn.linkedin.com/in/alex-example",
    ],
)
def test_a_profile_is_reduced_to_the_username_the_template_expects(printed):
    read = reading()
    read.header.github = read.header.linkedin = printed
    header = importer.to_document(read, CvDocument()).header
    assert header.github == header.linkedin == "alex-example"


@pytest.mark.parametrize(
    "printed",
    [
        "LinkedIn",
        "GitHub",
        "github.com/",
        "in",
        "My profile",
        "alex.example",
        "",
        # Not a person's slug: the first path segment is the *kind* of page.
        "www.linkedin.com/pub/alex/1/2/3",
        "linkedin.com/company/example",
        # Some other host entirely — its pieces are not a username.
        "https://example.com/alex",
    ],
)
def test_the_name_of_the_service_is_not_a_username(printed):
    """The homepage lesson, one field over: an icon with "LinkedIn" beside it
    would be linked as linkedin.com/in/LinkedIn — somebody else's page."""
    read = reading()
    read.header.github = read.header.linkedin = printed
    header = importer.to_document(read, CvDocument()).header
    assert header.github is None and header.linkedin is None


def test_the_base_lends_its_look_and_none_of_its_words():
    base = sample_document().model_copy(update={"template": "plain", "theme": Theme(color="#112233")})
    doc = importer.to_document(reading(education=[], experience=[], other=[]), base)
    assert doc.template == "plain" and doc.theme.color == "#112233"
    # The sample's portfolio link and its three projects are not in the reading.
    assert doc.header.extra_info is None
    assert [s.key for s in doc.sections] == ["summary", "skills"]


def test_a_vietnamese_heading_becomes_a_file_safe_key_and_stays_a_title():
    read = reading(
        other=[
            ReadSection(
                title="Chứng chỉ & Giải thưởng",
                items=[ReadBullet(label="", text="AWS Cloud Practitioner", date="2025")],
            ),
            ReadSection(
                title="Hoạt động",
                items=[ReadBullet(label="", text="Tình nguyện viên", date="")],
            ),
            # Same heading twice, and one that folds to nothing at all.
            ReadSection(title="Hoạt động", items=[ReadBullet(label="", text="Đ", date="")]),
            ReadSection(title="語学", items=[ReadBullet(label="", text="N2", date="")]),
            # A heading that collides with a named section's own key.
            ReadSection(title="Skills", items=[ReadBullet(label="", text="Git", date="")]),
            ReadSection(title="Empty", items=[ReadBullet(label="", text="  ", date="")]),
        ]
    )
    others = [
        s for s in importer.to_document(read, CvDocument()).sections if isinstance(s, BulletsSection)
    ]
    assert [(s.key, s.title) for s in others if s.key != "skills"] == [
        ("chung-chi-giai-thuong", "Chứng chỉ & Giải thưởng"),
        ("hoat-dong", "Hoạt động"),
        ("hoat-dong-2", "Hoạt động"),
        ("section", "語学"),
        ("skills-2", "Skills"),
    ]


def test_a_paragraph_filed_as_a_heading_does_not_become_a_file_name_that_long():
    read = reading(
        other=[
            ReadSection(
                title="Volunteer work and community activities " * 10,
                items=[ReadBullet(label="", text="Mentor", date="")],
            )
        ]
    )
    section = importer.to_document(read, CvDocument()).sections[-2]
    assert len(section.key) <= 40 and not section.key.endswith("-")
    assert section.title.startswith("Volunteer work")  # the title itself is left alone


def test_an_unheaded_section_gets_the_skeletons_title_and_a_made_up_order_is_ignored():
    read = reading(
        headings=ReadHeadings(summary="", education="", experience="", projects="", skills=""),
        order=["experience", "hobbies", "experience"],
    )
    doc = importer.to_document(read, CvDocument())
    # Stated first, then everything unplaced in the skeleton's order.
    assert [s.title for s in doc.sections] == [
        "Work Experience",
        "Summary",
        "Education",
        "Skills",
        "Honors & Awards",
    ]


def test_every_draft_is_a_document_the_app_can_store_and_render():
    from jobpilot.cv.render import render_document

    doc = importer.to_document(reading(), CvDocument())
    assert CvDocument.model_validate(doc.model_dump(mode="json")) == doc
    files = render_document(doc)
    assert "resume/honors-awards.tex" in files


# --------------------------------------------------------------------------- #
# The mechanical check: numbers against a PDF's own text
# --------------------------------------------------------------------------- #
def test_an_image_is_never_reported_as_checked():
    result = importer.import_cv([("scan.png", PNG)], FixtureCvReader(answer=reading()), CvDocument())
    assert result.checked is False and result.unbacked_numbers == []
    assert result.files == [{"name": "scan.png", "media_type": "image/png", "bytes": len(PNG)}]


def test_a_pdf_with_a_text_layer_backs_every_number_in_a_faithful_reading():
    pdf = text_pdf(*LAYER.split("  "))
    result = importer.import_cv([("cv.pdf", pdf)], FixtureCvReader(answer=reading()), CvDocument())
    assert result.checked is True
    assert result.unbacked_numbers == []


def test_a_number_the_pdf_never_states_is_reported_and_the_draft_is_left_alone():
    """Reported, not corrected: extraction has failures of its own, and the
    person holding the original is the one who can tell which side is wrong."""
    misread = reading()
    misread.experience[0].items[0] = "Wrote unit tests with JUnit, achieving over 90% code coverage."
    misread.education[0].date = "Oct. 2022 -- Apr. 2027"
    result = importer.import_cv(
        [("cv.pdf", text_pdf(LAYER))], FixtureCvReader(answer=misread), CvDocument()
    )
    assert result.checked is True
    assert result.unbacked_numbers == ["90", "2027"]
    text = importer._draft_text(result.document)
    assert "over 90% code coverage" in text and "Apr. 2027" in text


def test_the_phone_number_is_checked_too():
    """Unlike the tailor's number guard, which skips the header: there the digits
    of a phone number are not a claim about the work; here they are a
    transcription like any other, and a wrong digit loses the callback."""
    misread = reading()
    misread.header.mobile = "(+84) 900 000 001"
    result = importer.import_cv(
        [("cv.pdf", text_pdf(LAYER))], FixtureCvReader(answer=misread), CvDocument()
    )
    assert result.unbacked_numbers == ["001"]


def test_a_scanned_pdf_has_no_layer_worth_checking_against():
    """A page number stamped on a scan is a text layer. Comparing against it
    would flag every number on the CV — a finding the tool made up."""
    result = importer.import_cv(
        [("scan.pdf", text_pdf("Page 1"))], FixtureCvReader(answer=reading()), CvDocument()
    )
    assert result.checked is False and result.unbacked_numbers == []


def test_a_pdf_plus_a_photo_is_not_checked_at_all():
    """The layer would cover one file and every number from the other would look
    invented — so a mixed upload is 'unchecked', not 'half checked'."""
    files = [Attachment("application/pdf", text_pdf(LAYER)), IMAGE]
    assert importer.text_layer(files) is None
    assert importer.text_layer([IMAGE]) is None


def test_a_text_pdf_plus_a_scanned_one_is_not_checked():
    """Measured in review: the share threshold is on the total, so a real layer
    plus a blank scan cleared it and seven real numbers were reported missing —
    the made-up finding this module says it does not make."""
    files = [Attachment("application/pdf", text_pdf(LAYER)), Attachment("application/pdf", text_pdf())]
    assert importer.text_layer(files) is None
    result = importer.import_cv(
        [("a.pdf", files[0].data), ("b.pdf", files[1].data)],
        FixtureCvReader(answer=reading()),
        CvDocument(),
    )
    assert result.checked is False and result.unbacked_numbers == []


def test_a_page_with_no_text_is_a_scan_wherever_it_sits():
    # pdfminer closes each page with a form feed; the last one is not a page.
    assert importer._pages("page one\fpage two\f") == ["page one", "page two"]
    assert importer._pages("page one\f \n\f") == ["page one", " \n"]
    # pypdf marks no pages: the file is one stretch of text.
    assert importer._pages("all of it") == ["all of it"]


def test_a_garbage_scan_cannot_crash_the_number_check():
    """``int()`` refuses a digit string past ~4300 characters."""
    read = reading()
    read.summary = "Call " + "7" * 5000 + " or 12 or 007"
    doc = importer.to_document(read, CvDocument())
    missing = importer.unbacked_numbers(doc, "")
    assert missing[-1] == "7" * 5000
    # Value order, not text order: 12 sorts before 300.
    assert missing.index("12") < missing.index("300")


def test_symbols_the_pdf_would_read_as_formatting_are_reported_not_rewritten():
    """Run through the renderer in review: both tildes vanish and the PDF says
    40% where the original hedged — while the editor shows the line as printed."""
    from jobpilot.cv.latex import tex

    read = reading()
    line = "Cut latency by ~40% for ~2M users"
    read.experience[0].items[0] = line
    read.skills[0].text = "C, **Go**, `Rust`"
    result = importer.import_cv([("scan.png", PNG)], FixtureCvReader(answer=read), CvDocument())

    assert result.markup == ["~40% for ~", "**Go**", "`Rust`"]
    # The claim this test rests on, pinned: the renderer really does eat them.
    assert "~" not in tex(line) and "textasciitilde" not in tex(line)
    # Reported, and the draft still says exactly what the page said.
    assert line in importer._draft_text(result.document)


def test_a_draft_with_no_markup_reports_none():
    result = importer.import_cv([("scan.png", PNG)], FixtureCvReader(answer=reading()), CvDocument())
    assert result.markup == []


def test_no_extractor_means_unchecked_not_clean(monkeypatch):
    monkeypatch.setattr("jobpilot.cv.ats.extract", lambda path: None)
    result = importer.import_cv(
        [("cv.pdf", text_pdf(LAYER))], FixtureCvReader(answer=reading()), CvDocument()
    )
    assert result.checked is False


# --------------------------------------------------------------------------- #
# Refusals and failures
# --------------------------------------------------------------------------- #
def test_a_file_with_no_cv_in_it_is_refused_rather_than_returned_empty():
    nothing = reading(
        summary="",
        education=[],
        experience=[],
        projects=[],
        skills=[],
        other=[],
        unreadable=["the image shows a landscape, not a document"],
    )
    with pytest.raises(importer.CvImportRefused, match="nothing that reads as a CV.*landscape"):
        importer.import_cv([("cat.jpg", JPEG)], FixtureCvReader(answer=nothing), CvDocument())


def test_the_models_notes_come_back_with_the_draft():
    read = reading(unreadable=["phone number is cut off at the page edge", " "])
    result = importer.import_cv([("scan.png", PNG)], FixtureCvReader(answer=read), CvDocument())
    assert result.unreadable == ["phone number is cut off at the page edge"]


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


def test_the_reader_makes_one_call_with_the_files_attached_and_logs_it(recorded):
    client = _Client(reply=reading())
    assert ModelCvReader(client).read([IMAGE, PDF]) == reading()

    (call,) = client.calls
    assert call["schema"] is CvRead
    (turn,) = call["messages"]
    assert turn["attachments"] == [IMAGE, PDF] and "2 files" in turn["content"]
    # The two rules a transcription lives or dies by are in the system prompt.
    assert "DO NOT WRITE" in call["system"] and "Do not translate" in call["system"]
    assert [(r.task, r.accepted) for r in recorded] == [("cv_import", True)]


def test_a_dead_backend_is_a_read_error_and_is_still_logged(recorded):
    with pytest.raises(CvReadError, match="rate limited"):
        ModelCvReader(_Client(error=LlmError("rate limited"))).read([IMAGE])
    assert [(r.task, r.accepted) for r in recorded] == [("cv_import", False)]
    assert "rate limited" in recorded[0].error


def test_every_field_the_provider_sees_is_required():
    """An optional field is what trips 'Schema is too complex' (llm/CLAUDE.md),
    and a default is how a field becomes optional without anyone deciding it."""

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert sorted(node.get("required", [])) == sorted(node["properties"]), node
            assert "anyOf" not in node and "default" not in node, node
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(CvRead.model_json_schema())


# --------------------------------------------------------------------------- #
# POST /api/cv/master/import
# --------------------------------------------------------------------------- #
def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


@pytest.fixture
def reader() -> FixtureCvReader:
    return FixtureCvReader(answer=reading())


@pytest.fixture
def client(session_factory, reader):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    with session_factory() as s:
        cv_store.ensure_master(s)
        s.commit()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_reader] = lambda: reader
    c = api_client(app)
    c.headers.update(AUTH)
    yield c
    app.dependency_overrides.clear()


def test_an_import_returns_a_draft_and_saves_nothing(client, reader, session_factory):
    before = client.get("/cv/master").json()

    r = client.post(
        "/cv/master/import",
        json={"files": [{"name": "page-1.png", "data": _b64(PNG)}, {"name": "", "data": _b64(JPEG)}]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["document"]["header"]["first_name"] == "Alex"
    assert [s["key"] for s in body["document"]["sections"]][:2] == ["summary", "experience"]
    assert body["checked"] is False and body["unbacked_numbers"] == []
    assert [f["media_type"] for f in body["files"]] == ["image/png", "image/jpeg"]
    assert [len(call) for call in reader.calls] == [2]

    # The whole point: reading a file is not saving a CV.
    assert client.get("/cv/master").json() == before
    with session_factory() as s:
        assert cv_store.count_versions(s, "master") == before["version"]


def test_a_data_uri_is_accepted_as_well_as_bare_base64(client, reader):
    r = client.post(
        "/cv/master/import",
        json={"files": [{"name": "cv.pdf", "data": "data:application/pdf;base64," + _b64(text_pdf(LAYER))}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["checked"] is True
    assert reader.calls[0][0].is_pdf


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (_b64(HEIC), "not a PNG, JPEG, WebP or PDF"),
        ("not base64 !!", "did not arrive intact"),
        ("A" * (importer.MAX_PDF_BYTES * 4 // 3 + 8), "larger than any import accepts"),
    ],
)
def test_an_unusable_upload_is_a_422_with_a_sentence_not_a_validation_list(
    client, reader, data, message
):
    r = client.post("/cv/master/import", json={"files": [{"name": "x", "data": data}]})
    assert r.status_code == 422
    # A string, so the dashboard can show it as-is.
    assert isinstance(r.json()["detail"], str) and message in r.json()["detail"]
    assert reader.calls == []


def test_too_many_files_are_counted_before_any_is_decoded(client, reader):
    files = [{"name": f"p{n}.png", "data": "not base64 !!"} for n in range(importer.MAX_FILES + 1)]
    r = client.post("/cv/master/import", json={"files": files})
    assert r.status_code == 422
    # The count, not the first undecodable file: nothing was decoded to find out.
    assert "at most 6 files" in r.json()["detail"]
    assert reader.calls == []


def test_markup_in_the_draft_reaches_the_dashboard_as_data(client, reader):
    reader.answer.summary = "Grew usage ~3x in ~6 months."
    r = client.post("/cv/master/import", json={"files": [{"name": "a.png", "data": _b64(PNG)}]})
    assert r.status_code == 200 and r.json()["markup"] == ["~3x in ~"]


def test_only_the_master_cv_is_imported(client, reader):
    r = client.post("/cv/itviec:abc/import", json={"files": [{"name": "a.png", "data": _b64(PNG)}]})
    assert r.status_code == 400
    assert reader.calls == []


def test_a_provider_failure_is_a_502(client, reader):
    reader.answer = None
    r = client.post("/cv/master/import", json={"files": [{"name": "a.png", "data": _b64(PNG)}]})
    assert r.status_code == 502


def test_a_backend_with_no_key_is_a_409_before_the_upload_is_read(client, monkeypatch):
    app.dependency_overrides.pop(get_reader)
    monkeypatch.setattr("jobpilot.llm.blocker", lambda task: f"no key for {task}")
    r = client.post("/cv/master/import", json={"files": [{"name": "a.png", "data": _b64(PNG)}]})
    assert r.status_code == 409 and r.json()["detail"] == "no key for tailor"


def test_the_endpoint_needs_the_token(client):
    r = client.post(
        "/cv/master/import",
        json={"files": [{"name": "a.png", "data": _b64(PNG)}]},
        headers={"X-API-Token": "wrong"},
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# jobpilot cv read
# --------------------------------------------------------------------------- #
def _cli_read(monkeypatch, tmp_path, answer=None):
    from jobpilot.cli import main

    monkeypatch.setattr("jobpilot.llm.blocker", lambda task: "")
    monkeypatch.setattr("jobpilot.llm.warnings", lambda task: [])
    monkeypatch.setattr(
        "jobpilot.cv.reader.default_reader", lambda: FixtureCvReader(answer=answer or reading())
    )
    scan = tmp_path / "scan.png"
    scan.write_bytes(PNG)
    out = tmp_path / "draft.local.json"
    assert main(["cv", "read", str(scan), "-o", str(out)]) == 0
    return cv_store.read_document(out)


def test_cv_read_writes_a_draft_on_the_masters_look_and_saves_nothing(
    worker_db, tmp_path, monkeypatch, capsys
):
    # A look that is NOT the default, or "took the Master's" and "took the
    # default" are the same assertion — which the first version of this test was.
    styled = sample_document().model_copy(update={"template": "plain", "theme": Theme(color="#112233")})
    assert styled.template != CvDocument().template
    with worker_db() as s:
        cv_store.save_version(s, cv_store.MASTER_SCOPE, styled, author="user")
        s.commit()
        before = cv_store.count_versions(s, "master")

    draft = _cli_read(monkeypatch, tmp_path)

    assert draft.header.email == "alex@example.com"
    assert draft.template == "plain" and draft.theme.color == "#112233"
    # ...and none of the Master's words: the sample has three projects.
    assert "projects" not in {section.key for section in draft.sections}
    printed = capsys.readouterr().out
    assert "not saved to the database" in printed and "NOT checked" in printed
    with worker_db() as s:
        assert cv_store.count_versions(s, "master") == before


def test_cv_read_on_a_fresh_database_does_not_create_the_master(worker_db, tmp_path, monkeypatch):
    """`get_document` seeds an empty Master when there is none. A command that
    says it saves nothing must not be what writes version 1."""
    draft = _cli_read(monkeypatch, tmp_path)
    assert draft.template == CvDocument().template
    with worker_db() as s:
        assert cv_store.count_versions(s, "master") == 0


def test_cv_read_prints_what_the_pdf_would_restyle(worker_db, tmp_path, monkeypatch, capsys):
    _cli_read(monkeypatch, tmp_path, reading(summary="Grew usage ~3x in ~6 months."))
    assert "~3x in ~" in capsys.readouterr().out
