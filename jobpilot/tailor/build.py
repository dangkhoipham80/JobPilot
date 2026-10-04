"""Compile a LaTeX CV project to PDF with tectonic.

tectonic is a single static binary that drives xelatex, fetches the TeX packages
a document actually asks for and caches them: ~10 MB to install plus a ~50 MB
cache, nothing to start before building, and binaries for x86-64 and ARM64.

There used to be a second engine, the `csmith/awesome-cv-builder` Docker image
(3.18 GB, a daemon, x86-64 only). It was removed on 2026-10-04: tectonic had
been the default since cv-C, produced the same PDFs on both templates, and the
host that runs JobPilot has no Docker at all — so the fallback was a path
nobody exercised, and the rule "build every `.cls` change with both engines"
could no longer be followed. A config still saying ``cv.engine: docker`` gets a
:class:`BuildError` that says so, rather than a confusing lookup failure.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from jobpilot.config import REPO_ROOT, get_config

#: Engines we know how to drive. ``auto`` means the first one.
ENGINES = ("tectonic",)

#: Where a tectonic binary is looked for when it is not on PATH, relative to the
#: repo. Checked *after* PATH, so a system install always wins.
#:
#: This exists so nobody has to write an absolute path into
#: ``cv.tectonic_bin``. That setting works, but it names one machine: the file
#: it points at does not exist on anyone else's checkout, and the failure is
#: quiet until the first build fails. Dropping the binary in ``tools/`` is the same
#: gesture on every OS, needs no config at all, and travels with the checkout
#: rather than with one laptop's PATH.
TOOLS_DIR = "tools"

_INSTALL_HINT = (
    "one static binary, no daemon: see https://tectonic-typesetting.github.io/install.html "
    "(macOS: `brew install tectonic`; Linux/macOS: `curl --proto '=https' --tlsv1.2 -fsSL "
    "https://drop-sh.fullyjustified.net | sh`; or download a release from "
    "https://github.com/tectonic-typesetting/tectonic/releases). Put it on PATH, or drop "
    f"it in {TOOLS_DIR}/ inside the repo, or point cv.tectonic_bin at it"
)


def _find_executable(command: str) -> str | None:
    """``shutil.which``, then the repo's ``tools/`` directory.

    ``which`` covers a system install and an absolute path in the config alike.
    The ``tools/`` fallback covers the case that is otherwise fiddly on Windows:
    a downloaded binary that nobody wants to put on PATH.
    """
    found = shutil.which(command)
    if found:
        return found
    # Only a bare command name gets the fallback. A configured path that does
    # not resolve is a mistake worth reporting, not one to paper over by
    # running some other file that happens to share its name.
    if os.path.dirname(command):
        return None
    candidate = REPO_ROOT / TOOLS_DIR / command
    for path in (candidate, candidate.with_suffix(".exe")):
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


class BuildError(RuntimeError):
    """Raised when the LaTeX build fails or produces no PDF."""


@dataclass
class BuildResult:
    pdf: Path
    #: None when the page count could not be established (see ``build_cv``).
    pages: int | None
    log_tail: str = ""
    #: Which engine produced this PDF. Appended with a default so existing
    #: callers and their positional construction keep working.
    engine: str = ""


def resolve_engine(engine: str | None = None, tectonic_bin: str | None = None) -> tuple[str, str]:
    """The engine to build with and the executable to run it, or raise saying how
    to get one.

    Returns an *absolute* executable rather than the configured name, because
    the build runs with ``cwd`` set to the build dir. A relative
    ``cv.tectonic_bin`` like ``./tools/tectonic`` would otherwise be looked up
    here against the process's directory (found) and executed against the build
    dir (not found) -- an exec failure some directories away from anything that
    explains it.

    The ``abspath`` is doing that work, not ``shutil.which``: given a string with
    a directory component, ``which`` checks that path directly and hands back
    *the string as passed*, still relative. Mocking ``which`` to return an
    absolute path therefore proves nothing about this, which is why the test for
    it puts a real file at a real relative path.

    Tectonic is looked up with :func:`_find_executable`, which also checks the
    repo's ``tools/`` directory, so a downloaded binary needs no config entry.
    """
    cfg = get_config().cv
    choice = (engine or cfg.engine or "auto").strip().lower()
    if choice == "docker":
        raise BuildError(
            "cv.engine is 'docker', but the Docker LaTeX engine was removed — set cv.engine "
            f"to 'auto' (or delete the line) and install tectonic: {_INSTALL_HINT}"
        )
    if choice not in ("auto", *ENGINES):
        raise BuildError(
            f"unknown cv.engine {choice!r} — expected one of: auto, " + ", ".join(ENGINES)
        )

    # shutil.which also accepts a path with a directory component, so
    # cv.tectonic_bin works as either a command name or a path.
    found = _find_executable(tectonic_bin or cfg.tectonic_bin)
    if not found:
        raise BuildError(
            f"no LaTeX engine found — a CV cannot be built without tectonic: {_INSTALL_HINT}"
        )
    return "tectonic", os.path.abspath(found)


def _pages_from_log(log_path: Path) -> int | None:
    """xelatex writes e.g. 'Output written on cv.pdf (1 page, 36973 bytes).'

    Tectonic reaches the PDF through an intermediate and logs ``Output written on
    cv.xdv (2 pages, ...)`` instead — same sentence, different extension. The
    filename is a wildcard here, so both match; that is load-bearing rather than
    incidental, hence the test pinning the .xdv wording.
    """
    if not log_path.is_file():
        return None
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"Output written on .*?\((\d+)\s+page", text)
    return int(m.group(1)) if m else None


def _pages_from_pdf(pdf_path: Path) -> int | None:
    """Authoritative count via pypdf; fall back to regex if unavailable/unparseable.

    The PDF is the source of truth rather than the log: an xelatex log has been
    seen reporting '1 page' for a 2-page PDF.
    """
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(pdf_path)).pages)
    except ImportError:
        pass
    except Exception:
        pass  # malformed/edge PDF — try regex below

    data = pdf_path.read_bytes()
    pages = len(re.findall(rb"/Type\s*/Page(?![s])", data))
    if pages:
        return pages
    counts = [int(c) for c in re.findall(rb"/Count\s+(\d+)", data)]
    return max(counts) if counts else None


def page_summary(pages: int | None) -> str:
    """One line about the page budget, for the CLI. A CV should be one page."""
    if pages is None:
        return "page count unknown — pip install -e '.[cv]' for pypdf"
    return "OK: 1 page" if pages == 1 else f"WARNING: {pages} pages (CV should be 1)"


@dataclass(frozen=True)
class _Invocation:
    """One engine's command line, plus the directory it must run from."""

    cmd: list[str] = field(default_factory=list)
    cwd: Path | None = None


