"""Reading a CV off a picture or a PDF — the model half of ``cv/importer.py``.

One structured call: the file goes in, a :class:`CvRead` comes out. What happens
to it afterwards (turning it into a ``CvDocument``, checking it, deciding it is
not a CV at all) is ``importer``'s business, so that this module stays the only
place that knows a model was involved.

### Why ``CvRead`` and not ``CvDocument``

``CvDocument`` is the shape the app stores: a discriminated union of five section
types, most of whose fields have defaults. That is exactly the shape a provider
refuses — ``jobpilot/llm/CLAUDE.md`` records the measurement: an optional field
becomes an ``anyOf`` branch, and enough of them fail with *Schema is too complex*
however small the schema reads. So the wire schema is flat and total: one list
per kind of section, **every field required**, and "not on the document" spelled
``""`` or ``[]``. The prompt says so out loud, because a required field with no
stated way to be empty is an instruction to invent something.

### No corrective round

``tailor`` and ``edit`` retry because a rule was broken and the rule can be
quoted back. A transcription has no such rule to quote: there is nothing but the
picture to hold the answer against, and the picture is the one thing code cannot
read. The checks that *are* possible live in ``importer`` and report rather than
retry — and the result is a draft in an editor, saved only when the user says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from jobpilot.llm.base import Attachment, Completion, LlmError, StructuredClient
from jobpilot.llm.usage import call_log

#: Names the model uses in ``CvRead.order``. ``other`` stands for the whole
#: ``other`` list, which keeps its own internal order.
SECTION_NAMES: tuple[str, ...] = ("summary", "education", "experience", "projects", "skills", "other")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReadHeader(_Model):
    first_name: str = Field(description="Every word of the printed name except the last.")
    last_name: str = Field(description="The last word of the printed name.")
    position: str = Field(description="The headline under the name, or ''.")
    address: str = Field(description="As printed, or ''.")
    mobile: str = Field(description="As printed, or ''.")
    email: str = Field(description="As printed, or ''.")
    homepage: str = Field(description="Personal site without the scheme, or ''.")
    github: str = Field(description="GitHub username only, or ''.")
    linkedin: str = Field(description="LinkedIn username only, or ''.")


class ReadHeadings(_Model):
    """The heading printed above each section — '' when the CV has no such section."""

    summary: str
    education: str
    experience: str
    projects: str
    skills: str


class ReadEducation(_Model):
    degree: str
    institution: str
    location: str = Field(description="As printed, or ''.")
    date: str = Field(description="The period as printed, or ''.")
    items: list[str] = Field(description="The bullets under this entry, one per item.")


class ReadEntry(_Model):
    """One job or one project."""

    title: str = Field(description="Employer and job title, or the project's name, as printed.")
    date: str = Field(description="The period as printed, or ''.")
    url: str = Field(description="A link printed for this entry, or ''.")
    role: str = Field(description="The person's role if the entry states one separately, or ''.")
    tech_stack: list[str] = Field(
        description="Items of an explicit tech-stack line on this entry, or []."
    )
    items: list[str] = Field(description="The bullets under this entry, one per item.")


class ReadBullet(_Model):
    label: str = Field(description="A lead-in before a colon ('Languages'), or ''.")
    text: str
    date: str = Field(description="A date printed beside this line, or ''.")


class ReadSection(_Model):
    """Any section that is not one of the five named ones."""

    title: str = Field(description="The heading as printed.")
    items: list[ReadBullet]


class CvRead(_Model):
    header: ReadHeader
    headings: ReadHeadings
    order: list[str] = Field(
        description="Section names in the order they appear on the document: "
        + ", ".join(SECTION_NAMES)
        + "."
    )
    summary: str = Field(description="The profile/objective paragraph, or ''.")
    education: list[ReadEducation]
    experience: list[ReadEntry]
    projects: list[ReadEntry]
    skills: list[ReadBullet]
    other: list[ReadSection]
    unreadable: list[str] = Field(
        description="One short note per thing that could not be read with confidence."
    )


SYSTEM_PROMPT = """\
You transcribe one CV (résumé) from the attached file or files into structured \
fields. The files are page images or PDFs of a single CV, in reading order.

# TRANSCRIBE — DO NOT WRITE

