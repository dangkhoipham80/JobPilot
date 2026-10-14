"""Turn an uploaded CV — page images, a PDF or pasted text — into a draft ``CvDocument``.

The model reads the file (``cv/reader.py``); everything here is what can be done
*without* a model: deciding whether the upload is something a provider will
accept, shaping the reading into the document the app stores, and checking the
one thing about it that code can check.

### Nothing is saved

``import_cv`` returns a document; it does not write one. The Master CV is the
corpus every later tailor is checked against, so a misread that landed there
unseen would be laundered into "already on the CV" for every job that follows.
The draft goes to an editor, next to the file it was read from, and becomes a
version only when the user saves it. That review is the guard — the only one a
photograph allows.

### What code can still check

A PDF that carries a text layer gives a second, independent reading of the same
page. Every number in the draft is looked up in it, and the ones that are not
there are *reported* (``unbacked_numbers``), never corrected and never grounds
for refusal: text extraction has its own failures, and a tool that rewrote a
right answer to match a wrong extraction would be inventing the error it claims
to catch. An image has no such layer, so the answer there is ``checked=False`` —
"nothing was checked", which must never be shown as "nothing was wrong".

A CV pasted as text is the same check with nothing in between: the text *is* the
second reading, so its numbers are always compared (``import_text``).
"""

from __future__ import annotations

import base64
import binascii
import re
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from jobpilot.cv.reader import SECTION_NAMES, CvRead, CvReader, ReadBullet, ReadEntry
from jobpilot.cv.schema import (
    BulletItem,
    BulletsSection,
    CvDocument,
    EducationEntry,
    EducationSection,
    Entry,
    ExperienceSection,
    Header,
    ParagraphSection,
    ProjectsSection,
)
from jobpilot.llm.base import Attachment

#: A CV is a page or two; a photographed one is a file per page.
MAX_FILES = 6

#: Anthropic's API documents a 5 MB cap per image. Whether that is measured
#: before or after base64 (which inflates by a third) is not something tried
#: here: the one backend called for real, the ``claude`` CLI, took a 4.5 MB PNG,
#: but it may well shrink images on its way out. So this assumes the stricter
#: reading — 3.5 MB of file is 4.7 MB encoded — and applies it to every
#: provider: an upload that works or fails depending on which backend `/models`
#: points at is a bug report waiting to be filed. A page reads fine far below
#: this, and the dashboard shrinks photos above it before sending.
MAX_IMAGE_BYTES = 3_500_000
MAX_PDF_BYTES = 10_000_000
MAX_TOTAL_BYTES = 12_000_000

#: Past this it is not a CV, it is the wrong file — and every page is tokens.
MAX_PDF_PAGES = 10

IMAGE_TYPES: tuple[str, ...] = ("image/png", "image/jpeg", "image/webp")
PDF_TYPE = "application/pdf"
TEXT_TYPE = "text/plain"

#: A pasted CV. The ceiling is the page limit above in characters — a dense page
#: is about four thousand — and past it the paste is something else: a whole
#: thread, a portfolio, the wrong tab. The floor is there because a read takes a
#: minute and a model: a name and an email is under it, and no CV is.
MAX_TEXT_CHARS = 40_000
MIN_TEXT_CHARS = 100


class CvImportRefused(ValueError):
    """The upload cannot be read: wrong kind of file, too large, or not a CV."""


