"""Phase 4.5: inline markup -> LaTeX, and CvDocument -> .tex rendering."""

from __future__ import annotations

import pytest

from jobpilot.cv.latex import escape_tex, tex
from jobpilot.cv.compile import sync_assets, template_assets
from jobpilot.cv.render import (
    RenderError,
    list_templates,
    render_document,
    render_tex_snapshot,
    template_dir,
)
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
    Theme,
)
from jobpilot.cv.sample import sample_document


# --------------------------------------------------------------------------- #
# latex.py
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("plain", "plain"),
        ("80% & rising", r"80\% \& rising"),
        ("snake_case #1", r"snake\_case \#1"),
        ("**bold**", r"\textbf{bold}"),
        ("`Spring Boot`", r"\tech{Spring Boot}"),
        ("~React~", r"\techfe{React}"),
        ("a **b** c `d` e", r"a \textbf{b} c \tech{d} e"),
        ("[Portfolio](https://x.dev/p)", r"\hreficon{https://x.dev/p}{Portfolio}"),
        # Link labels render recursively.
        ("[**Slide** `AI`](http://a.b)", r"\hreficon{http://a.b}{\textbf{Slide} \tech{AI}}"),
        # Unmatched markers degrade to literal text rather than eating the line.
        ("50% off * sale", r"50\% off * sale"),
        ("", ""),
    ],
)
def test_inline_markup(raw, expected):
    assert tex(raw) == expected


def test_escape_does_not_double_escape_backslash():
    assert escape_tex(r"a\b") == r"a\textbackslash{}b"


def test_markup_body_is_escaped():
    """Specials inside a marker still get escaped — no LaTeX injection via content."""
    assert tex("**100% done**") == r"\textbf{100\% done}"
    assert tex("`C#`") == r"\tech{C\#}"


def test_url_specials_escaped_in_links():
    assert tex("[x](https://a.b/c#d)") == r"\hreficon{https://a.b/c\#d}{x}"


# --------------------------------------------------------------------------- #
# render.py
# --------------------------------------------------------------------------- #
def _doc(**kw) -> CvDocument:
    return CvDocument(header=Header(first_name="A", last_name="B"), **kw)


def test_renders_one_file_per_enabled_section_plus_cv_tex():
    doc = _doc(
        sections=[
            ParagraphSection(key="summary", title="Summary", text="Hi"),
            BulletsSection(key="skills", title="Skills", enabled=False),
        ]
    )
    files = render_document(doc)
    assert set(files) == {"cv.tex", "resume/summary.tex"}
    # Disabled sections are neither emitted nor \input.
    assert "resume/skills.tex" not in files["cv.tex"]
    assert r"\input{resume/summary.tex}" in files["cv.tex"]


def test_section_order_follows_the_json_list():
    doc = _doc(
        sections=[
            BulletsSection(key="skills", title="Skills"),
            ParagraphSection(key="summary", title="Summary"),
        ]
    )
    body = render_document(doc)["cv.tex"]
    assert body.index("resume/skills.tex") < body.index("resume/summary.tex")


def test_bullets_render_label_and_date():
    doc = _doc(
        sections=[
            BulletsSection(
                key="honors",
                title="Honors & Awards",
                items=[BulletItem(label="Award", text="Won it", date="2024")],
            )
        ]
    )
    out = render_document(doc)["resume/honors.tex"]
    assert r"\cvsection{Honors \& Awards}" in out
    assert r"\item{\textbf{Award}: Won it\hfill\entrysimpledatestyle{2024}}" in out


def test_education_entry_macro():
    doc = _doc(
        sections=[
            EducationSection(
                key="education",
                title="Education",
                entries=[
                    EducationEntry(
                        degree="`BSc`, SE",
                        institution="FPT",
                        location="HCMC",
                        date="2022 -- 2026",
                        items=["GPA **3.2**"],
                    )
                ],
            )
        ]
    )
    out = render_document(doc)["resume/education.tex"]
    assert r"\cventry" in out
    assert r"{\tech{BSc}, SE}" in out
    assert r"\item {GPA \textbf{3.2}}" in out


