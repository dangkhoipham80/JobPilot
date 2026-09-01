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

Three known limitations, written down rather than half-fixed:

* **"k" is not read as thousands.** "$50k - $70k/year" parses as 50 to 70, which
  is wrong by 1000x on the commonest US-board format. The obvious fix -- a
  whole-label "this label says k" flag, mirroring ``millions`` -- is *worse than
  the bug*: "401k" and "thưởng 500k" are ordinary boilerplate beside a normal
  salary, so the flag multiplies bounds that were already right. It was tried
  and reverted after "$800 - $900/month, 401k" came back as 800,000-900,000 a
  month. Doing this properly means attaching the scale to the figure that
  carries the "k", not to the label, and that is its own change.
* **A label that leads with non-pay numbers can still lose.** "2 - 3 năm KN, 20
  triệu" reports 2 million: the range fence correctly rejects "2 - 3" as not
  money, and the fallback then takes the first figure in the string. The
  fallback is right far more often than not -- salary labels lead with the
  salary -- but it is a heuristic, not a guarantee.
* **A marker detached from both bounds is not seen.** "Lương USD, 1,500 - 2,500"
  gives 1500-1500, because the fence wants a marker touching one of the bounds
  and this one sits in front of the whole phrase. Allowing punctuation between
  marker and figure was tried: it fixes exactly this shape and breaks "Lương
  USD, 2 - 3 năm kinh nghiệm", which it then reads as a pay range of 2 to 3.
  That is the same trade this module has now lost six times, so the fence stays
  tight and this stays a gap. Ads that write the currency beside a figure are
  unaffected, which is nearly all of them and all of the JSON-LD sources.
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

# ----------------------------------------------------------------------------
# What makes a figure money
#
# **A figure counts as money only when it is written as money**: a marker in
# front of it, or a marker behind it. Nothing else qualifies -- not "ends the
# label", not "is the only number here".
#
# This one rule is the whole defence, because the module's failure mode never
# varies: whenever a pattern misses, parsing falls through to the bare-figure
# branch, and *some* number in the label gets reported as pay. Ads are full of
# numbers that are not pay -- years of experience, ages, headcount, "thưởng 2
# tháng", "lương tháng 13", "85%" -- and every one of them looks plausible in a
# chart. It cost four separate regressions to arrive at stating it once:
#
#   "Lương 20 triệu, trên 2 năm kinh nghiệm"  floor of 2 *million*, 20tr -> "<$500"
#   "Lương 20 triệu, tuổi dưới 30"            an age as the ceiling
#   "20 triệu, 3+ năm kinh nghiệm"            a year count as the floor
#   "Lương 20 triệu, 2 ~ 3 năm kinh nghiệm"   a year *range* as the pay range
#
# So the markers live in exactly two constants and every branch below is built
# from them. Adding a keyword, a separator or a new shape without going through
# _LEAD/_TRAIL is how each of the four got in.
# ----------------------------------------------------------------------------

#: Markers that precede a figure: "$2,000", "USD 2,000", "US$ 2,000".
_LEAD = r"(?:us\s*\$|\$|usd|vnd|vnđ)"
#: Markers that follow one, currency or scale. ``us\s*\$`` leads the alternation
#: so "3000 US$" is not read as a bare "3000" followed by junk.
_MONEY = r"(?:tr|triệu|k|m|million|us\s*\$|usd|vnd|vnđ|đ|dollars?|\$)"
#: A marker ends where the word ends -- "5m VND" is money, "5months" is not.
#: ``\b`` cannot be used: it fails after "$", so "2000$" would not count.
_END = r"(?!\w)"
#: A trailing marker, optionally wrapped: "3000 USD", "3000 (USD)", "3000 US$".
_TRAIL = rf"\s*[(\[]?\s*{_MONEY}{_END}"

#: A figure written as money, captured. Two alternatives, so two groups.
_BOUND = rf"(?:{_LEAD}\s*({_NUM})|({_NUM}){_TRAIL})"

# A range needs only *one* of its four marker slots filled -- boards write the
# unit once ("20 - 60 triệu", "15tr - 25tr", "$2,000 - $3,000", "USD 2,000 - USD
# 3,000") and which slot it lands in varies by board. But it does need one:
# without that, adding "~" to the separators turned "2 ~ 3 năm kinh nghiệm" into
# a salary range, on labels the previous version had read correctly.
_RANGE = re.compile(
    rf"(?P<lead1>{_LEAD}\s*)?(?P<lo>{_NUM})(?P<unit1>{_TRAIL})?"
    rf"\s*(?:{_SEP})\s*"
    rf"(?P<lead2>{_LEAD}\s*)?(?P<hi>{_NUM})(?P<unit2>{_TRAIL})?",
    re.I,
)
_RANGE_MARKERS = ("lead1", "unit1", "lead2", "unit2")