def sniff(data: bytes) -> str | None:
    """The media type the bytes themselves claim, or None.

    From the content, never from the file name or the browser's ``type``: this
    string is forwarded to the provider as a statement about the bytes, and a
    ``.png`` that is really a HEIC is rejected there with an error about image
    decoding that says nothing useful to the person who uploaded it.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    # Not ``startswith``: the PDF spec only asks for the header within the first
    # 1024 bytes, and exporters do put a BOM or a blank line ahead of it.
    if b"%PDF-" in data[:1024]:
        return PDF_TYPE
    return None


def _mb(size: int) -> str:
    return f"{size / 1_000_000:.1f} MB"


def pdf_pages(data: bytes) -> int | None:
    """Page count, or None when it cannot be known (pypdf missing, odd file)."""
    try:
        from io import BytesIO

        from pypdf import PdfReader

        return len(PdfReader(BytesIO(data)).pages)
    except Exception:
        return None


#: What to do instead, when the file is not one of the four kinds — said to
#: somebody importing a CV. Other callers of ``load_files`` pass their own.
CV_TEXT_HINT = "a CV that is already text is pasted, or read with `cv read --text`"


def load_files(
    files: list[tuple[str, bytes]], *, text_hint: str = CV_TEXT_HINT
) -> list[Attachment]:
    """Validate an upload and hand back what the model will be shown.

    Refuses rather than repairs. Every limit here is one a provider enforces
    anyway; refusing first means the message names the file and the limit
    instead of quoting a 400 from somebody else's API.
    """
    if not files:
        raise CvImportRefused("no file was uploaded")
    if len(files) > MAX_FILES:
        raise CvImportRefused(f"at most {MAX_FILES} files per import — got {len(files)}")

    out: list[Attachment] = []
    for name, data in files:
        label = name or "file"
        if not data:
            raise CvImportRefused(f"{label} is empty")
        kind = sniff(data)
        if kind is None:
            raise CvImportRefused(
                f"{label} is not a PNG, JPEG, WebP or PDF — convert it first "
                "(an iPhone HEIC photo, a Word file and a screenshot in TIFF all land here; "
                f"{text_hint})"
            )
        limit = MAX_PDF_BYTES if kind == PDF_TYPE else MAX_IMAGE_BYTES
        if len(data) > limit:
            raise CvImportRefused(
                f"{label} is {_mb(len(data))}; the limit for "
                f"{'a PDF' if kind == PDF_TYPE else 'an image'} is {_mb(limit)}"
            )
        if kind == PDF_TYPE:
            pages = pdf_pages(data)
            # None is "could not count", not "too many": let the provider decide.
            if pages is not None and pages > MAX_PDF_PAGES:
                raise CvImportRefused(
                    f"{label} has {pages} pages; an import takes at most {MAX_PDF_PAGES}"
                )
        out.append(Attachment(media_type=kind, data=data, name=name))

    total = sum(len(a.data) for a in out)
    if total > MAX_TOTAL_BYTES:
        raise CvImportRefused(
            f"the files add up to {_mb(total)}; the limit per import is {_mb(MAX_TOTAL_BYTES)}"
        )
    return out


#: Every way a paste ends a line or a page. A form feed becomes a newline, not
#: nothing: dropped, it would weld the last word of one page to the first of
#: the next — and "2024" to "2025", which the number check would then miss.
_LINE_BREAK = re.compile(r"\r\n|[\r\x0b\x0c\u0085\u2028\u2029]")

#: What is left below U+0020 except tab and newline, plus DEL. None of it is
#: text, and a NUL is refused outright by Postgres if it ever reached a saved CV.
#: Replaced by a space rather than removed, for the reason a form feed becomes a
#: newline: whatever stood between two numbers must go on standing between them.
_CONTROL = re.compile(r"[\x00-\x08\x0e-\x1f\x7f]")


def plain_text(text: str) -> str:
    """``text`` with one kind of line ending and no control characters."""
    return _CONTROL.sub(" ", _LINE_BREAK.sub("\n", text)).strip()


def decode_upload(name: str, data: str) -> bytes:
    """One uploaded file's bytes. Accepts a bare base64 string or a data URI."""
    payload = data.split(",", 1)[1] if data.startswith("data:") else data
    # Checked on the encoded length, before decoding: a body far past any limit
    # should cost a comparison, not an allocation the size of the upload.
    if len(payload) > MAX_PDF_BYTES * 4 // 3 + 4:
        raise CvImportRefused(f"{name or 'file'} is larger than any import accepts")
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CvImportRefused(f"{name or 'file'} did not arrive intact") from exc


