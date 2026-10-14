"""Employer logos: captured from boards, found from a domain, cached, served narrowly."""

from __future__ import annotations

from datetime import timedelta

import pytest

from jobpilot.api.deps import get_db
from jobpilot.api.main import app
from jobpilot.api.routes import companies as company_routes
from jobpilot.companies import logos
from jobpilot.companies.logos import Fetcher, clean_domain, icon_links, refresh_due, sniff
from jobpilot.companies.service import link_job
from jobpilot.config import get_secrets
from jobpilot.crawler.base import BaseScraper
from jobpilot.crawler.ratelimit import RateLimiter
from jobpilot.crawler.types import RawJob, SearchHit
from jobpilot.store.models import Company, Job
from jobpilot.tests.conftest import api_client
from jobpilot.timeutil import vn_now

AUTH = {"X-API-Token": get_secrets().jobpilot_api_token}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
SVG = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"


def _fetcher(routes: dict[str, tuple[int, str, bytes]]) -> Fetcher:
    calls: list[str] = []

    def get(url: str):
        calls.append(url)
        return routes.get(url, (404, "text/html", b""))

    f = Fetcher(get=get, respect_robots=False)
    f.calls = calls  # type: ignore[attr-defined]
    return f


@pytest.mark.parametrize(
    ("text", "domain"),
    [
        ("acme.com", "acme.com"),
        ("https://www.Acme.com/careers?x=1", "acme.com"),
        ("careers.acme.co.uk", "careers.acme.co.uk"),
        ("not a domain", None),
        ("", None),
        ("javascript:alert(1)", None),
    ],
)
def test_clean_domain(text, domain):
    assert clean_domain(text) == domain


def test_only_raster_images_are_accepted():
    assert sniff(PNG) == "png"
    assert sniff(b"\xff\xd8\xff\xe0" + b"0" * 70) == "jpg"
    assert sniff(SVG) is None  # a document that can carry script
    assert sniff(b"<html>not an image</html>") is None


def test_homepage_icons_are_ranked_touch_icon_first_and_svg_skipped():
    html = """
      <link rel="icon" href="/favicon-32.png" sizes="32x32">
      <link rel="icon" type="image/svg+xml" href="/logo.svg">
      <link rel='apple-touch-icon' href='https://cdn.acme.com/touch.png'>
      <link rel="mask-icon" href="/mask.png">
      <link rel="stylesheet" href="/a.css">
    """
    assert icon_links(html, "https://acme.com/") == [
        "https://cdn.acme.com/touch.png",
        "https://acme.com/favicon-32.png",
    ]


_seq = iter(range(10_000))


def _company(db, **kw) -> Company:
    c = Company(name="Acme", normalized_name=f"acme-{next(_seq)}", **kw)
    db.add(c)
    db.flush()
    return c


def test_the_boards_logo_comes_first_then_the_domain(session_factory, tmp_path):
    with session_factory() as db:
        board = _company(db, logo_url="https://cdn.board.example/acme.png", domain="acme.com")
        site = _company(db, domain="globex.com")
        nothing = _company(db, domain="initech.com")
        fetcher = _fetcher(
            {
                "https://cdn.board.example/acme.png": (200, "image/png", PNG),
                "https://globex.com/": (200, "text/html", b'<link rel="icon" href="/i.svg"><link rel="icon" href="/i.png">'),
                "https://globex.com/i.png": (200, "image/png", PNG + b"g"),
                "https://initech.com/favicon.ico": (200, "image/svg+xml", SVG),
            }
        )
        result = refresh_due(db, fetcher=fetcher, directory=tmp_path)

        assert (result.tried, result.found) == (3, 2)
        assert board.logo_file and (tmp_path / board.logo_file).read_bytes() == PNG
        assert "https://globex.com/i.svg" not in fetcher.calls  # never requested
        assert site.logo_file and site.logo_file != board.logo_file
        assert nothing.logo_file is None and nothing.logo_checked_at is not None


