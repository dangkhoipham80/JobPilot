"""Phase 1: build wrapper unit tests (no Docker and no tectonic needed)."""

import os
from pathlib import Path

import pytest

from jobpilot.tailor import build as build_mod
from jobpilot.tailor.build import (
    BuildError,
    _pages_from_log,
    _pages_from_pdf,
    build_cv,
    page_summary,
    resolve_engine,
)


def _installed(*names):
    """Stub shutil.which so only ``names`` count as installed."""
    return lambda cmd: f"/usr/bin/{cmd}" if cmd in names else None


@pytest.fixture(autouse=True)
def _empty_tools_dir(tmp_path_factory, monkeypatch):
    """Point REPO_ROOT at an empty directory for every test in this module.

    resolve_engine falls back to ``<repo>/tools/`` when tectonic is not on PATH,
    which means a developer who has actually downloaded the binary would see
    different results from CI for the tests that stub ``which`` to return
    nothing. Whether an engine is installed on the machine running the suite is
    not something these tests are about."""
    monkeypatch.setattr(build_mod, "REPO_ROOT", tmp_path_factory.mktemp("no_tools"))


def test_build_raises_when_entry_missing(tmp_path):
    with pytest.raises(BuildError, match="entry not found"):
        build_cv(tmp_path, entry="nope.tex")


def test_build_raises_when_docker_absent(tmp_path, monkeypatch):
    (tmp_path / "cv.tex").write_text("\\documentclass{article}", encoding="utf-8")
    monkeypatch.setattr(build_mod.shutil, "which", _installed())
    with pytest.raises(BuildError, match="docker not found"):
        build_cv(tmp_path, entry="cv.tex", engine="docker")


# --------------------------------------------------------------------------- #
# Engine selection
# --------------------------------------------------------------------------- #


def test_auto_prefers_tectonic_when_both_are_installed(monkeypatch):
    monkeypatch.setattr(build_mod.shutil, "which", _installed("tectonic", "docker"))
    assert resolve_engine("auto")[0] == "tectonic"


def test_auto_falls_back_to_docker(monkeypatch):
    """Docker is the fallback, not dead weight: it is what every PDF in this
    repo's history was built with, so it stays the reference implementation."""
    monkeypatch.setattr(build_mod.shutil, "which", _installed("docker"))
    assert resolve_engine("auto")[0] == "docker"


def test_no_engine_at_all_explains_how_to_install_either(monkeypatch):
    monkeypatch.setattr(build_mod.shutil, "which", _installed())
    with pytest.raises(BuildError) as exc:
        resolve_engine("auto")
    message = str(exc.value)
    assert "tectonic" in message and "docker" in message
    # Naming the engines is not enough — the point of the message is that
    # someone stuck with no PDF can act on it without reading DEPLOY.md.
    assert "tectonic-typesetting" in message and "docker pull" in message


def test_asking_for_a_missing_engine_names_that_engine_not_the_other(monkeypatch):
    """The old message was hardcoded to 'docker not found', which is an actively
    misleading thing to print when tectonic is the engine that is missing."""
    monkeypatch.setattr(build_mod.shutil, "which", _installed("docker"))
    with pytest.raises(BuildError, match="tectonic not found"):
        resolve_engine("tectonic")


def test_an_unknown_engine_is_rejected_rather_than_silently_defaulted(monkeypatch):
    monkeypatch.setattr(build_mod.shutil, "which", _installed("tectonic", "docker"))
    with pytest.raises(BuildError, match="unknown cv.engine"):
        resolve_engine("tectonik")


def _drop_binary(directory, name="tectonic"):
    """A file `which`-style lookups will accept as executable on this platform."""
    directory.mkdir(parents=True, exist_ok=True)
    binary = directory / (f"{name}.exe" if os.name == "nt" else name)
    binary.write_text("", encoding="utf-8")
    binary.chmod(0o755)
    return binary