def decode_uploads(files: list[tuple[str, str]]) -> list[tuple[str, bytes]]:
    """Every uploaded file's bytes, in order.

    Counted before anything is decoded: the limit exists so that a body of a
    thousand files costs a comparison, not a thousand allocations.
    """
    if len(files) > MAX_FILES:
        raise CvImportRefused(f"at most {MAX_FILES} files per import — got {len(files)}")
    return [(name, decode_upload(name, data)) for name, data in files]


def load_text(text: str) -> str:
    """Validate a pasted CV and hand back what the model will be shown.

    Line endings are made one kind and control characters dropped; nothing else
    is touched. This string is also what the draft's numbers are checked
    against, so it has to stay what the user pasted.
    """
    cleaned = plain_text(text)
    if not cleaned:
        raise CvImportRefused("no text was pasted")
    if len(cleaned) > MAX_TEXT_CHARS:
        raise CvImportRefused(
            f"the text is {len(cleaned):,} characters; a CV import takes at most "
            f"{MAX_TEXT_CHARS:,} — paste the CV alone"
        )
    if len(cleaned) < MIN_TEXT_CHARS:
        raise CvImportRefused(
            f"the text is {len(cleaned)} characters — too short to be a CV "
            f"(at least {MIN_TEXT_CHARS})"
        )
    return cleaned


# --------------------------------------------------------------------------- #
# CvRead -> CvDocument
# --------------------------------------------------------------------------- #
#: Titles for a section the document left unheaded. English, like the skeleton's:
#: they are CV content the user renames in the editor, not UI copy.
_DEFAULT_TITLES = {
    "summary": "Summary",
    "education": "Education",
    "experience": "Work Experience",
    "projects": "Projects",
    "skills": "Skills",
}


_MAX_KEY = 40


def _lines(values: list[str]) -> list[str]:
    return [v.strip() for v in values if v.strip()]


def _key(title: str, taken: set[str]) -> str:
    """A section key: ASCII, unique, safe as a file name.

    The key names ``resume/<key>.tex`` and is ``\\input`` by LaTeX, so a heading
    cannot be used as-is — "Chứng chỉ & Giải thưởng" has to become
    ``chung-chi-giai-thuong``. ``đ`` is mapped by hand because Unicode gives it
    no decomposition: NFKD leaves it whole and the ASCII filter would drop it.
    """
    folded = unicodedata.normalize("NFKD", title.replace("đ", "d").replace("Đ", "D"))
    slug = re.sub(r"[^a-z0-9]+", "-", folded.encode("ascii", "ignore").decode().lower()).strip("-")
    # A heading is a few words; anything longer is a paragraph the model filed
    # as one, and it would otherwise become a file name of the same length.
    base = slug[:_MAX_KEY].strip("-") or "section"
    key, n = base, 2
    while key in taken:
        key, n = f"{base}-{n}", n + 1
    taken.add(key)
    return key


#: A profile address: optional scheme, any subdomain (``www.``, and the country
#: ones LinkedIn hands out — ``vn.linkedin.com`` is what a CV printed in Vietnam
#: usually carries), then the path.
_PROFILE_URL = re.compile(
    r"^(?:https?://)?(?:[\w-]+\.)*(github\.com|linkedin\.com)(?:/(.*))?$", re.IGNORECASE
)

#: What comes back when only the *name of the service* was printed — an icon
#: with "LinkedIn" beside it. Not a username, however much it looks like one.
_NOT_A_HANDLE = frozenset({"github", "linkedin"})


