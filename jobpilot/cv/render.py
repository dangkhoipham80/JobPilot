"""Serialize a ``CvDocument`` to an Awesome-CV LaTeX project.

``render_document`` returns a path -> text mapping (``cv.tex`` plus one file per
enabled section under ``resume/``) rather than writing to disk, so callers can
diff, snapshot into ``cv_versions.tex_snapshot``, or materialize a build dir.

Templates use ``<< >>`` / ``<% %>`` delimiters so LaTeX's own braces pass through
untouched.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from jobpilot.cv.latex import escape_tex, tex
from jobpilot.cv.schema import CvDocument

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_TEMPLATE = "awesome_cv"
SECTION_DIR = "resume"
#: Per-template manifest, read by :func:`describe_template`.
MANIFEST_FILE = "template.json"
#: Entry file for the cover letter, next to ``cv.tex`` in the same build dir.
LETTER_FILE = "cover_letter.tex"

# section type -> template file. 'experience' and 'projects' share one template.
_SECTION_TEMPLATES = {
    "paragraph": "section_paragraph.tex.j2",
    "bullets": "section_bullets.tex.j2",
    "education": "section_education.tex.j2",
    "experience": "section_entries.tex.j2",
    "projects": "section_entries.tex.j2",
}


class RenderError(RuntimeError):
    """Raised when a document cannot be serialized (unknown template/section)."""


def _url(value: str) -> str:
    """Escape the two characters xelatex still eats inside \\href."""
    return value.replace("#", r"\#").replace("%", r"\%")


def _techlist(items: list[str]) -> str:
    return ", ".join(rf"\textbf{{{escape_tex(i)}}}" for i in items)


@dataclass(frozen=True)
class TemplateInfo:
    """One template on disk: its id (= directory name) plus its manifest."""

    id: str
    name: str
    description: str = ""
    #: Repo-root files/dirs this template needs copied next to the generated
    #: cv.tex. Empty for a template that needs nothing but its own output.
    assets: tuple[str, ...] = ()


def template_dir(template: str) -> Path:
    """Resolve a template id to its directory, rejecting anything unknown.

    Membership is checked against the ids actually on disk rather than by
    probing ``TEMPLATES_DIR / template``: ``doc.template`` is a free-form string
    that arrives from a JSON body, and joining user text onto a path is the
    shape of bug ``check_override`` already exists to prevent.
    """
    if template not in _template_ids():
        raise RenderError(f"unknown CV template: {template!r}")
    return TEMPLATES_DIR / template


def _template_ids() -> list[str]:
    if not TEMPLATES_DIR.is_dir():
        return []
    return sorted(p.name for p in TEMPLATES_DIR.iterdir() if p.is_dir())


def _describe(template: str, root: Path) -> TemplateInfo:
    """Build the info for an id already known to be on disk."""
    raw: dict = {}
    manifest = root / MANIFEST_FILE
    if manifest.is_file():
        try:
            raw = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RenderError(f"template {template!r} has an unreadable {MANIFEST_FILE}: {exc}") from exc
    return TemplateInfo(
        id=template,
        name=str(raw.get("name") or template),
        description=str(raw.get("description") or ""),
        assets=tuple(str(a) for a in raw.get("assets") or ()),
    )


def describe_template(template: str) -> TemplateInfo:
    """Read ``template.json``. A template with no manifest still works."""
    return _describe(template, template_dir(template))


def template_env(template: str) -> Environment:
    root = template_dir(template)
    env = Environment(
        loader=FileSystemLoader(str(root)),
        block_start_string="<%",
        block_end_string="%>",
        variable_start_string="<<",
        variable_end_string=">>",
        comment_start_string="<#",
        comment_end_string="#>",
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
        autoescape=False,
    )
    env.filters["tex"] = tex
    env.filters["url"] = _url
    env.filters["techlist"] = _techlist
    return env


def list_templates() -> list[TemplateInfo]:
    """Templates available on disk, described (for ``GET /cv/templates``).

    Scans the directory once rather than re-validating each id through
    ``template_dir`` — these ids came *from* the listing.
    """
    return [_describe(t, TEMPLATES_DIR / t) for t in _template_ids()]


def render_letter(doc: CvDocument, context: dict) -> str:
    """Serialize a cover letter to ``cover_letter.tex``.

    Takes the header/theme from ``doc`` so the letter carries the same identity
    block and accent colour as the CV it ships with; ``context`` carries the
    letter's own text (already plain strings — the template escapes them).
    """
    env = template_env(doc.template)
    return env.get_template(LETTER_FILE + ".j2").render(doc=doc, h=doc.header, **context)


def render_document(doc: CvDocument) -> dict[str, str]:
    """Render to ``{relative_path: file_text}``. Only enabled sections and
    entries without a hidden tag are emitted."""
    doc = doc.visible()
    env = template_env(doc.template)
    sections = doc.active_sections()

    files: dict[str, str] = {}
    for s in sections:
        name = _SECTION_TEMPLATES.get(s.type)
        if name is None:  # pragma: no cover - guarded by the schema's discriminator
            raise RenderError(f"no template for section type {s.type!r}")
        files[f"{SECTION_DIR}/{s.key}.tex"] = env.get_template(name).render(s=s, doc=doc)

    files["cv.tex"] = env.get_template("cv.tex.j2").render(
        doc=doc, h=doc.header, sections=sections, section_dir=SECTION_DIR
    )
    return files


def render_tex_snapshot(doc: CvDocument) -> str:
    """Single-string snapshot of the whole project, for audit/diff in version history."""
    files = render_document(doc)
    parts = [f"% ===== {path} =====\n{text}" for path, text in sorted(files.items())]
    return "\n".join(parts)


def write_document(doc: CvDocument, dest: Path | str) -> Path:
    """Write the rendered project into ``dest`` (created if missing).

    Section files left over from a previous render are removed first, so
    disabling or renaming a section doesn't leave an orphan ``\\input`` target.
    """
    dest = Path(dest)
    files = render_document(doc)
    section_dir = dest / SECTION_DIR
    if section_dir.is_dir():
        for stale in section_dir.glob("*.tex"):
            if f"{SECTION_DIR}/{stale.name}" not in files:
                stale.unlink()
    for rel, text in files.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return dest