def _tectonic_invocation(work_dir: Path, entry: str, binary: str) -> _Invocation:
    """Run in ``work_dir``, which is what makes the relative paths resolve.

    The generated project reaches its sections as ``\\input{resume/...}`` and its
    fonts as ``Path=fonts/``, both relative to the working directory, which
    tectonic gets from ``cwd``. ``binary`` is the path :func:`resolve_engine`
    already resolved, for the same reason.

    ``--untrusted`` disables \\write18 for the same reason ``compile.check_override``
    validates paths: raw-LaTeX overrides come from a text box, and a `.tex` file
    from a text box is input, not code we vouched for. ``--keep-logs`` leaves the
    `.log` that :func:`_pages_from_log` needs when pypdf is missing.
    """
    cmd = [
        binary,
        "-X", "compile",
        "--untrusted",
        "--keep-logs",
        "--outdir", str(work_dir),
        entry,
    ]  # fmt: skip
    return _Invocation(cmd, cwd=work_dir)


def build_cv(
    work_dir: Path | str,
    entry: str = "cv.tex",
    timeout: int = 300,
    engine: str | None = None,
) -> BuildResult:
    """Build ``entry`` in ``work_dir``; see :func:`resolve_engine`."""
    work_dir = Path(work_dir).resolve()
    stem = Path(entry).stem
    if not (work_dir / entry).is_file():
        raise BuildError(f"entry not found: {work_dir / entry}")

    engine, binary = resolve_engine(engine)
    pdf = work_dir / f"{stem}.pdf"
    log = work_dir / f"{stem}.log"
    # Drop the previous PDF and log first. A build that fails without a PDF
    # must not find yesterday's file answering for it — that reports success
    # and hands back stale content, the worst of the failure modes — and with
    # pypdf missing, a stale log would supply a page count for a PDF that no
    # longer exists.
    pdf.unlink(missing_ok=True)
    log.unlink(missing_ok=True)

    run = _tectonic_invocation(work_dir, entry, binary)
    try:
        proc = subprocess.run(
            run.cmd,
            cwd=str(run.cwd) if run.cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - env dependent
        raise BuildError(f"LaTeX build timed out after {timeout}s ({engine})") from exc
    except OSError as exc:
        # resolve_engine() found the executable a moment ago, so reaching here
        # means it went away, is not executable, or is the wrong architecture.
        # Without this the caller gets a bare OSError from deep inside a build
        # helper; the API route turns that into a naked 500.
        raise BuildError(f"could not run {engine} ({run.cmd[0]}): {exc}") from exc

    if proc.returncode != 0 or not pdf.is_file():
        tail = (proc.stdout or "")[-1500:] + "\n" + (proc.stderr or "")[-1500:]
        raise BuildError(f"LaTeX build failed via {engine} (rc={proc.returncode}).\n{tail}")

    # None when nothing could read it — "unknown" and "zero pages" are different
    # claims, and a CV that built fine should not be badged as 0 pages in red.
    # That is the live failure mode when pypdf is missing: xelatex writes its PDF
    # with compressed object streams, so the regex fallback finds no /Type /Page;
    # the .log tectonic keeps (--keep-logs) then supplies a real count.
    pages = _pages_from_pdf(pdf) or _pages_from_log(log)
    # Tectonic reports on stderr; a tail of stdout is an empty string that looks
    # like a build with nothing to say.
    return BuildResult(pdf=pdf, pages=pages, log_tail=(proc.stderr or "")[-500:], engine=engine)
