"""Compile a LaTeX CV project to PDF, with two interchangeable engines.

**tectonic** (default) is a single static binary that fetches the TeX packages a
document actually asks for and caches them: ~10 MB to install on Linux plus a
~50 MB cache, and nothing to start before building. **docker** runs the
`csmith/awesome-cv-builder` image, which is 3.18 GB, has to be pulled, and needs
a daemon running. Both drive xelatex over the same generated `.tex` and produce
the same PDF -- verified on both templates, including that Vietnamese diacritics
survive into the text layer, which is the failure mode that would matter and the
one that fails *silently* (see `jobpilot/cv/CLAUDE.md`).

Docker is kept as the fallback rather than deleted: it is the engine every PDF in
this repo's history was built with, so it stays the reference when a build looks
wrong. `cv.engine` picks (`auto` prefers tectonic and falls back to docker).

The Docker path spells the command out rather than using the image's built-in
one, which hardcodes `cv.tex`:

    /bin/sh -c 'DIR=$(mktemp -d); xelatex -output-directory=$DIR cv.tex; \
                mv $DIR/cv.pdf .; rm -rf $DIR'

so passing ``entry="cover_letter.tex"`` and letting the image do its thing would
rebuild the CV and then fail looking for a PDF nobody asked it to make. Spelling
it out is the only way ``entry`` means anything; the default path renders the
same command the image ships with.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from jobpilot.config import get_config

#: Engines we know how to drive, in the order ``auto`` tries them.
ENGINES = ("tectonic", "docker")

_INSTALL_HINT = {
    "tectonic": (
        "one static binary, no daemon: see https://tectonic-typesetting.github.io/install.html "
        "(Linux/macOS: `curl --proto '=https' --tlsv1.2 -fsSL https://drop-sh.fullyjustified.net "
        "| sh`; or download a release from "
        "https://github.com/tectonic-typesetting/tectonic/releases and put it on PATH). "
        "Point cv.tectonic_bin at it if you keep it somewhere off PATH"
    ),
    "docker": (
        "install Docker, start the daemon, then `docker pull csmith/awesome-cv-builder` "
        "(~3.2 GB)"
    ),
}


class BuildError(RuntimeError):
    """Raised when the LaTeX build fails or produces no PDF."""


def _user_args() -> list[str]:
    """``-u uid:gid`` on POSIX, nothing on Windows.

    The container writes ``cv.pdf`` into the bind mount as whoever it runs as.
    On Linux that is root, so the PDF lands owned by root inside a directory
    owned by the service account — and the *next* build dies in ``pdf.unlink()``
    with EACCES, leaving stale output behind. Docker Desktop on Windows and
    macOS translates ownership at the mount layer, where passing a Linux uid
    means nothing (and on Windows there is no ``os.getuid`` to pass), so this is
    deliberately POSIX-only. README.md has carried both invocations all along;
    only the Windows one was ever wired up.
    """
    if not hasattr(os, "getuid"):  # Windows
        return []
    return ["-u", f"{os.getuid()}:{os.getgid()}"]


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

    ``auto`` prefers tectonic purely on install cost -- the two produce the same
    PDF, so there is nothing else to choose on.

    Returns an *absolute* executable rather than the configured name, because
    the tectonic build runs with ``cwd`` set to the build dir. A relative
    ``cv.tectonic_bin`` like ``./tools/tectonic`` would otherwise be looked up
    here against the process's directory (found) and executed against the build
    dir (not found) -- an exec failure some directories away from anything that
    explains it.

    The ``abspath`` is doing that work, not ``shutil.which``: given a string with
    a directory component, ``which`` checks that path directly and hands back
    *the string as passed*, still relative. Mocking ``which`` to return an
    absolute path therefore proves nothing about this, which is why the test for
    it puts a real file at a real relative path.
    """
    cfg = get_config().cv
    choice = (engine or cfg.engine or "auto").strip().lower()
    if choice not in ("auto", *ENGINES):
        raise BuildError(
            f"unknown cv.engine {choice!r} — expected one of: auto, " + ", ".join(ENGINES)
        )

    binary = tectonic_bin or cfg.tectonic_bin
    # shutil.which also accepts a path with a directory component, so
    # cv.tectonic_bin works as either a command name or a path.
    found = {"tectonic": shutil.which(binary), "docker": shutil.which("docker")}

    if choice != "auto":
        if not found[choice]:
            other = "docker" if choice == "tectonic" else "tectonic"
            raise BuildError(
                f"{choice} not found on PATH (cv.engine = {choice!r}) — "
                f"{_INSTALL_HINT[choice]}. Or set cv.engine to {other!r} or 'auto'."
            )
        return choice, os.path.abspath(found[choice])

    for name in ENGINES:
        if found[name]:
            return name, os.path.abspath(found[name])
    raise BuildError(
        "no LaTeX engine found — a CV cannot be built without one of:\n"
        f"  tectonic (recommended) — {_INSTALL_HINT['tectonic']}\n"
        f"  docker (fallback) — {_INSTALL_HINT['docker']}\n"
        "cv.engine selects between them (auto|tectonic|docker)."
    )


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

    (The Docker builder's xelatex log is unreliable — it can report '1 page' for a
    2-page PDF — so the PDF itself is the source of truth.)
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


