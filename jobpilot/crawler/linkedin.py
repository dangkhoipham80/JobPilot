"""LinkedIn jobs, sourced from **your own inbox** — never by crawling LinkedIn.

``linkedin.com/robots.txt`` disallows automated access to the job pages,
including the logged-out ``/jobs-guest/`` endpoint, and opens with "The use of
robots or other automated means to access LinkedIn without the express
permission of LinkedIn is strictly prohibited." So there is no robots-compliant
way to crawl it, and this project does not try (CLAUDE.md rule 5).

What LinkedIn *does* offer is **Job Alerts**: you describe what you want and it
emails you matching jobs. This scraper reads those emails from your mailbox.
Same jobs, zero requests to LinkedIn, nothing to get banned.

The parsing methods stay pure — they take an email's HTML and return hits — so
they are unit-testable against a saved alert message, exactly like the HTML
scrapers. Only ``crawl`` differs: it pulls from IMAP instead of HTTP.

Alert emails carry a title, company and location but rarely the full job
description. Jobs land with ``needs_jd`` set; paste the description in on the
job page before tailoring, or the tailor has little to work with.
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from jobpilot.crawler.base import BaseScraper
from jobpilot.crawler.mailbox import LINKEDIN_SENDERS, Mailbox, MailMessage
from jobpilot.crawler.text import clean_text
from jobpilot.crawler.types import RawJob, SearchHit

log = logging.getLogger(__name__)

# Alert emails link to /comm/jobs/view/<id> (tracked) or /jobs/view/<id>.
JOB_LINK_RE = re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(\d+)", re.I)
# Lines that are chrome or social proof, not job data. Verified against real
# alert emails: LinkedIn slips "34 company alumni" / "4 connections" straight
# after the company line, and they read exactly like a location if you let them.
_NOISE = re.compile(
    r"^(see all jobs|view job|apply now|unsubscribe|this email was|you are receiving"
    r"|actively recruiting|easy apply|be an early applicant|promoted|new|viewed"
    r"|\d+\s+(school|company)\s+alumni"
    r"|\d+\s+connections?\b"
    r"|\d+\s+(school|company)\s+alumni\s+work\s+here)",
    re.I,
)

# Real alert cards put company and location on ONE line: "ACME · Ho Chi Minh
# City, Vietnam (Hybrid)". The separator is a middle dot, occasionally with
# non-breaking spaces around it.
_COMPANY_LOCATION_SEP = re.compile(r"\s*[·•]\s*")

# Section headings, which LinkedIn also links to a job URL. Verified on a real
# alert: "Jobs similar to Java Engineer - Everyday Banking at NAB Innovation
# Centre Vietnam" linked to /jobs/view/<id> and was read as a job whose title
# was the whole heading and whose company was "Jobs similar to".
#
# Skipped rather than unwrapped. The heading names a job the user already saw --
# it is the *reason* the section exists — and the section's own cards are the
# real content. Trying to parse a title and company back out of the sentence
# would mean guessing where one ends and the other begins, on a line whose
# wording LinkedIn is free to change; being absent is a better answer than being
# confidently wrong about who the employer is.
_SECTION_HEADING = re.compile(
    r"^(jobs? similar to|more jobs (for|like)|because you|based on your|recommended for you)\b",
    re.I,
)


def _strip_card_tail(title: str, company: str, location: str | None) -> str:
    """Remove the company/location line when the link swallowed the whole card.

    In some layouts the ``<a>`` wraps the entire card rather than just the job
    title, so ``get_text()`` returns "Backend Software Engineer Axon · Ho Chi
    Minh City (On-site)" — title, employer and city run together with no
    delimiter between the first two. Nothing in that string says where the title
    ends.

    The card answers it anyway: the company/location line is also present on its
    own, so whatever the title ends with that equals that line is not part of the
    title. On a real crawl this was 8 of 47 LinkedIn jobs, each stored with the
    employer's name buried in the title, the *title* as the company, and the real
    company pushed into the location.

    Returns the title untouched when the tail does not match, because a title
    that keeps a few extra words is a great deal better than one truncated by a
    guess.
    """
    tail = f"{company} · {location}" if location else company
    for candidate in (tail, f"{company}·{location}" if location else ""):
        if candidate and title.endswith(candidate):
            return title[: -len(candidate)].strip(" ·-–—") or title
    return title


def job_url(job_id: str) -> str:
    """The canonical, tracker-free URL for a job id."""
    return f"https://www.linkedin.com/jobs/view/{job_id}/"


class LinkedInAlertsScraper(BaseScraper):
    source = "linkedin"

    def __init__(self, *, mailbox: Mailbox | None = None, since_days: int = 14, **kw) -> None:
        # No fetcher, no robots policy: this source never makes an HTTP request.
        kw.pop("fetcher", None)
        kw.pop("robots", None)
        super().__init__(**kw)
        self.mailbox = mailbox
        self.since_days = since_days

    # -- pure parsing (unit-testable against a saved alert email) ----------- #
    def search_url(self, query: str, page: int = 1) -> str:
        """Not applicable — this source reads a mailbox, not a URL."""
        return ""

    def parse_search(self, html: str) -> list[SearchHit]:
        """Pull the job cards out of one LinkedIn Job Alert email."""
        soup = BeautifulSoup(html or "", "html.parser")
        hits: dict[str, SearchHit] = {}

        for anchor in soup.find_all("a", href=True):
            match = JOB_LINK_RE.search(anchor["href"])
            if not match:
                continue
            job_id = match.group(1)
            title = clean_text(anchor.get_text(" ", strip=True))
            # A section heading links to a job too, but its text is a sentence
            # about the section rather than a job title. Dropped before anything
            # reads it as one — and before it can claim the id, which the card
            # further down the email uses properly.
            if _SECTION_HEADING.match(title):
                continue
            # Every card links twice (logo image + title). The image anchor has
            # no text, so prefer whichever occurrence actually names the job.
            if job_id in hits and not title:
                continue
            if not title and job_id not in hits:
                hits[job_id] = SearchHit(native_id=job_id, url=job_url(job_id))
                continue

            company, location = self._company_and_location(anchor, title)
            title = _strip_card_tail(title, company, location)
            hits[job_id] = SearchHit(
                native_id=job_id,
                url=job_url(job_id),
                title=title,
                company=company,
                location=location,
            )

        return [h for h in hits.values() if h.title]

    @staticmethod
    def _company_and_location(anchor, title: str) -> tuple[str, str | None]:
        """Read the company/location line that follows a job title in a card.

        Alert emails are nested tables with no stable classes, so this walks up
        to the smallest ancestor holding more than the title alone and reads its
        text lines. Real emails put both facts on one line —
        ``"NAB Innovation Centre Vietnam · Ho Chi Minh City, Vietnam (Hybrid)"``
        — so the line is split on the middle dot rather than assuming a second
        line, which would otherwise pick up "34 company alumni".

        Wrong guesses cost a blank field, not a wrong job.
        """
        block = anchor
        lines: list[str] = []
        for _ in range(6):  # a card is a few table levels above the link
            block = block.parent
            if block is None:
                break
            text = block.get_text("\n", strip=True)
            candidates = [
                clean_text(line)
                for line in text.split("\n")
                if clean_text(line) and clean_text(line) != title and not _NOISE.match(line.strip())
            ]
            if candidates:
                lines = candidates
                break

        if not lines:
            return "", None

        parts = _COMPANY_LOCATION_SEP.split(lines[0], maxsplit=1)
        company = parts[0].strip()
        location = parts[1].strip() if len(parts) > 1 else ""
        if not location and len(lines) > 1:
            # Some layouts really do put the location on its own line.
            location = lines[1]
        return company, location or None

    def parse_detail(self, html: str, hit: SearchHit) -> RawJob:
        """Build the job from the card. There is no detail page to fetch — that
        would mean crawling LinkedIn, which is the thing this avoids."""
        return RawJob(
            source=self.source,
            native_id=hit.native_id,
            url=hit.url,
            title=hit.title,
            company=hit.company,
            location=hit.location,
            posted_raw=hit.posted_raw,
            # Deliberately empty rather than a placeholder note: "no description"
            # must be one check (`not description_md`) for the UI, the API and the
            # tailor alike. `needs_jd` in extra records *why* it is empty.
            description_md="",
            # LinkedIn is never auto-applied (CLAUDE.md rule 2): you submit it.
            apply_channel="external",
            apply_target=hit.url,
            extra={"needs_jd": True, **hit.extra},
        )

    # -- crawl loop: IMAP instead of HTTP ---------------------------------- #
    def crawl(self, query: str = "", limit: int | None = None) -> list[RawJob]:
        """Read recent alert emails and turn every job card into a ``RawJob``."""
        mailbox = self.mailbox
        if mailbox is None:
            from jobpilot.crawler.mailbox import ImapMailbox

            mailbox = ImapMailbox()

        messages: list[MailMessage] = mailbox.fetch(
            senders=LINKEDIN_SENDERS, since_days=self.since_days, limit=40
        )
        log.info("[%s] %d alert email(s)", self.source, len(messages))

        jobs: dict[str, RawJob] = {}
        for message in messages:
            try:
                hits = self.parse_search(message.html)
            except Exception as exc:
                # One malformed email must not sink the batch.
                log.warning("[%s] skip email %s: %s", self.source, message.uid, exc)
                continue
            for hit in hits:
                if hit.native_id in jobs:
                    continue  # the same job repeats across daily alerts
                if message.date is not None:
                    hit.posted_raw = message.date.isoformat()
                jobs[hit.native_id] = self.parse_detail("", hit)

        results = list(jobs.values())
        if limit is not None:
            results = results[:limit]
        log.info("[%s] %d unique job(s) from alerts", self.source, len(results))
        return results
