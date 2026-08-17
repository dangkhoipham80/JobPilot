"""Phase 1: build wrapper unit tests (no Docker needed)."""

import pytest

from jobpilot.tailor import build as build_mod
from jobpilot.tailor.build import (
    BuildError,
    _pages_from_log,
    _pages_from_pdf,
    build_cv,
    page_summary,
)


def test_build_raises_when_entry_missing(tmp_path):
    with pytest.raises(BuildError, match="entry not found"):
        build_cv(tmp_path, entry="nope.tex")


def test_build_raises_when_no_toolchain_at_all(tmp_path, monkeypatch):
    (tmp_path / "cv.tex").write_text("\\documentclass{article}", encoding="utf-8")
    monkeypatch.setattr(build_mod.shutil, "which", lambda _: None)
    with pytest.raises(BuildError, match="neither `docker` nor `xelatex`"):
        build_cv(tmp_path, entry="cv.tex")


def test_pages_from_log(tmp_path):
    log = tmp_path / "cv.log"
    log.write_text("Output written on cv.pdf (1 page, 36973 bytes).", encoding="utf-8")
    assert _pages_from_log(log) == 1


def test_pages_from_log_multi(tmp_path):
    log = tmp_path / "cv.log"
    log.write_text("blah\nOutput written on cv.pdf (2 pages, 1234 bytes).\n", encoding="utf-8")
    assert _pages_from_log(log) == 2


def test_pages_from_log_missing(tmp_path):
    assert _pages_from_log(tmp_path / "absent.log") is None


