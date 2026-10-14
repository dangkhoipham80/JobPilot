"""Turn a job description you pasted in by hand into a reviewed, tailorable job.

Three steps, deliberately separate, because each one is useful without the next
and each one is a different kind of claim:

1. **Read** (:mod:`jobpilot.intake.service`, ``extract_jd``) — a model pulls the
   title, company, location, salary, level and skills out of a blob of text.
   Nothing is written to the database; the answer goes back to the form so the
   user can correct it before it becomes a row.
2. **Save** — the existing ``POST /jobs`` path, unchanged in contract, now
   running the same enrichment a crawled job gets.
3. **Assess** (``assess_fit``) — a model scores the saved job against the Master
   CV and says what is missing. Advisory: it never edits the CV and never feeds
   the tailor prompt.

The load-bearing rule is that step 1 **does not rewrite the posting**. The JD
stored on the job is the text the user pasted, converted from HTML if that is
what they pasted and otherwise theirs — whitespace tidied per line, indentation
and paragraph breaks kept, not a word changed. A model that paraphrased
the JD would be inventing the evidence that every later guardrail checks
against — the tailor's requirement list, the cover letter, the fit report all
read that field and would inherit the invention silently.
"""

from __future__ import annotations

from jobpilot.intake.schema import FitReport, JdExtract
from jobpilot.intake.service import (
    FileReading,
    IntakeRefused,
    IntakeResult,
    assess_fit,
    extract_jd,
    read_files,
)

__all__ = [
    "FileReading",
    "FitReport",
    "IntakeRefused",
    "IntakeResult",
    "JdExtract",
    "assess_fit",
    "extract_jd",
    "read_files",
]