# "Up to 3000 USD", "tới 25 triệu", "dưới 30 triệu"
_MAX_ONLY = re.compile(rf"\b(?:up\s*to|tới|đến|max|dưới|under|below)\s*{_BOUND}", re.I)
# "From 2000 USD", "từ 15 triệu", "trên 30 triệu", "at least 2000 USD"
_MIN_ONLY = re.compile(rf"\b(?:from|từ|starting|min|at\s*least|ít\s*nhất|trên)\s*{_BOUND}", re.I)

#: "or more", spelled out. The trailing guard keeps "and up" from matching
#: inside "and updated benefits".
_OPEN = r"(?:trở\s*lên|or\s*more|and\s*up|or\s*above)(?!\w)"

# The floor written as a suffix: "160 triệu+", "$2000+", "20 triệu trở lên".
#
# The ceiling is genuinely unstated, so ``max`` stays None -- the mirror of "up
# to 3000" leaving ``min`` None. Writing the floor into *both* bounds instead
# asserts a ceiling the ad never gave.
#
# The plus must be *bound to the figure*: "2000+" is an open range, while
# "2000 USD + phụ cấp" is a base plus allowances -- a very common Vietnamese
# form, and reading it as "2000 or more" trades one wrong number for another.
# The signal is the space *before* the plus, not what follows it; keying on what
# follows gets "15tr+ gross" and "2000+ USD" backwards, since both are open
# ranges whose plus happens to precede a word.
_MIN_SUFFIX = re.compile(
    # "$2000+", "$2000 or more" -- money by the leading marker
    rf"(?:{_LEAD}\s*({_NUM})(?:(?<!\s)\+|\s*{_OPEN})"
    # "15tr+", "160 triệu+", "2000 USD or more" -- money by the trailing marker
    rf"|({_NUM}){_TRAIL}\s*(?:(?<!\s)\+|{_OPEN})"
    # "2000+ USD", "5.000.000+ VNĐ" -- plus bound to the figure, marker after it
    #
    # No "or end of label" alternative here, however tempting: this branch is
    # where "20 triệu, 3+" would come back as a floor of 3 million. An anchor is
    # not a marker, which is the rule stated at the top of this section -- and it
    # got broken here first, on the branch added last.
    rf"|({_NUM})(?<!\s)\+{_TRAIL})",
    re.I,
)
_ANY_NUM = re.compile(_NUM)


def _figure(m: re.Match) -> str:
    """The captured figure, from whichever alternative carried the marker.

    ``_BOUND`` and ``_MIN_SUFFIX`` express "a figure written as money" as two or
    three alternatives, so exactly one group is ever set. The test covers ``"0"``,
    which ``or``-chaining would have mistaken for "no group matched".
    """
    return next(g for g in m.groups() if g is not None)


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

    ``millions`` is a whole-label flag, which is only safe because Vietnamese
    ads carry the convention that a bare figure next to "triệu" is millions.
    **"k" has no equivalent convention and must not be added this way** -- see
    the note in :func:`parse`.
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


def _first_range(s: str) -> re.Match | None:
    """The first range in ``s`` with at least one bound written as money.

    Scanning past the rejects rather than giving up on the first one matters:
    "2 - 3 năm kinh nghiệm, lương 20 - 60 triệu" leads with a range that is not
    money, and stopping there would report the years of experience as pay.
    """
    for m in _RANGE.finditer(s):
        if any(m.group(g) for g in _RANGE_MARKERS):
            return m
    return None


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
    num = lambda raw: _number(raw, millions)  # noqa: E731

    low = high = None
    if (m := _first_range(s)) is not None:
        low, high = num(m.group("lo")), num(m.group("hi"))
    elif (m := _MAX_ONLY.search(s)) is not None:
        high = num(_figure(m))
    elif (m := _MIN_ONLY.search(s)) is not None:
        low = num(_figure(m))
    elif (m := _MIN_SUFFIX.search(s)) is not None:
        low = num(_figure(m))
    elif (m := _ANY_NUM.search(s)) is not None:
        # A bare figure with no modifier is a point salary, not a range, so both
        # bounds are the same number on purpose.
        #
        # This is also where every label whose numbers are not money lands, and
        # it is deliberately *not* fenced -- something has to answer. Taking the
        # first figure is right far more often than not, because salary labels
        # lead with the salary, but it is a heuristic: "2 - 3 năm KN, 20 triệu"
        # comes back as 2 million. See the limitations in the module docstring.
        low = high = num(m.group(0))

    if low is None and high is None:
        return None
    if low is not None and high is not None and low > high:
        low, high = high, low
    return Salary(min=low, max=high, currency=currency, period=period)