- Copy what is printed. Do not improve, shorten, complete, reorder or correct it.
- Never add a skill, a date, a number, a company, a title or a sentence that is \
not visible in the file. This CV is the record every later step trusts; a word \
you add here becomes a claim the person never made.
- When something is cut off, blurred, covered or handwritten beyond reading: \
copy only the part you can read, or leave it out, and say so in `unreadable`.
- A field with nothing printed for it is "" (a list: []). Empty is the correct \
answer for an absent field. A guess is not.

# KEEP THE LANGUAGE OF THE DOCUMENT

Do not translate. A Vietnamese CV comes back in Vietnamese, word for word, \
diacritics included. Headings too.

# PLAIN TEXT

No Markdown, no asterisks or backticks, no LaTeX. One bullet per list item, \
without the bullet character. A sentence the layout wrapped over two lines is \
one item.

# FIELDS

- `header`: split the printed name so that `first_name` + " " + `last_name` \
reads exactly as printed (the last word is `last_name`). `position` is the \
headline under the name. `github` and `linkedin` are the username only. \
`homepage` is a printed site address without "https://". For all three: a link \
shown only as a word ("Portfolio", "Website", "LinkedIn", "GitHub") or as an \
icon has no address and no username to copy, so the field is "" and the link \
goes in `unreadable`. Anything not printed is "".
- `headings`: the heading printed above each of the five named sections, "" for \
a section the CV does not have.
- `order`: the sections in the order they appear, using exactly these names: \
summary, education, experience, projects, skills, other.
- `summary`: the profile / objective paragraph.
- `education`: one entry per school or degree.
- `experience`: one entry per job. `title` is the employer and the job title as \
printed, joined with ", ". `date` is the period, with the place if it is \
printed beside it.
- `projects`: one entry per project. `url` only if a link is printed.
- `role` and `tech_stack`, on jobs and projects: fill them only when the entry \
has its own line for them ("Role: Team Lead", "Tech stack: Java, Kafka"), and \
then do not repeat that line in `items`. Otherwise "" and [].
- `skills`: one item per line or group. `label` is the group name before the \
colon, "" when there is none.
- `other`: every remaining section — awards, certificates, languages, \
activities, references — with its printed heading.
- `unreadable`: one short note per thing you could not read with confidence or \
had to leave out, written in the language of the document. Include information \
that is drawn rather than written (skill bars, charts, icons without text). \
Empty when everything was legible.
"""


def user_prompt(files: int) -> str:
    pages = "file" if files == 1 else f"{files} files, in reading order"
    return f"Transcribe the CV in the attached {pages}."


class CvReadError(RuntimeError):
    """The model backend could not produce a reading of the file."""


class CvReader(Protocol):
    """Reads the attached pages into a :class:`CvRead`."""

    def read(self, files: list[Attachment]) -> CvRead: ...


@dataclass
class ModelCvReader:
    """One structured call against a :class:`StructuredClient`."""

    client: StructuredClient

    def read(self, files: list[Attachment]) -> CvRead:
        # No job_id: a Master CV belongs to no job. Logged under its own name so
        # `llm stats` can tell a read apart from an edit or a tailor.
        with call_log("cv_import") as usage:
            try:
                completion: Completion[CvRead] = self.client.structured(
                    system=SYSTEM_PROMPT,
                    messages=[
                        {"role": "user", "content": user_prompt(len(files)), "attachments": files}
                    ],
                    schema=CvRead,
                )
            except LlmError as exc:
                raise CvReadError(str(exc)) from exc
            result = usage.add_from(completion)
            usage.succeeded()
            return result


@dataclass
class FixtureCvReader:
    """A canned reading — used by tests and by anything that must not hit an API."""

    answer: CvRead | None = None
    calls: list[list[Attachment]] = field(default_factory=list)

    def read(self, files: list[Attachment]) -> CvRead:
        self.calls.append(files)
        if self.answer is None:
            raise CvReadError("fixture reader has no answer configured")
        return self.answer


def default_reader() -> CvReader:
    """The reader ``llm.tailor`` (or ``llm.provider``) asks for.

    The tailor backend, not a task of its own, for the reason Master CV editing
    uses it: both put the whole CV in front of a model, so the user's choice of
    who may see the CV — and the data-use warning shown for it — already covers
    this call.
    """
    from jobpilot.llm.registry import client_for

    return ModelCvReader(client_for("tailor"))