def test_tectonic_is_found_in_the_repo_tools_dir_without_any_config(tmp_path, monkeypatch):
    """So nobody has to write an absolute path into cv.tectonic_bin. That
    setting works but it names one machine: the file it points at is absent on
    every other checkout, and the failure is quiet — `auto` falls back to Docker
    and builds keep working, just not the way the config says."""
    binary = _drop_binary(tmp_path / build_mod.TOOLS_DIR)
    monkeypatch.setattr(build_mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(build_mod.shutil, "which", _installed())  # nothing on PATH

    engine, resolved = resolve_engine("auto")

    assert engine == "tectonic"
    assert Path(resolved).samefile(binary)


def test_path_wins_over_the_repo_tools_dir(tmp_path, monkeypatch):
    """A system install is the one the rest of the machine already agrees on."""
    _drop_binary(tmp_path / build_mod.TOOLS_DIR)
    monkeypatch.setattr(build_mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(build_mod.shutil, "which", _installed("tectonic"))

    assert resolve_engine("tectonic")[1].endswith("tectonic")
    assert build_mod.TOOLS_DIR not in resolve_engine("tectonic")[1]


def test_a_configured_path_that_is_wrong_is_not_quietly_replaced(tmp_path, monkeypatch):
    """cv.tectonic_bin naming a file that does not exist is a mistake worth
    reporting. Falling back to some other file with the same basename would
    run a binary the config never pointed at."""
    _drop_binary(tmp_path / build_mod.TOOLS_DIR)
    monkeypatch.setattr(build_mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(build_mod.shutil, "which", _installed())

    with pytest.raises(BuildError, match="tectonic not found"):
        resolve_engine("tectonic", tectonic_bin="/nowhere/special/tectonic")


def test_a_relative_tectonic_bin_is_made_absolute(tmp_path, monkeypatch):
    """The tectonic build runs with cwd set to the build dir, so a relative
    cv.tectonic_bin ("a path with a directory component works too", per the
    config docs) gets looked up against the process's directory and executed
    against the build dir — every CV build dies with an exec error several
    directories away from anything that explains it.

    Deliberately no monkeypatching of shutil.which: given a string with a
    directory component, which() checks that path and returns *the string as
    passed*, still relative. A stubbed which() that hands back an absolute path
    asserts the stub, not the behaviour — this test only fails if the real
    resolution is real."""
    tools = tmp_path / "tools"
    tools.mkdir()
    # which() needs something it will accept as executable on this platform.
    name = "tectonic.bat" if os.name == "nt" else "tectonic"
    binary = tools / name
    binary.write_text("", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.chdir(tmp_path)

    engine, resolved = resolve_engine("tectonic", tectonic_bin=f"./tools/{name}")

    assert engine == "tectonic"
    assert Path(resolved).is_absolute(), f"{resolved!r} is still relative"
    assert Path(resolved).samefile(binary)


def test_an_engine_that_cannot_be_executed_is_a_builderror_not_an_oserror(tmp_path, monkeypatch):
    """resolve_engine() found it a moment ago, so this means it went away, is not
    executable, or is the wrong architecture. A bare OSError out of a build
    helper reaches the compile route as a naked 500."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "cv.tex").write_text("\\documentclass{article}", encoding="utf-8")
    monkeypatch.setattr(build_mod.shutil, "which", _installed("tectonic"))

    def boom(*_a, **_k):
        raise OSError(8, "Exec format error")

    monkeypatch.setattr(build_mod.subprocess, "run", boom)
    with pytest.raises(BuildError, match="could not run tectonic"):
        build_cv(work, entry="cv.tex", engine="tectonic")


# --------------------------------------------------------------------------- #
# Tectonic backend
# --------------------------------------------------------------------------- #


def _tectonic_run(work, stem="cv", rc=0, stdout="", stderr="", log=None):
    """A fake subprocess.run that produces output the way tectonic does."""
    seen: list[dict] = []

    def fake_run(cmd, **kwargs):
        seen.append({"cmd": cmd, "cwd": kwargs.get("cwd")})
        if rc == 0:
            (work / f"{stem}.pdf").write_bytes(b"%PDF-1.5\n<</Type /Page>>\n%%EOF")
            if log is not None:
                (work / f"{stem}.log").write_text(log, encoding="utf-8")
        return type("P", (), {"returncode": rc, "stdout": stdout, "stderr": stderr})()

    return seen, fake_run


def test_tectonic_runs_in_the_build_dir_so_relative_paths_resolve(tmp_path, monkeypatch):
    """The project reaches its sections as \\input{resume/...} and its fonts as
    Path=fonts/. Docker got that from the bind mount; tectonic gets it from cwd,
    and without it the build dies on a missing file or a missing font."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "cv.tex").write_text("\\documentclass{article}", encoding="utf-8")
    monkeypatch.setattr(build_mod.shutil, "which", _installed("tectonic"))
    seen, fake_run = _tectonic_run(work)
    monkeypatch.setattr(build_mod.subprocess, "run", fake_run)

    result = build_cv(work, entry="cv.tex", engine="tectonic")

    assert result.engine == "tectonic"
    cmd, cwd = seen[0]["cmd"], seen[0]["cwd"]
    assert cwd == str(work.resolve())
    assert cmd[1:3] == ["-X", "compile"] and cmd[-1] == "cv.tex"
    # --untrusted for the same reason compile.check_override() exists: a raw
    # .tex override arrives from a text box, so \write18 stays off.
    assert "--untrusted" in cmd
    # Without --keep-logs there is no .log, and a missing pypdf would then mean
    # no page count at all rather than a fallback.
    assert "--keep-logs" in cmd
    assert "docker" not in cmd


def test_tectonic_reports_its_own_chatter_not_an_empty_stdout(tmp_path, monkeypatch):
    """Tectonic writes progress and errors to stderr; Docker writes to stdout.
    Tailing the wrong stream yields '' — a build that looks like it had nothing
    to say rather than one nobody read."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "cv.tex").write_text("\\documentclass{article}", encoding="utf-8")
    monkeypatch.setattr(build_mod.shutil, "which", _installed("tectonic"))
    _, fake_run = _tectonic_run(work, stdout="", stderr="note: Writing `cv.pdf`")
    monkeypatch.setattr(build_mod.subprocess, "run", fake_run)

    assert "Writing" in build_cv(work, entry="cv.tex", engine="tectonic").log_tail


def test_a_failed_tectonic_build_names_tectonic(tmp_path, monkeypatch):
    """'is Docker installed and running?' is useless advice when tectonic built."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "cv.tex").write_text("\\documentclass{article}", encoding="utf-8")
    monkeypatch.setattr(build_mod.shutil, "which", _installed("tectonic"))
    _, fake_run = _tectonic_run(work, rc=1, stderr="error: the XeTeX engine had an error")
    monkeypatch.setattr(build_mod.subprocess, "run", fake_run)

    with pytest.raises(BuildError, match="via tectonic"):
        build_cv(work, entry="cv.tex", engine="tectonic")


def test_a_stale_log_cannot_answer_for_a_build_that_left_none(tmp_path, monkeypatch):
    """Only tectonic writes a .log, and build dirs are reused per scope. Switch
    cv.engine to docker with pypdf missing and the previous tectonic run's log is
    still sitting there — _pages_from_log would read a page count off a PDF that
    no longer exists and report it as this build's."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "cv.tex").write_text("\\documentclass{article}", encoding="utf-8")
    (work / "cv.log").write_text("Output written on cv.xdv (7 pages, 1 bytes).", encoding="utf-8")
    monkeypatch.setattr(build_mod.shutil, "which", _installed("docker"))
    # Unreadable by pypdf and by the regex, so the .log is the only candidate.
    monkeypatch.setattr(build_mod, "_pages_from_pdf", lambda _p: None)

    def fake_run(*_a, **_k):
        (work / "cv.pdf").write_bytes(b"%PDF-1.5\n<compressed>\n%%EOF")
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(build_mod.subprocess, "run", fake_run)
    assert build_cv(work, entry="cv.tex", engine="docker").pages is None


def test_pages_from_log(tmp_path):
    log = tmp_path / "cv.log"
    log.write_text("Output written on cv.pdf (1 page, 36973 bytes).", encoding="utf-8")
    assert _pages_from_log(log) == 1


def test_pages_from_log_reads_tectonics_xdv_wording(tmp_path):
    """Tectonic goes through an intermediate and logs 'Output written on cv.xdv',
    not 'cv.pdf'. The regex wildcards the filename, so it matches — this pins
    that, because the extension is the kind of detail a tightening would break."""
    log = tmp_path / "cv.log"
    log.write_text("Output written on cv.xdv (2 pages, 33068 bytes).", encoding="utf-8")
    assert _pages_from_log(log) == 2


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
    monkeypatch.setattr(build_mod.shutil, "which", _installed("docker"))

    # The PDF has to appear *because the build ran*, the way docker produces it.
    # Pre-creating it and stubbing the run as a no-op would pass even if the
    # build did nothing at all.
    def fake_run(*_a, **_k):
        (work / "cv.pdf").write_bytes(b"%PDF-1.5\n<compressed object streams>\n%%EOF")
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(build_mod.subprocess, "run", fake_run)
    assert build_cv(work, entry="cv.tex", engine="docker").pages is None


def test_a_failed_build_does_not_hand_back_the_previous_pdf(tmp_path, monkeypatch):
    """The image runs `xelatex …; mv …; rm …` with no `set -e`, so LaTeX can fail
    and the container still exits 0. Then the only evidence of failure is the
    missing PDF — which last successful build's file would happily answer for,
    turning a broken build into a silent success serving stale content."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "cv.tex").write_text("\\documentclass{article}", encoding="utf-8")
    (work / "cv.pdf").write_bytes(b"%PDF-1.5\nyesterday\n%%EOF")
    monkeypatch.setattr(build_mod.shutil, "which", _installed("docker"))
    monkeypatch.setattr(
        build_mod.subprocess,
        "run",
        lambda *a, **k: type(
            "P", (), {"returncode": 0, "stdout": "! Undefined cs", "stderr": ""}
        )(),
    )
    with pytest.raises(BuildError):
        build_cv(work, entry="cv.tex", engine="docker")


def test_the_entry_file_reaches_the_container(tmp_path, monkeypatch):
    """The image's built-in command hardcodes cv.tex, so `entry` only means
    something if we spell the command out ourselves."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "cover_letter.tex").write_text("\\documentclass{article}", encoding="utf-8")
    seen: list[list[str]] = []
    monkeypatch.setattr(build_mod.shutil, "which", _installed("docker"))

    def fake_run(cmd, **_k):
        seen.append(cmd)
        (work / "cover_letter.pdf").write_bytes(b"%PDF-1.5\n<</Type /Page>>\n%%EOF")
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(build_mod.subprocess, "run", fake_run)
    result = build_cv(work, entry="cover_letter.tex", engine="docker")
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
    monkeypatch.setattr(build_mod.shutil, "which", _installed("docker"))

    def fake_run(cmd, **_k):
        seen.append(cmd)
        (work / "my cv.pdf").write_bytes(b"%PDF-1.5\n<</Type /Page>>\n%%EOF")
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(build_mod.subprocess, "run", fake_run)
    build_cv(work, entry="my cv.tex", engine="docker")
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
