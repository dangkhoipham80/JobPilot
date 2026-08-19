"""Text normalisation shared by every "did the model quote something real?" check.

Two features rely on the same guarantee — an LLM claim is only accepted when the
span it cites genuinely appears in the source text: inbox sync (`apply/inbox.py`,
the quote must be in the email) and Master CV editing (`tailor/edit_guard.py`,
the quote must be in the user's instruction). They live in different packages and
would happily grow two slightly different notions of "appears in", which is the
kind of divergence that stays invisible until one side accepts what the other
rejects. One normaliser, both sides.
"""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")


def normalize_text(text: str | None) -> str:
    """Collapse whitespace, strip, lowercase — for substring comparison only.

    Deliberately does *not* strip punctuation: a quote that differs from the
    source by more than spacing and case is a paraphrase, and the whole point of
    demanding a quote is that a paraphrase does not count.
    """
    return _WS.sub(" ", text or "").strip().lower()


def quote_appears_in(quote: str, source: str) -> bool:
    """True when ``quote`` really occurs in ``source``, ignoring spacing and case.

    An empty quote is *not* treated as trivially present; callers that allow an
    absent quote must check for emptiness themselves, so "no quote given" and
    "quote that checks out" can never be confused.
    """
    needle = normalize_text(quote)
    return bool(needle) and needle in normalize_text(source)