def _handle(value: str) -> str | None:
    """A username, from however it was printed — or None when none was.

    ``github.com/alex?tab=repositories`` and ``vn.linkedin.com/in/alex/details/``
    both mean ``alex``: the templates build the profile URL themselves, so
    anything more in this field is linked as ``github.com/github.com/alex``.

    The refusals are the lesson ``_homepage`` learned from a real PDF, one field
    over: a link printed as a bare word is a label, and ``LinkedIn`` would be
    linked as ``linkedin.com/in/LinkedIn`` — somebody else's page. A LinkedIn
    address is only a person when its path starts ``in/``; ``/pub/…`` and
    ``/company/…`` have no slug this field could hold. Neither service allows a
    space, a dot or a colon in a username, which is also what stops the pieces
    of an address on some other host from being mistaken for one.
    """
    printed = value.strip().split("?", 1)[0].split("#", 1)[0]
    url = _PROFILE_URL.match(printed)
    parts = [p for p in (url.group(2) or "" if url else printed).split("/") if p]
    if parts and parts[0].lower() == "in":
        # LinkedIn's own short form, with or without the host in front.
        parts = parts[1:]
    elif url and url.group(1).lower() == "linkedin.com":
        return None
    name = parts[0].lstrip("@") if parts else ""
    if not name or any(c in name for c in " .:") or name.lower() in _NOT_A_HANDLE:
        return None
    return name


def _homepage(value: str) -> str | None:
    """A site address, or None when what was read is not one.

    Seen on the first real PDF tried: a header link printed as the single word
    "Portfolio" came back as the homepage. It is the label a link sits under,
    not an address, and the template would have linked it as ``http://Portfolio``.
    An address has a dot in it and no spaces; anything else is dropped rather
    than guessed at — the URL behind the label is not on the page to be read.
    """
    site = re.sub(r"^https?://", "", value.strip(), flags=re.IGNORECASE).rstrip("/")
    return site if "." in site and " " not in site else None


def _bullet(item: ReadBullet) -> BulletItem:
    return BulletItem(
        label=item.label.strip() or None, text=item.text.strip(), date=item.date.strip() or None
    )


def _entry(entry: ReadEntry) -> Entry:
    return Entry(
        title=entry.title.strip(),
        date=entry.date.strip(),
        url=entry.url.strip() or None,
        items=_lines(entry.items),
        role=entry.role.strip() or None,
        tech_stack=_lines(entry.tech_stack),
    )


def to_document(read: CvRead, base: CvDocument) -> CvDocument:
    """Shape a reading into a document, on ``base``'s template and theme.

    Only what was on the page: a section the CV does not have is left out rather
    than added empty, so the draft has exactly the sections the original does.
    ``base`` contributes presentation and nothing else — none of its text
    survives, because a draft that mixed two CVs could not be checked against
    either.
    """
    h = read.header
    header = Header(
        first_name=h.first_name.strip(),
        last_name=h.last_name.strip(),
        position=h.position.strip(),
        address=h.address.strip() or None,
        mobile=h.mobile.strip() or None,
        email=h.email.strip() or None,
        homepage=_homepage(h.homepage),
        github=_handle(h.github),
        linkedin=_handle(h.linkedin),
    )

    def title(name: str) -> str:
        return getattr(read.headings, name).strip() or _DEFAULT_TITLES[name]

    taken: set[str] = set(_DEFAULT_TITLES)
    groups: dict[str, list] = {name: [] for name in SECTION_NAMES}

    if read.summary.strip():
        groups["summary"].append(
            ParagraphSection(key="summary", title=title("summary"), text=read.summary.strip())
        )
    education = [
        EducationEntry(
            degree=e.degree.strip(),
            institution=e.institution.strip(),
            location=e.location.strip(),
            date=e.date.strip(),
            items=_lines(e.items),
        )
        for e in read.education
    ]
    if education:
        groups["education"].append(
            EducationSection(key="education", title=title("education"), entries=education)
        )
    if read.experience:
        groups["experience"].append(
            ExperienceSection(
                key="experience",
                title=title("experience"),
                entries=[_entry(e) for e in read.experience],
            )
        )
    if read.projects:
        groups["projects"].append(
            ProjectsSection(
                key="projects", title=title("projects"), entries=[_entry(e) for e in read.projects]
            )
        )
    skills = [_bullet(i) for i in read.skills if i.text.strip()]
    if skills:
        groups["skills"].append(BulletsSection(key="skills", title=title("skills"), items=skills))
    for section in read.other:
        items = [_bullet(i) for i in section.items if i.text.strip()]
        if items:
            heading = section.title.strip()
            groups["other"].append(
                BulletsSection(key=_key(heading, taken), title=heading or "Other", items=items)
            )

    # The document's own order first; anything the model did not place keeps the
    # skeleton's order after it. A name it made up is ignored, not an error.
    stated = [name for name in read.order if name in groups]
    order = list(dict.fromkeys([*stated, *SECTION_NAMES]))
    sections = [section for name in order for section in groups[name]]

    return CvDocument(template=base.template, theme=base.theme, header=header, sections=sections)


