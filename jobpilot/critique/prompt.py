"""Prompt for the CV critique: the Master outline plus the counted market snapshot."""

from __future__ import annotations

from datetime import date

from jobpilot.cv.schema import CvDocument
from jobpilot.tailor.prompt import render_master

LANGUAGES = {"vi": "Vietnamese", "en": "English"}

RULES = """\
You review a software engineer's Master CV against the job ads they are
targeting, and tell them what to improve, what is fine, and what to cut.

# What you are given
- The Master CV as an indexed outline. It is a store: it may hold more projects
  than one page fits, because each application is tailored down from it and
  keeps only the few most relevant projects. So the number of projects is not a
  problem in itself and "cut the store down to N" is not advice: judge each
  entry on whether it would help any realistic application, and use `cut` for
  one that would not.
- A market snapshot counted from crawled job ads for the target role. It
  describes those ads, not the whole market, and it says how many jobs it rests
  on. When it warns that the sample is small, say your read is tentative.
  Some rows are a job board's category tags rather than skills ("software
  development", "software products and web services"); ignore those.

# Rules
- This is advice to the candidate, not a CV. Be direct and specific: "the
  BlueOne bullets say what was built but not what it changed" beats "add impact".
- Never suggest putting a skill, employer, title or figure on the CV that the
  outline does not already show. For a skill the market wants and the CV lacks,
  say whether it is worth learning; do not tell them to list it. When a bullet
  would be stronger with a metric, say "add a real figure if you have one" —
  never propose a number.
- Do not quote counts or percentages from the snapshot. The page prints them
  beside your text; refer to demand in words ("most backend ads ask for it").
- Address sections by their key and entries by `section_key` + `entry_index`
  exactly as the outline prints them. Give a verdict for every experience and
  project entry, and for every section.
- In every free-text field, name an entry or bullet by its title or what it
  says ("the FPT Software bullets", "the Kafka line in Slide AI") — never by an
  index such as entry[0] or bullet[2]. The reader never sees the outline.
- `skills`: only skills from the snapshot that are NOT on the CV, at most eight,
  the most relevant to the target first. Leave out board category tags and
  generic words ("api") rather than advising to skip them.
- Dates on the CV are judged against today's date, given with the snapshot. An
  entry dated this year is recent, not a typo.
- `priorities`: three to five, most valuable first, each one actionable.
- Write every free-text field in {language}. Keep technology names, role titles
  and section keys as they are.
"""


def system_prompt(master: CvDocument, lang: str = "vi") -> str:
    """Stable for a given CV and language — rules plus the outline."""
    language = LANGUAGES.get(lang, LANGUAGES["vi"])
    return f"{RULES.replace('{language}', language)}\n\n{render_master(master)}"


def user_prompt(market: str, role: str, today: date) -> str:
    # Today's date is not optional: without it a model whose training ended
    # before the CV's latest entries reads "Oct 2026 -- Present" as a typo and
    # tells the user to fix a date that is correct (seen on the first real run).
    target = role or "any software engineering role"
    return (
        f"Today's date: {today.isoformat()}\n"
        f"Target role: {target}\n\n{market}\n\n"
        "Review the Master CV above against this snapshot."
    )
