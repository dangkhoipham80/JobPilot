"""Turning a published salary label into numbers you can plot.

``vietnam.parse_salary`` already decides whether a string *is* a salary. This
goes one step further and extracts the figures, because "20 - 60 triệu" and
"1,500-2,500 USD" cannot be compared, bucketed or averaged as text — and a
market page whose central question is "what does this pay" needs them as
numbers.

Three things it refuses to do, all for the same reason: a wrong number is worse
than no number.

* **No guessing the currency.** A bare "20 - 60" could be millions of VND or
  dollars an hour. Without a marker the answer is ``None``.
* **No guessing the period.** Vietnamese ads quote monthly; US remote boards
  quote yearly. Unmarked defaults to monthly *only* for VND, where it is the
  near-universal convention, and is left explicit for everything else.
* **No inventing a midpoint.** "Up to 3000 USD" has no minimum. It stays
  ``None`` rather than becoming 0, which would drag every average down.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from jobpilot.crawler.vietnam import MAX_SALARY_LEN, clean_text, is_undisclosed_salary

#: VND per 1 USD, and the day it was true. Used only to put mixed-currency ads
#: on one axis; the native figures are kept alongside so nothing is lost to it.
#: It *will* drift — same class of fact as ``llm/pricing.PRICES``, so it carries
#: a date and the UI calls the converted number an estimate.
USD_VND_RATE = 25_400
FX_CHECKED_ON = "2026-08-08"

#: "triệu" is millions of VND — the unit almost every Vietnamese ad uses.
_MILLION = 1_000_000

_NUM = r"\d[\d.,]*"

# Every separator boards actually use between two bounds. ASCII hyphen, en/em
# dash, the real minus sign, and the tilde -- which CJK-aware input methods turn
# into its full-width or wave-dash form, so "2000～3000 USD" arrives looking like
# a range to a human and like one number to this module.
_SEP = r"-|–|—|−|~|～|〜|to|đến"

# A currency or scale marker can sit *after* the first figure ("15tr - 25tr") or
# *before* the second ("$2,000 - $3,000"). Both are ordinary on real boards, and
# missing either one is the same bug twice: the range pattern fails, parsing
# falls through to the single-number branch, and the floor is reported as both
# bounds. A ceiling quietly replaced by the floor is the kind of wrong that looks
# right -- see the note on this failure in jobpilot/analytics/CLAUDE.md.
# THE money table. One list, used by every branch below.
#
# It was three separate lists, and they drifted the way separate lists of the
# same thing always do: ``$`` was a valid marker after a figure in one and not in
# another, so "Up to 2000$" invented a floor while "Up to 2000 USD" did not.
# Anything that means money belongs here and nowhere else.
_MONEY = r"(?:tr|triệu|k|m|million|usd|vnd|vnđ|đ|dollars?|\$)"
#: A marker ends where the word ends -- "5m VND" is money, "5months" is not.
_END = r"(?!\w)"

# A currency or scale marker can sit *after* the first figure ("15tr - 25tr") or
# *before* the second ("$2,000 - $3,000", "USD 2,000 - USD 3,000"). Both are
# ordinary on real boards, and missing either one is the same bug twice: the
# range pattern fails, parsing falls through to the single-number branch, and the
# floor is reported as both bounds. A ceiling quietly replaced by the floor is
# the kind of wrong that looks right -- see jobpilot/analytics/CLAUDE.md.
_UNIT = rf"(?:\s*{_MONEY}{_END})?"
_SYMBOL = r"(?:(?:us\s*\$|\$|usd|vnd|vnđ)\s*)?"
_RANGE = re.compile(rf"({_NUM}){_UNIT}\s*(?:{_SEP})\s*{_SYMBOL}({_NUM})", re.I)

# **A figure only counts as money when it is written as money** -- a symbol in
# front of it or a unit behind it. Nothing else qualifies, and in particular
# "ends the label" does not.
#
# This is the fence that keeps the bounded forms below off the numbers in the
# boilerplate around them, and it went in after they walked straight into it.
# "trên" and "dưới" are two of the commonest words in a Vietnamese ad and they
# almost never introduce pay: unfenced, "Lương 20 triệu, trên 2 năm kinh nghiệm"
# reports a floor of 2 *million* and drops a 20tr job into the "<$500" band, and
# "20 triệu, dưới 30 tuổi" takes an **age** as the pay ceiling. Both are worse
# than the bare-figure branch they displace, which takes the first number and is
# usually right because a salary label leads with the salary.
#
# The first draft of the fence also accepted a bare figure at end of label, which
# let exactly the same sentences back in with the words reordered: "Lương 20
# triệu, tuổi dưới 30". An anchor is not a unit.
_BOUND = rf"(?:\$\s*({_NUM})|({_NUM})\s*{_MONEY}{_END})"

# "Up to 3000 USD", "tới 25 triệu", "dưới 30 triệu"
_MAX_ONLY = re.compile(rf"\b(?:up\s*to|tới|đến|max|dưới|under|below)\s*{_BOUND}", re.I)
# "From 2000 USD", "từ 15 triệu", "trên 30 triệu", "at least 2000 USD"
_MIN_ONLY = re.compile(rf"\b(?:from|từ|starting|min|at\s*least|ít\s*nhất|trên)\s*{_BOUND}", re.I)

# The floor written as a suffix: "160 triệu+", "15tr+", "20 triệu trở lên".
#
# The ceiling is genuinely unstated, so ``max`` stays None -- the mirror of "up
# to 3000" leaving ``min`` None. Writing the floor into *both* bounds instead
# asserts a ceiling the ad never gave.
#
# Two separate things have to be true, and the first draft checked neither
# properly:
#
# 1. **The plus must be bound to the figure.** "2000+" is an open range;
#    "2000 USD + phụ cấp" is a base plus allowances, a very common Vietnamese
#    form, and reading it as "2000 or more" trades one wrong number for another.
#    The signal is the space *before* the plus (``(?<!\s)``), not what follows
#    it -- keying on what follows gets "15tr+ gross" and "2000+ USD" backwards,
#    since both are open ranges whose plus happens to precede a word.
# 2. **The figure must be money**, by the same rule as _BOUND. Unfenced, any
#    "<digits>+" qualified, so "20 triệu, 3+ năm kinh nghiệm" reported a floor of
#    3 million -- the identical failure the fence above exists to prevent, left
#    open on the one branch this module added most recently.
_MIN_SUFFIX = re.compile(
    rf"({_NUM})(?:"
    # "15tr+", "160 triệu+", "2000 USD+" -- marker, then a plus bound to it
    rf"\s*{_MONEY}{_END}\s*(?<!\s)\+"
    # "2000+ USD", "5.000.000+ VNĐ", "2000+" -- plus bound to the figure
    rf"|(?<!\s)\+(?:\s*{_MONEY}{_END}|\s*$)"
    # "20 triệu trở lên", "2000 USD or more"
    rf"|\s*{_MONEY}{_END}\s*(?:trở\s*lên|or\s*more|and\s*up|or\s*above)" rf")",
    re.I,
)
_ANY_NUM = re.compile(_NUM)


def _bound_figure(m: re.Match) -> str:
    """The figure from a :data:`_BOUND` match, whichever side carried the marker."""
    return m.group(1) or m.group(2)


_USD = re.compile(r"\$|usd|dollar", re.I)
_VND = re.compile(r"vnd|vnđ|đ\b|triệu|tr\b|million", re.I)
_MILLION_UNIT = re.compile(r"triệu|tr\b|million|m\b", re.I)

_YEARLY = re.compile(r"/\s*(y|yr|year|năm)|per\s+year|annum|annual", re.I)
_HOURLY = re.compile(r"/\s*(h|hr|hour|giờ)|per\s+hour", re.I)


@dataclass(frozen=True)
class Salary:
    """A parsed pay range. ``min``/``max`` are in ``currency`` per ``period``."""

    min: float | None
    max: float | None
    currency: str
    period: str

    @property
    def usd_month(self) -> float | None:
        """A representative figure in US dollars per month, for one shared axis.

        The midpoint when both bounds are known, and the single known bound when
        only one is — *not* a midpoint against an imagined zero floor, which
        would halve every "up to $3000" ad and drag the corpus median with it.

        ``None`` when neither bound is known.
        """
        known = [v for v in (self.min, self.max) if v is not None]
        if not known:
            return None
        amount = sum(known) / len(known)
        if self.currency == "VND":
            amount /= USD_VND_RATE
        if self.period == "year":
            amount /= 12
        elif self.period == "hour":
            amount *= 160  # a working month
        return round(amount, 2)

    def as_dict(self) -> dict:
        return {**asdict(self), "usd_month": self.usd_month}


def _number(raw: str, millions: bool) -> float | None:
    """A figure like ``1,500`` or ``2.500`` as a float.

    Both separators appear, and they mean opposite things by locale. The rule
    that works on real ads: a separator with exactly three digits after it is a
    thousands grouping; anything else is a decimal point.
    """
    text = raw.strip().rstrip(".,")
    if not text:
        return None
    text = re.sub(r"[.,](?=\d{3}\b)", "", text)
    text = text.replace(",", ".")
    try:
        value = float(text)
    except ValueError:
        return None
    if millions and value < 1000:
        value *= _MILLION
    return value


def parse(text: str | None) -> Salary | None:
    """Extract figures from a salary label, or ``None`` if there are none.

    ``None`` covers every honest failure: a withheld salary, a label with no
    currency, and a string long enough to be page text rather than a label.
    """
    s = clean_text(text)
    if not s or len(s) > MAX_SALARY_LEN:
        return None

    currency = "USD" if _USD.search(s) else ("VND" if _VND.search(s) else "")
    if not currency:
        # No marker, no answer. "20 - 60" is millions of dong or dollars an
        # hour depending on the board, and picking one would be a coin flip
        # rendered as a fact.
        return None
    if is_undisclosed_salary(s) and not _ANY_NUM.search(s):
        return None

    millions = currency == "VND" and bool(_MILLION_UNIT.search(s))
    period = "year" if _YEARLY.search(s) else ("hour" if _HOURLY.search(s) else "month")

    low = high = None
    if (m := _RANGE.search(s)) is not None:
        low, high = _number(m.group(1), millions), _number(m.group(2), millions)
    elif (m := _MAX_ONLY.search(s)) is not None:
        high = _number(_bound_figure(m), millions)
    elif (m := _MIN_ONLY.search(s)) is not None:
        low = _number(_bound_figure(m), millions)
    elif (m := _MIN_SUFFIX.search(s)) is not None:
        low = _number(m.group(1), millions)
    elif (m := _ANY_NUM.search(s)) is not None:
        # A bare figure with no modifier is a point salary, not a range, so both
        # bounds are the same number on purpose.
        low = high = _number(m.group(0), millions)

    if low is None and high is None:
        return None
    if low is not None and high is not None and low > high:
        low, high = high, low
    return Salary(min=low, max=high, currency=currency, period=period)