def _script(entry: str) -> str:
    """The image's own command, with the entry file made explicit.

    xelatex writes to a temp dir so a failed run leaves no half-written PDF next
    to the source for the caller to mistake for a success.
    """
    stem = Path(entry).stem
    # Quoted even though every caller passes a repo constant: this string is a
    # shell command, and the moment an entry has a space in it an unquoted one
    # splits into two tokens and xelatex reports a missing file that isn't the
    # one you named.
    return (
        f"DIR=$(mktemp -d); xelatex -output-directory=$DIR {shlex.quote(entry)}; "
        f"mv $DIR/{shlex.quote(stem + '.pdf')} .; rm -rf $DIR"
    )


@dataclass(frozen=True)
class _Invocation:
    """One engine's command line, plus the directory it must run from."""

    cmd: list[str] = field(default_factory=list)
    cwd: Path | None = None


def _docker_invocation(work_dir: Path, entry: str, image: str | None) -> _Invocation:
    """Unchanged from before there were two engines — this is the fallback path."""
    image = image or get_config().cv.docker_image
    mount = f"{work_dir}:/work"
    return _Invocation([
        "docker", "run", "--rm",
        *_user_args(),
        "-v", mount,
        image, "/bin/sh", "-c", _script(entry),
    ])  # fmt: skip


def _tectonic_invocation(work_dir: Path, entry: str, binary: str) -> _Invocation:
    """Run in ``work_dir``, which is what makes the relative paths resolve.

    The generated project reaches its sections as ``\\input{resume/...}`` and its
    fonts as ``Path=fonts/``, both relative to the working directory — Docker got
    that from the bind mount, tectonic gets it from ``cwd``. ``binary`` is the
    path :func:`resolve_engine` already resolved, for the same reason.

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
    image: str | None = None,
    timeout: int = 300,
    engine: str | None = None,
) -> BuildResult:
    """Build ``entry`` in ``work_dir``; see :func:`resolve_engine` for the choice.

    ``image`` names the Docker image and is ignored when tectonic runs, which is
    the default — pass ``engine="docker"`` alongside it to be sure it applies.
    """
    work_dir = Path(work_dir).resolve()
    stem = Path(entry).stem
    if not (work_dir / entry).is_file():
        raise BuildError(f"entry not found: {work_dir / entry}")

    engine, binary = resolve_engine(engine)
    pdf = work_dir / f"{stem}.pdf"
    log = work_dir / f"{stem}.log"
    # Drop the previous PDF first. The Docker image's command is
    # `xelatex …; mv …; rm …` with no `set -e`, so a LaTeX error still exits 0
    # (the trailing `rm` decides the status) and the only tell that the build
    # failed is the missing PDF — which yesterday's file would answer for. That
    # reports success and hands back stale content, the worst of the two failure
    # modes. Tectonic does set a real exit code, but the check costs nothing and
    # a build dir is shared by both engines.
    pdf.unlink(missing_ok=True)
    # The log goes too, and for a sharper reason: only tectonic writes one, so a
    # log left by an earlier tectonic build would still be sitting here during a
    # later docker build. With pypdf missing, _pages_from_log would then read a
    # page count off a PDF that no longer exists and report it as this build's.
    log.unlink(missing_ok=True)

    run = (
        _tectonic_invocation(work_dir, entry, binary)
        if engine == "tectonic"
        else _docker_invocation(work_dir, entry, image)
    )
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
        # Which engine failed decides what the fix is, so it leads the message:
        # "is Docker running?" is useless advice when tectonic did the building.
        tail = (proc.stdout or "")[-1500:] + "\n" + (proc.stderr or "")[-1500:]
        raise BuildError(f"LaTeX build failed via {engine} (rc={proc.returncode}).\n{tail}")

    # None when nothing could read it — "unknown" and "zero pages" are different
    # claims, and a CV that built fine should not be badged as 0 pages in red.
    # That is the live failure mode when pypdf is missing: xelatex writes its PDF
    # with compressed object streams, so the regex fallback finds no /Type /Page.
    # Docker leaves no .log to fall back to; tectonic does, so under tectonic a
    # missing pypdf degrades to a real count instead of to "unknown".
    pages = _pages_from_pdf(pdf) or _pages_from_log(log)
    # Tectonic reports on stderr, Docker on stdout; a tail of the wrong stream is
    # an empty string that looks like a build with nothing to say.
    chatter = proc.stderr if engine == "tectonic" else proc.stdout
    return BuildResult(pdf=pdf, pages=pages, log_tail=(chatter or "")[-500:], engine=engine)