def test_experience_and_projects_tech_stack_lines_differ():
    entry = Entry(title="T", date="D", items=["did a thing"], tech_stack=["Java", "Kafka"])
    exp = render_document(
        _doc(sections=[ExperienceSection(key="e", title="Work", entries=[entry])])
    )["resume/e.tex"]
    proj = render_document(
        _doc(
            sections=[
                ProjectsSection(
                    key="p",
                    title="Projects",
                    entries=[entry.model_copy(update={"role": "Team Lead"})],
                )
            ]
        )
    )["resume/p.tex"]

    assert r"\item {\tech{Tech Stack}: \textbf{Java}, \textbf{Kafka}}" in exp
    assert r"\textbf{Role}: Team Lead \quad | \quad \textbf{Tech Stack}:" in proj


def test_entry_url_wraps_title_in_hreficon():
    doc = _doc(
        sections=[
            ProjectsSection(
                key="p",
                title="Projects",
                entries=[Entry(title="Proj", date="2024", url="https://git.io/x")],
            )
        ]
    )
    out = render_document(doc)["resume/p.tex"]
    assert r"\hreficon{https://git.io/x}{\textbf{Proj}}" in out


def test_theme_named_colour_vs_hex():
    named = render_document(_doc(theme=Theme(color="awesome-emerald")))["cv.tex"]
    hexed = render_document(_doc(theme=Theme(color="#ca63a8")))["cv.tex"]
    assert r"\colorlet{awesome}{awesome-emerald}" in named
    assert r"\definecolor{awesome}{HTML}{CA63A8}" in hexed


def test_optional_header_fields_are_omitted():
    out = render_document(_doc())["cv.tex"]
    assert r"\address" not in out
    assert r"\quote" not in out


def test_unknown_template_rejected():
    with pytest.raises(RenderError):
        render_document(_doc(template="does_not_exist"))


def test_both_shipped_templates_are_listed():
    assert {"awesome_cv", "plain"} <= {t.id for t in list_templates()}


def test_a_template_declares_the_assets_it_needs():
    """`plain` builds on stock `article`, so it must not drag the .cls along."""
    assert template_assets("awesome_cv") == ("awesome-cv.cls", "fontawesome.sty", "fonts")
    assert template_assets("plain") == ("fonts",)


def test_sync_assets_refreshes_a_stale_asset_instead_of_keeping_it(tmp_path):
    """Build dirs under out/cv/<scope>/ are long-lived and reused, so a
    skip-if-exists copy pins each one to whatever awesome-cv.cls was checked out
    the first time it built. That is how the tectonic engine's fix to
    awesome-cv.cls + fontawesome.sty reached freshly-built scopes only, while
    every previously-built scope kept the old pair and died on a missing font —
    with the repo holding the fix, so the error pointed at the wrong thing."""
    source, dest = tmp_path / "repo", tmp_path / "build"
    (source / "fonts").mkdir(parents=True)
    (source / "awesome-cv.cls").write_text("new class", encoding="utf-8")
    (source / "fontawesome.sty").write_text("new sty", encoding="utf-8")
    (source / "fonts" / "Roboto-Regular.ttf").write_bytes(b"new font")

    dest.mkdir()
    (dest / "fonts").mkdir()
    (dest / "awesome-cv.cls").write_text("OLD class", encoding="utf-8")
    (dest / "fontawesome.sty").write_text("OLD sty", encoding="utf-8")
    (dest / "fonts" / "Roboto-Regular.ttf").write_bytes(b"OLD font")

    sync_assets(dest, source=source, template="awesome_cv")

    assert (dest / "awesome-cv.cls").read_text(encoding="utf-8") == "new class"
    assert (dest / "fontawesome.sty").read_text(encoding="utf-8") == "new sty"
    # Fonts live in a directory asset, which the old code copied only when the
    # whole directory was absent — a stale font file was unreachable forever.
    assert (dest / "fonts" / "Roboto-Regular.ttf").read_bytes() == b"new font"


def test_sync_assets_leaves_unrelated_files_in_the_build_dir_alone(tmp_path):
    """Refreshing assets must not turn into wiping the build dir: the rendered
    .tex and any raw-LaTeX override live here too."""
    source, dest = tmp_path / "repo", tmp_path / "build"
    source.mkdir()
    (source / "awesome-cv.cls").write_text("class", encoding="utf-8")
    (source / "fontawesome.sty").write_text("sty", encoding="utf-8")
    dest.mkdir()
    (dest / "cv.tex").write_text("hand-written", encoding="utf-8")

    sync_assets(dest, source=source, template="awesome_cv")

    assert (dest / "cv.tex").read_text(encoding="utf-8") == "hand-written"


