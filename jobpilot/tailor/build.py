"""Compile an Awesome-CV LaTeX project to PDF.

Two backends, because the two machines this runs on cannot share one:

* ``docker`` — the `csmith/awesome-cv-builder` image (see README.md), which
  mounts `/work` and runs xelatex. What the laptop uses.
* ``local``  — xelatex already on PATH. What the ARM server uses, because that
  image is **amd64-only** (single manifest, verified against the registry) and
  there is no arm64 build of it. TeX Live itself is packaged for arm64, so the
  engine is available even where the image is not.

Both produce the same PDF from the same inputs; the tests pin that. The backend
is chosen by ``cv.build_backend`` and never silently swapped underneath you —
a CV that quietly built through a different toolchain than the one you reviewed
is exactly the "reports success, hands back something else" failure this file
already guards against elsewhere.

Either way this wrapper reports the page count (from the PDF, with the xelatex
`.log` as fallback).

The image's built-in command hardcodes `cv.tex`:

    /bin/sh -c 'DIR=$(mktemp -d); xelatex -output-directory=$DIR cv.tex; \
                mv $DIR/cv.pdf .; rm -rf $DIR'

so passing ``entry="cover_letter.tex"`` and letting the image do its thing would
rebuild the CV and then fail looking for a PDF nobody asked it to make. We spell
the command out instead, which is the only way ``entry`` means anything. The
default path renders the same command the image ships with.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from jobpilot.config import get_config


class BuildError(RuntimeError):
    """Raised when the LaTeX build fails or produces no PDF."""


#: What ``cv.build_backend`` accepts. ``auto`` resolves at build time.
BACKENDS = ("auto", "docker", "local")


def resolve_backend(configured: str | None = None) -> str:
    """Decide which toolchain compiles this build. Returns 'docker' or 'local'.

    ``auto`` prefers Docker when its CLI is present, which keeps the machine
    that has been building CVs all along building them exactly as before, and
    falls to the local engine otherwise — the server, where Docker is not
    installed at all.

    It deliberately does **not** fall back when Docker is present but broken
    (daemon stopped, image missing). Those are one command away from fixed, and
    silently switching toolchains to paper over them would mean the PDF you
    approve and the PDF that gets sent were produced by different software
    without anyone being told. The error says which backend was chosen and how
    to choose the other one.
    """
    configured = (configured or get_config().cv.build_backend or "auto").lower()
    if configured not in BACKENDS:
        raise BuildError(
            f"cv.build_backend is {configured!r} — expected one of {', '.join(BACKENDS)}"
        )
    if configured != "auto":
        return configured

    if shutil.which("docker"):
        return "docker"
    if shutil.which("xelatex"):
        return "local"
    raise BuildError(
        "no LaTeX toolchain found: neither `docker` nor `xelatex` is on PATH. "
        "Install Docker Desktop, or a TeX Live with xelatex and set "
        "cv.build_backend: local"
    )


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


def _pages_from_log(log_path: Path) -> int | None:
    """xelatex writes e.g. 'Output written on cv.pdf (1 page, 36973 bytes).'"""
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


def _docker_run(work_dir: Path, entry: str, image: str, timeout: int):
    if shutil.which("docker") is None:
        raise BuildError(
            "cv.build_backend is 'docker' but docker is not on PATH. Install it, "
            "or use a local TeX Live and set cv.build_backend: local"
        )
    cmd = [
        "docker", "run", "--rm",
        *_user_args(),
        "-v", f"{work_dir}:/work",
        image, "/bin/sh", "-c", _script(entry),
    ]  # fmt: skip
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _local_run(work_dir: Path, entry: str, out_dir: Path, timeout: int):
    """Run the xelatex already installed on this machine.

    ``cwd`` is the build directory because that is where ``sync_assets`` put
    ``awesome-cv.cls``, ``fontawesome.sty`` and ``fonts/``; xelatex resolves
    those relative to where it runs, not to the file it is given.

    ``-interaction=nonstopmode`` matters more than it looks: without it a
    missing package stops at an interactive prompt, and a build running under a
    queue worker with no terminal would hang there until the timeout instead of
    reporting the actual error.
    """
    if shutil.which("xelatex") is None:
        raise BuildError(
            "cv.build_backend is 'local' but xelatex is not on PATH — install "
            "TeX Live (see DEPLOY.md), or use Docker and set cv.build_backend: docker"
        )
    cmd = [
        "xelatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={out_dir}",
        entry,
    ]
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, cwd=str(work_dir)
    )


def build_cv(
    work_dir: Path | str,
    entry: str = "cv.tex",
    image: str | None = None,
    timeout: int = 300,
    backend: str | None = None,
) -> BuildResult:
    work_dir = Path(work_dir).resolve()
    stem = Path(entry).stem
    if not (work_dir / entry).is_file():
        raise BuildError(f"entry not found: {work_dir / entry}")

    chosen = resolve_backend(backend)
    pdf = work_dir / f"{stem}.pdf"
    log = work_dir / f"{stem}.log"
    # Drop the previous PDF first. The image's command is `xelatex …; mv …; rm …`
    # with no `set -e`, so a LaTeX error still exits 0 (the trailing `rm` decides
    # the status) and the only tell that the build failed is the missing PDF —
    # which yesterday's file would answer for. That reports success and hands
    # back stale content, the worst of the two failure modes.
    # The log goes too, or a failed build reports the *previous* page count.
    pdf.unlink(missing_ok=True)
    log.unlink(missing_ok=True)

    try:
        if chosen == "docker":
            proc = _docker_run(work_dir, entry, image or get_config().cv.docker_image, timeout)
        else:
            # Same reason the image builds into a temp dir: a run that dies
            # part-way leaves no half-written PDF beside the source for the
            # caller to mistake for a success.
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                proc = _local_run(work_dir, entry, out, timeout)
                # Move both back before the temp dir goes away. The log is kept
                # (the image discards its own), which is the difference between
                # a LaTeX error you can read and a return code you can't.
                for produced, target in ((out / f"{stem}.pdf", pdf), (out / f"{stem}.log", log)):
                    if produced.is_file():
                        shutil.move(str(produced), target)
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - env dependent
        raise BuildError(f"LaTeX build timed out after {timeout}s ({chosen} backend)") from exc

    if proc.returncode != 0 or not pdf.is_file():
        tail = (proc.stdout or "")[-1500:] + "\n" + (proc.stderr or "")[-1500:]
        raise BuildError(f"LaTeX build failed (rc={proc.returncode}, {chosen} backend).\n{tail}")

    # None when nothing could read it — "unknown" and "zero pages" are different
    # claims, and a CV that built fine should not be badged as 0 pages in red.
    # That is the live failure mode when pypdf is missing: xelatex writes its PDF
    # with compressed object streams, so the regex fallback finds no /Type /Page,
    # and the builder image doesn't leave a .log behind either.
    pages = _pages_from_pdf(pdf) or _pages_from_log(work_dir / f"{stem}.log")
    return BuildResult(pdf=pdf, pages=pages, log_tail=(proc.stdout or "")[-500:])
