"""Employer logos: where they come from, and the copy the dashboard serves.

Two sources, in order:

1. **What a board said** — ``companies.logo_url``, from the JSON-LD
   ``hiringOrganization.logo`` on the posting (TopCV, ITviec). The board's own
   picture of the employer.
2. **The employer's own site** — ``companies.domain`` (set by a source that knows
   it, or typed in on the Companies page): its homepage's ``apple-touch-icon`` /
   ``icon`` link, then ``/favicon.ico``. A third-party favicon service would be
   one request instead of two, but the one checked (Google's) is disallowed by
   its robots.txt, and every request here goes through the same robots check as
   the crawler.

Everything is downloaded once and served from disk (``/api/logos/<hash>.<ext>``):
the dashboard never hotlinks a board's CDN, so a page of jobs does not tell a
dozen hosts what you are looking at, and a logo that moves upstream does not
break here. The page shows initials when there is nothing — that is a UI
fallback, never a stored "logo".

Only real raster images are kept — PNG, JPEG, GIF, WebP, ICO, sniffed from the
bytes, at most ``MAX_BYTES``. **SVG is refused**: it is a document that can carry
script, and it would be served from the dashboard's own origin.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from jobpilot.store.models import Company
from jobpilot.timeutil import vn_now

log = logging.getLogger(__name__)

MAX_BYTES = 512 * 1024
#: A company whose logo could not be found is retried after this long.
RETRY_AFTER = timedelta(days=7)
#: Served filenames: content hash + extension. The route accepts nothing else.
FILE_RE = re.compile(r"^[0-9a-f]{20}\.(png|jpg|gif|webp|ico)$")

_DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_LINK_RE = re.compile(r"<link\b[^>]*>", re.I)
_ATTR_RE = re.compile(r'([a-z-]+)\s*=\s*("([^"]*)"|\'([^\']*)\'|([^\s>]+))', re.I)

#: (status, content-type, body). Injected in tests; real requests otherwise.
Getter = Callable[[str], tuple[int, str, bytes]]


def clean_domain(text: str | None) -> str | None:
    """``"https://www.Acme.com/careers"`` → ``"acme.com"``; ``None`` if not a host."""
    value = (text or "").strip().lower()
    if not value:
        return None
    host = urlsplit(value if "//" in value else f"//{value}").hostname or ""
    host = host.removeprefix("www.")
    return host if _DOMAIN_RE.match(host) else None


def logo_dir() -> Path:
    from jobpilot.config import REPO_ROOT, get_config

    return REPO_ROOT / get_config().cv.out_dir / "logos"


def sniff(data: bytes) -> str | None:
    """The extension of a raster image, from its bytes; ``None`` for anything else."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:4] == b"\x00\x00\x01\x00":
        return "ico"
    return None


def icon_links(html: str, base_url: str) -> list[str]:
    """Icon URLs a homepage declares, best first: touch icons, then the largest icon."""
    ranked: list[tuple[int, str]] = []
    for tag in _LINK_RE.findall(html[:200_000]):
        attrs = {m.group(1).lower(): m.group(3) or m.group(4) or m.group(5) or "" for m in _ATTR_RE.finditer(tag)}
        rel = attrs.get("rel", "").lower()
        href = attrs.get("href", "").strip()
        if not href or "icon" not in rel or "mask-icon" in rel:
            continue
        if href.lower().endswith(".svg") or "svg" in attrs.get("type", "").lower():
            continue  # refused anyway — don't spend a request on it
        size = max((int(n) for n in re.findall(r"(\d+)x\d+", attrs.get("sizes", ""))), default=0)
        score = 1000 + size if "apple-touch-icon" in rel else size or 16
        ranked.append((score, urljoin(base_url, href)))
    ranked.sort(key=lambda pair: -pair[0])
    return [url for _, url in ranked]