def test_pages_from_pdf_counts_page_objects(tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.5\n1 0 obj<</Type /Page>>endobj\n<</Type /Pages /Count 1>>")
    assert _pages_from_pdf(pdf) == 1


def test_an_unreadable_page_count_is_unknown_not_zero(tmp_path, monkeypatch):
    """A real xelatex PDF stores its objects in compressed streams, so with pypdf
    missing the regex finds nothing — and the builder image leaves no .log to
    fall back to. Reporting 0 then badges a perfectly good CV as "0 pages" in
    red; the honest answer is that we don't know."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "cv.tex").write_text(
        "\\documentclass{article}\\begin{document}x\\end{document}", "utf-8"
    )
    monkeypatch.setattr(build_mod.shutil, "which", lambda _: "/usr/bin/docker")

    # The PDF has to appear *because the build ran*, the way docker produces it.
    # Pre-creating it and stubbing the run as a no-op would pass even if the
    # build did nothing at all.
    def fake_run(*_a, **_k):
        (work / "cv.pdf").write_bytes(b"%PDF-1.5\n<compressed object streams>\n%%EOF")
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(build_mod.subprocess, "run", fake_run)
    assert build_cv(work, entry="cv.tex").pages is None


def test_a_failed_build_does_not_hand_back_the_previous_pdf(tmp_path, monkeypatch):
    """The image runs `xelatex …; mv …; rm …` with no `set -e`, so LaTeX can fail
    and the container still exits 0. Then the only evidence of failure is the
    missing PDF — which last successful build's file would happily answer for,
    turning a broken build into a silent success serving stale content."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "cv.tex").write_text("\\documentclass{article}", encoding="utf-8")
    (work / "cv.pdf").write_bytes(b"%PDF-1.5\nyesterday\n%%EOF")
    monkeypatch.setattr(build_mod.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(
        build_mod.subprocess,
        "run",
        lambda *a, **k: type(
            "P", (), {"returncode": 0, "stdout": "! Undefined cs", "stderr": ""}
        )(),
    )
    with pytest.raises(BuildError):
        build_cv(work, entry="cv.tex")


def test_the_entry_file_reaches_the_container(tmp_path, monkeypatch):
    """The image's built-in command hardcodes cv.tex, so `entry` only means
    something if we spell the command out ourselves."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "cover_letter.tex").write_text("\\documentclass{article}", encoding="utf-8")
    seen: list[list[str]] = []
    monkeypatch.setattr(build_mod.shutil, "which", lambda _: "/usr/bin/docker")

    def fake_run(cmd, **_k):
        seen.append(cmd)
        (work / "cover_letter.pdf").write_bytes(b"%PDF-1.5\n<</Type /Page>>\n%%EOF")
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(build_mod.subprocess, "run", fake_run)
    result = build_cv(work, entry="cover_letter.tex")
    assert result.pdf.name == "cover_letter.pdf"
    script = seen[0][-1]
    assert "xelatex -output-directory=$DIR cover_letter.tex" in script
    assert "mv $DIR/cover_letter.pdf ." in script
    assert "cv.tex" not in script


def test_an_entry_with_a_space_stays_one_shell_token(tmp_path, monkeypatch):
    """The script is a shell command; an unquoted entry with a space splits into
    two tokens and xelatex reports a missing file that isn't the one named."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "my cv.tex").write_text("\\documentclass{article}", encoding="utf-8")
    seen: list[list[str]] = []
    monkeypatch.setattr(build_mod.shutil, "which", lambda _: "/usr/bin/docker")

    def fake_run(cmd, **_k):
        seen.append(cmd)
        (work / "my cv.pdf").write_bytes(b"%PDF-1.5\n<</Type /Page>>\n%%EOF")
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(build_mod.subprocess, "run", fake_run)
    build_cv(work, entry="my cv.tex")
    script = seen[0][-1]
    assert "'my cv.tex'" in script and "'my cv.pdf'" in script


def test_page_summary_says_unknown_rather_than_warning_about_none_pages():
    assert page_summary(1) == "OK: 1 page"
    assert "WARNING" in page_summary(2)
    assert "unknown" in page_summary(None)


def test_docker_runs_as_the_calling_user_on_posix(monkeypatch):
    """On Linux the container would otherwise write cv.pdf as root, and the next
    build's unlink() would fail with EACCES while reporting stale output."""
    import jobpilot.tailor.build as build_mod

    monkeypatch.setattr(build_mod.os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(build_mod.os, "getgid", lambda: 1000, raising=False)
    assert build_mod._user_args() == ["-u", "1000:1000"]


def test_docker_passes_no_uid_on_windows(monkeypatch):
    """Docker Desktop translates ownership at the mount layer and there is no
    getuid to pass; sending one would be a guess dressed up as a setting."""
    import jobpilot.tailor.build as build_mod

    monkeypatch.delattr(build_mod.os, "getuid", raising=False)
    assert build_mod._user_args() == []


# --------------------------------------------------------------------------- #
# Backend selection (jobpilot/tailor/build.resolve_backend)
# --------------------------------------------------------------------------- #
def _only(*present):
    """Fake a PATH holding exactly `present`."""
    return lambda name: f"/usr/bin/{name}" if name in present else None


def test_auto_prefers_docker_when_it_is_installed(monkeypatch):
    """The machine that has been building CVs all along must keep using the
    same toolchain — an upgrade is not the moment to change how PDFs are made."""
    monkeypatch.setattr(build_mod.shutil, "which", _only("docker", "xelatex"))
    assert build_mod.resolve_backend("auto") == "docker"


def test_auto_falls_to_local_when_docker_is_absent(monkeypatch):
    """The arm64 server: no Docker, because the builder image is amd64-only."""
    monkeypatch.setattr(build_mod.shutil, "which", _only("xelatex"))
    assert build_mod.resolve_backend("auto") == "local"


def test_an_explicit_backend_is_never_second_guessed(monkeypatch):
    monkeypatch.setattr(build_mod.shutil, "which", _only("docker", "xelatex"))
    assert build_mod.resolve_backend("local") == "local"
    assert build_mod.resolve_backend("docker") == "docker"


def test_an_unknown_backend_is_refused(monkeypatch):
    with pytest.raises(BuildError, match="expected one of"):
        build_mod.resolve_backend("podman")


def test_a_broken_docker_does_not_silently_become_a_local_build(tmp_path, monkeypatch):
    """Docker installed but unusable is one command from fixed. Switching
    toolchains behind the user's back would mean the PDF they approved and the
    PDF that gets emailed were made by different software, with nothing said."""
    (tmp_path / "cv.tex").write_text(r"\documentclass{article}", encoding="utf-8")
    monkeypatch.setattr(build_mod.shutil, "which", _only("xelatex"))

    calls = []
    monkeypatch.setattr(build_mod, "_local_run", lambda *a, **k: calls.append(a))
    with pytest.raises(BuildError, match="docker is not on PATH"):
        build_cv(tmp_path, entry="cv.tex", backend="docker")
    assert calls == [], "must not have quietly run the local engine instead"


def test_local_backend_explains_itself_when_xelatex_is_missing(tmp_path, monkeypatch):
    (tmp_path / "cv.tex").write_text(r"\documentclass{article}", encoding="utf-8")
    monkeypatch.setattr(build_mod.shutil, "which", _only("docker"))
    with pytest.raises(BuildError, match="xelatex is not on PATH"):
        build_cv(tmp_path, entry="cv.tex", backend="local")


def test_local_build_runs_xelatex_in_the_build_dir(tmp_path, monkeypatch):
    """xelatex resolves awesome-cv.cls, fontawesome.sty and fonts/ relative to
    its working directory, not to the .tex it was handed. Run it anywhere else
    and the class is 'not found' in a directory that plainly contains it."""
    (tmp_path / "cv.tex").write_text("x", encoding="utf-8")
    monkeypatch.setattr(build_mod.shutil, "which", _only("xelatex"))

    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"], seen["cwd"] = cmd, kwargs.get("cwd")
        out = [a for a in cmd if a.startswith("-output-directory=")][0].split("=", 1)[1]
        from pathlib import Path as P

        (P(out) / "cv.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
        (P(out) / "cv.log").write_text("Output written on cv.pdf (1 page, 10 bytes).")

        class R:
            returncode, stdout, stderr = 0, "", ""

        return R()

    monkeypatch.setattr(build_mod.subprocess, "run", fake_run)
    result = build_cv(tmp_path, entry="cv.tex", backend="local")

    assert seen["cwd"] == str(tmp_path.resolve())
    assert "-interaction=nonstopmode" in seen["cmd"], "a prompt would hang the queue worker"
    assert result.pdf == tmp_path / "cv.pdf"
    # The log is carried back out of the temp dir; the Docker path throws its away.
    assert (tmp_path / "cv.log").is_file()


def test_a_failed_local_build_leaves_no_stale_pdf(tmp_path, monkeypatch):
    """The worst outcome is reporting success with yesterday's PDF."""
    (tmp_path / "cv.tex").write_text("x", encoding="utf-8")
    stale = tmp_path / "cv.pdf"
    stale.write_bytes(b"%PDF-old")
    monkeypatch.setattr(build_mod.shutil, "which", _only("xelatex"))

    class R:
        returncode, stdout, stderr = 1, "", "! LaTeX Error"

    monkeypatch.setattr(build_mod.subprocess, "run", lambda *a, **k: R())
    with pytest.raises(BuildError, match="local backend"):
        build_cv(tmp_path, entry="cv.tex", backend="local")
    assert not stale.exists()