# --------------------------------------------------------------------------- #
# The one mechanical check
# --------------------------------------------------------------------------- #
_DIGITS = re.compile(r"\d+")

#: A text layer shorter than this share of the draft is not where the draft came
#: from — a scanned PDF with a stamped page number, an export with only a footer.
#: Checking against it would flag every number on the CV.
_MIN_LAYER_SHARE = 0.5


def _draft_text(doc: CvDocument) -> str:
    """Everything the draft says, header included, as one blob."""
    out: list[str] = []

    def walk(node) -> None:
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    # Header and sections only: template and theme are the app's words, not the CV's.
    walk(doc.header.model_dump(mode="json"))
    walk([s.model_dump(mode="json", exclude={"key", "type"}) for s in doc.sections])
    return " ".join(out)


def pages_of(text: str) -> list[str]:
    """``text`` per page. pdfminer ends each page with a form feed; pypdf does
    not mark pages at all, in which case this is the whole file as one."""
    pages = text.split("\f")
    return pages[:-1] if len(pages) > 1 and not pages[-1].strip() else pages


def text_layer(files: list[Attachment]) -> str | None:
    """The text every file carries, or None when that is not the whole CV.

    None for any upload that includes an image, a PDF with no text, or a PDF
    with a page that has none: the layer would then cover only some of the CV,
    and every number read off the rest would look invented. Also None when no
    extractor is installed — unknown, not empty.

    Not airtight, and the direction it fails in is the tolerable one: a scanned
    page that happens to carry a stamped page number counts as text, so its
    numbers get *reported* as missing. A false alarm sends the user to look at
    the original, which is where this feature sends them anyway.
    """
    from jobpilot.cv.ats import extract

    if not files or not all(a.is_pdf for a in files):
        return None
    parts: list[str] = []
    # A file on disk because both extractors take a path; 0700 and gone on exit,
    # like the system prompt in ``llm/claude_cli.py`` — it is the whole CV.
    with tempfile.TemporaryDirectory(prefix="jobpilot-cv-import-") as workdir:
        for n, attachment in enumerate(files):
            path = Path(workdir) / f"{n}.pdf"
            path.write_bytes(attachment.data)
            got = extract(path)
            # A file — or, where the extractor marks page breaks, a page — with
            # no text at all is a scan. The layer then covers part of the CV,
            # and every number read off the rest would be reported as invented.
            if got is None or not all(page.strip() for page in pages_of(got.text)):
                return None
            parts.append(got.text)
    return "\n".join(parts)


def unbacked_numbers(doc: CvDocument, layer: str) -> list[str]:
    """Numbers the draft states that the PDF's own text never does."""
    missing = set(_DIGITS.findall(_draft_text(doc))) - set(_DIGITS.findall(layer))
    # Numeric order without ``int()``: Python refuses to convert a digit string
    # past ~4300 characters, and a page of garbage is exactly what a bad scan
    # reads as. Length then text orders digit strings the way their values do.
    return sorted(missing, key=lambda n: (len(n.lstrip("0")), n))