def test_a_company_without_a_logo_is_retried_weekly_not_every_crawl(session_factory, tmp_path):
    with session_factory() as db:
        _company(db, domain="initech.com", logo_checked_at=vn_now() - timedelta(days=1))
        _company(db)  # no source at all: never tried
        assert refresh_due(db, fetcher=_fetcher({}), directory=tmp_path).tried == 0
        later = vn_now() + timedelta(days=8)
        assert refresh_due(db, fetcher=_fetcher({}), directory=tmp_path, now=later).tried == 1


def test_a_job_hands_its_employer_the_logo_and_domain_without_overwriting(session_factory):
    with session_factory() as db:
        job = Job(
            id="topcv:1",
            source="topcv",
            title="Java Developer",
            company="Acme",
            payload={"company_logo": "https://cdn.board.example/a.png", "company_domain": "https://www.acme.com/"},
        )
        db.add(job)
        company = link_job(db, job)
        assert (company.logo_url, company.domain) == ("https://cdn.board.example/a.png", "acme.com")

        company.domain = "acme.vn"  # the user corrected it
        other = Job(id="itviec:2", source="itviec", title="Dev", company="Acme",
                    payload={"company_logo": "https://other.example/b.png", "company_domain": "acme.com"})
        db.add(other)
        link_job(db, other)
        assert (company.logo_url, company.domain) == ("https://cdn.board.example/a.png", "acme.vn")


class _OnePage(BaseScraper):
    source = "board"

    def search_url(self, query, page=1):
        return "https://board.example/search" if page == 1 else ""

    def parse_search(self, html):
        return [SearchHit(native_id="1", url="https://board.example/job/1", title="Java Dev")]

    def parse_detail(self, html, hit):
        return RawJob(source="board", native_id="1", url=hit.url, title=hit.title, company="Acme")


def test_the_crawl_reads_the_logo_off_any_boards_json_ld():
    detail = (
        '<script type="application/ld+json">{"@type": "JobPosting", "title": "Java Dev",'
        ' "hiringOrganization": {"@type": "Organization", "name": "Acme",'
        ' "logo": "https://cdn.board.example/acme.png"}}</script>'
    )
    pages = {"https://board.example/search": "<html/>", "https://board.example/job/1": detail}
    s = _OnePage(fetcher=pages.__getitem__, rate_limiter=RateLimiter(0, 0))
    [raw] = s.crawl("java", limit=5)
    assert raw.extra["company_logo"] == "https://cdn.board.example/acme.png"


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(session_factory, tmp_path, monkeypatch):
    monkeypatch.setattr(logos, "logo_dir", lambda: tmp_path)
    monkeypatch.setattr(
        company_routes,
        "get_logo_fetcher",
        lambda: _fetcher({"https://acme.com/favicon.ico": (200, "image/x-icon", b"\x00\x00\x01\x00" + b"i" * 80)}),
    )

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    with session_factory() as db:
        db.add(Company(id=1, name="Acme", normalized_name="acme"))
        db.commit()
    app.dependency_overrides[get_db] = override_get_db
    yield api_client(app)
    app.dependency_overrides.clear()


def test_setting_a_domain_fetches_the_logo_and_serves_it_without_the_token(client):
    r = client.patch("/companies/1", json={"domain": "https://www.acme.com"}, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["domain"] == "acme.com" and body["name"] == "Acme"
    assert body["logo"].startswith("/api/logos/") and body["logo"].endswith(".ico")

    served = client.get(body["logo"].removeprefix("/api"))  # no token: an <img> can't send one
    assert served.status_code == 200 and served.headers["content-type"] == "image/x-icon"
    assert "immutable" in served.headers["cache-control"]


def test_the_logo_route_serves_nothing_but_hashed_names(client):
    for name in ("../config.yaml", "x.svg", "0123456789abcdef0123.svg", "acme.png"):
        assert client.get(f"/logos/{name}").status_code == 404


def test_a_bad_domain_is_refused(client):
    r = client.patch("/companies/1", json={"domain": "not a site"}, headers=AUTH)
    assert r.status_code == 422