def test_a_template_id_may_not_walk_out_of_the_templates_dir():
    """``doc.template`` is free-form text off a JSON body before it is a path."""
    for escape in ("../../etc", "..", "awesome_cv/../plain"):
        with pytest.raises(RenderError):
            template_dir(escape)


# --------------------------------------------------------------------------- #
# The "plain" template. It drops awesome-cv.cls for stock `article`, which swaps
# a forgiving custom environment for enumitem's strict one — so the cases that
# matter here are the *sparse* ones, not the full CV.
# --------------------------------------------------------------------------- #
def test_plain_defines_every_macro_the_inline_markup_emits():
    """cv/latex.py emits these unconditionally; an undefined one kills the build."""
    out = render_document(
        _doc(
            template="plain",
            sections=[ParagraphSection(key="s", title="S", text="`Java` ~React~ [P](http://a.b)")],
        )
    )["cv.tex"]
    for macro in (r"\newcommand{\tech}", r"\newcommand{\techfe}", r"\newcommand{\hreficon}"):
        assert macro in out


@pytest.mark.parametrize(
    "section",
    [
        ExperienceSection(key="exp", title="Experience", entries=[Entry(title="Solo", date="2024")]),
        ProjectsSection(key="prj", title="Projects", entries=[Entry(title="Solo", date="2024")]),
        EducationSection(key="edu", title="Education", entries=[EducationEntry(degree="BSc")]),
        BulletsSection(key="sk", title="Skills", items=[]),
    ],
)
def test_plain_never_emits_an_empty_itemize(section):
    """``\\begin{itemize}\\end{itemize}`` is a hard LaTeX error, not an empty block.

    A fresh DB seeds a *blank* CV (CLAUDE.md rule 3), so an entry with no bullets
    is the first thing a new user builds, not a corner case.
    """
    out = render_document(_doc(template="plain", sections=[section]))[f"resume/{section.key}.tex"]
    assert r"\begin{itemize}" not in out
    assert section.title in out  # the section itself still renders


def test_plain_keeps_each_bullet_on_its_own_line():
    """trim_blocks eats the newline after a tag; items must not run together."""
    out = render_document(
        _doc(
            template="plain",
            sections=[
                BulletsSection(
                    key="sk",
                    title="Skills",
                    items=[BulletItem(label="Lang", text="Java"), BulletItem(text="Python")],
                )
            ],
        )
    )["resume/sk.tex"]
    assert len([ln for ln in out.splitlines() if r"\item" in ln]) == 2


# --------------------------------------------------------------------------- #
# A full document end to end. Uses the fictional cv/sample.py CV — the app ships
# no CV content of its own, since personal data belongs in the database.
# --------------------------------------------------------------------------- #
def test_a_full_cv_renders_all_six_sections():
    doc = sample_document()
    files = render_document(doc)
    assert set(files) == {
        "cv.tex",
        "resume/summary.tex",
        "resume/education.tex",
        "resume/experience.tex",
        "resume/projects.tex",
        "resume/honors.tex",
        "resume/skills.tex",
    }


def test_full_cv_renders_the_awesome_cv_macros():
    """Spot-check the macro shapes a real Awesome-CV build depends on."""
    files = render_document(sample_document())
    assert r"\name{\textbf{ALEX}}{\tech{EXAMPLE}}" in files["cv.tex"]
    assert (
        r"\item {Wrote \textbf{unit tests} with \tech{JUnit}, achieving "
        r"\textbf{over 80\% code coverage} measured by \textbf{JaCoCo}.}"
        in files["resume/experience.tex"]
    )
    assert (
        r"\item{\textbf{Languages \& Frameworks}: Java, Spring Boot, Python, FastAPI}"
        in files["resume/skills.tex"]
    )


def test_tex_snapshot_covers_every_rendered_file():
    snapshot = render_tex_snapshot(sample_document())
    for path in render_document(sample_document()):
        assert f"% ===== {path} =====" in snapshot