def markup_hits(doc: CvDocument) -> list[str]:
    """Stretches of the draft that the PDF will render as formatting.

    Text in a ``CvDocument`` is not plain: ``~x~``, backticks, ``**x**`` and
    ``[label](url)`` are markup (``cv/latex.py``). A person typing in the editor
    knows that; a document read off a scan was never written in it. Measured on
    the renderer: "Cut latency by ~40% for ~2M users" loses both tildes, so the
    PDF claims 40% where the original hedged — while the editor still shows the
    line exactly as it was printed. Reported, not rewritten: only the person
    holding the original knows whether the symbol was meant.
    """
    from jobpilot.cv.latex import markup_spans

    seen: dict[str, None] = {}

    def walk(node) -> None:
        if isinstance(node, str):
            seen.update(dict.fromkeys(markup_spans(node)))
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(doc.header.model_dump(mode="json"))
    walk([s.model_dump(mode="json", exclude={"key", "type"}) for s in doc.sections])
    return list(seen)


@dataclass
class CvImportResult:
    document: CvDocument
    #: The model's own notes on what it could not read.
    unreadable: list[str] = field(default_factory=list)
    #: True when the draft's numbers were compared with a second reading: every
    #: file a PDF with text on every page (see ``text_layer`` for what that
    #: cannot rule out), or the source was pasted text.
    checked: bool = False
    unbacked_numbers: list[str] = field(default_factory=list)
    #: Stretches the PDF will render as formatting rather than print as written.
    markup: list[str] = field(default_factory=list)
    #: What was actually sent, after sniffing: name, media type, size. A pasted
    #: CV is one nameless ``text/plain`` entry.
    files: list[dict] = field(default_factory=list)


def _draft(read: CvRead, base: CvDocument) -> CvDocument:
    document = to_document(read, base)
    if not document.sections:
        # A photo of something else, a blank scan, a page too blurred to read, a
        # paste that was a job advert. Refusing beats handing back an empty
        # editor that looks like a result.
        raise CvImportRefused(
            "nothing that reads as a CV was found"
            + (f" — {'; '.join(read.unreadable)}" if read.unreadable else "")
        )
    return document


def _result(
    read: CvRead, document: CvDocument, *, layer: str | None, files: list[dict]
) -> CvImportResult:
    """``layer`` is the second reading the numbers are held against, or None."""
    checked = layer is not None
    return CvImportResult(
        document=document,
        unreadable=_lines(read.unreadable),
        checked=checked,
        unbacked_numbers=unbacked_numbers(document, layer or "") if checked else [],
        markup=markup_hits(document),
        files=files,
    )


def import_cv(files: list[tuple[str, bytes]], reader: CvReader, base: CvDocument) -> CvImportResult:
    """Read an uploaded CV into a draft document. Saves nothing."""
    attachments = load_files(files)
    read = reader.read(attachments)
    document = _draft(read, base)

    layer = text_layer(attachments)
    if layer is not None and len(layer.strip()) < len(_draft_text(document)) * _MIN_LAYER_SHARE:
        layer = None
    return _result(
        read,
        document,
        layer=layer,
        files=[
            {"name": a.name, "media_type": a.media_type, "bytes": len(a.data)} for a in attachments
        ],
    )


def import_text(text: str, reader: CvReader, base: CvDocument) -> CvImportResult:
    """Read a CV pasted as text into a draft document. Saves nothing.

    Always ``checked``: the paste is itself the text the draft's numbers are
    looked up in, so there is no share-of-the-draft threshold to pass — that one
    exists for a PDF layer that may not be where the draft came from, and this
    text is, by construction. What it still cannot tell is the same as for a
    PDF: a number that is in the text but was moved to the wrong entry.
    """
    source = load_text(text)
    read = reader.read_text(source)
    document = _draft(read, base)
    return _result(
        read,
        document,
        layer=source,
        files=[{"name": "", "media_type": TEXT_TYPE, "bytes": len(source.encode("utf-8"))}],
    )