def _http_get(url: str) -> tuple[int, str, bytes]:  # pragma: no cover - network
    import httpx

    from jobpilot.crawler.fetch import DEFAULT_USER_AGENT

    with httpx.Client(
        timeout=15, follow_redirects=True, headers={"User-Agent": DEFAULT_USER_AGENT}
    ) as client:
        with client.stream("GET", url) as resp:
            body = b""
            for chunk in resp.iter_bytes():
                body += chunk
                if len(body) > MAX_BYTES:
                    break
            return resp.status_code, resp.headers.get("content-type", ""), body


@dataclass
class Fetcher:
    """Robots-checked GETs for logo hunting. One instance per batch (robots cache)."""

    get: Getter = _http_get
    respect_robots: bool = True

    def __post_init__(self) -> None:
        self._robots = None
        if self.respect_robots:
            from jobpilot.crawler.fetch import DEFAULT_USER_AGENT
            from jobpilot.crawler.robots import RobotsPolicy

            self._robots = RobotsPolicy(DEFAULT_USER_AGENT)

    def fetch(self, url: str) -> tuple[int, str, bytes] | None:
        if not url.startswith(("https://", "http://")):
            return None
        if self._robots is not None and not self._robots.allowed(url):
            log.info("logo: robots.txt disallows %s", url)
            return None
        try:
            return self.get(url)
        except Exception as exc:  # network — the next candidate may work
            log.info("logo: %s failed (%s)", url, exc)
            return None

    def image(self, url: str) -> tuple[bytes, str] | None:
        got = self.fetch(url)
        if not got or got[0] >= 400:
            return None
        data = got[2]
        ext = sniff(data)
        if ext is None or len(data) > MAX_BYTES or len(data) < 64:
            return None
        return data, ext

    def candidates(self, company: Company) -> list[str]:
        out = [company.logo_url] if company.logo_url else []
        if company.domain:
            home = f"https://{company.domain}/"
            got = self.fetch(home)
            if got and got[0] < 400 and "html" in got[1]:
                out += icon_links(got[2].decode("utf-8", "ignore"), home)
            out.append(urljoin(home, "/favicon.ico"))
        return out


def save(data: bytes, ext: str, directory: Path | None = None) -> str:
    """Write the image under its content hash; the same picture is one file."""
    name = f"{hashlib.sha256(data).hexdigest()[:20]}.{ext}"
    folder = directory or logo_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    if not path.exists():
        path.write_bytes(data)
    return name


def refresh_one(company: Company, fetcher: Fetcher, directory: Path | None = None) -> bool:
    """Try every candidate for ``company``; record the attempt either way."""
    company.logo_checked_at = vn_now()
    for url in fetcher.candidates(company):
        got = fetcher.image(url)
        if got:
            company.logo_file = save(*got, directory=directory)
            return True
    return False


@dataclass
class LogoResult:
    tried: int = 0
    found: int = 0


def refresh_due(
    session: Session,
    *,
    limit: int = 25,
    fetcher: Fetcher | None = None,
    directory: Path | None = None,
    now: datetime | None = None,
) -> LogoResult:
    """Fetch logos for companies that have a source and no logo, oldest attempt first.

    Bounded by ``limit`` per call so a crawl does not turn into a logo crawl:
    the backlog clears over a few runs.
    """
    now = now or vn_now()
    fetcher = fetcher or Fetcher()
    due = session.scalars(
        select(Company)
        .where(
            Company.logo_file.is_(None),
            or_(Company.logo_url.is_not(None), Company.domain.is_not(None)),
            or_(Company.logo_checked_at.is_(None), Company.logo_checked_at < now - RETRY_AFTER),
        )
        .order_by(Company.logo_checked_at.is_not(None), Company.logo_checked_at, Company.id)
        .limit(limit)
    ).all()
    result = LogoResult()
    for company in due:
        result.tried += 1
        if refresh_one(company, fetcher, directory):
            result.found += 1
    session.flush()
    return result


def logo_path(name: str | None) -> str | None:
    """The URL the dashboard loads a cached logo from."""
    return f"/api/logos/{name}" if name and FILE_RE.match(name) else None
