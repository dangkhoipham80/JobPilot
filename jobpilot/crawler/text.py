"""Text helpers shared by scrapers & normalization (no network, pure functions)."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup
from bs4.element import Tag

_WS = re.compile(r"\s+")

#: Seniority word -> the level it means. Words that differ only in how formal
#: the board is ("Sr." / "Lead" / "Principal") collapse onto one level, matching
#: ``normalize.infer_level`` — the two must agree or a job's ``level`` column
#: would contradict the level its dedup key was split on.
_LEVEL_ALIASES = {
    "junior": "junior",
    "jr": "junior",
    "fresher": "fresher",
    "intern": "intern",
    "interns": "intern",
    "internship": "intern",
    "middle": "middle",
    "mid": "middle",
    "senior": "senior",
    "sr": "senior",
    "lead": "senior",
    "principal": "senior",
    "staff": "senior",
}

#: Derived, never written out a second time: a level word the stripper does not
#: know is a level word that cannot be read back out by :func:`title_level`, and
#: two lists that agree today drift the first time somebody adds "architect".
_LEVEL_WORDS = frozenset(_LEVEL_ALIASES)


def clean_text(s: str | None) -> str:
    """Collapse whitespace (incl. non-breaking spaces) and trim."""
    return _WS.sub(" ", (s or "").replace("\xa0", " ")).strip()


def el_text(el: Tag | None) -> str:
    """Whitespace-collapsed text of an element, or ``""`` when it is missing.

    Every scraper needs this as the first step of reading any field, so it lives
    here rather than as a fifth private copy.
    """
    return clean_text(el.get_text(" ", strip=True)) if el else ""


def first_match(root: Tag, *selectors: str) -> Tag | None:
    """First match trying each selector *in the given order*.

    Deliberately not ``root.select_one("a, b")``: a comma-separated selector
    returns the earliest match in **document order**, throwing away the
    preference the order was meant to express. On a VietnamWorks card the logo
    anchor precedes the heading anchor, so the one-liner picked the logo — which
    has no text, only a ``title`` attribute — and the job title silently came
    from the wrong element.
    """
    for sel in selectors:
        found = root.select_one(sel)
        if found is not None:
            return found
    return None


def strip_query(url: str) -> str:
    """Drop the query string and fragment from a URL.

    Job-board listing links carry per-session tracking (TopCV's ``u_sr_id``,
    VietnamWorks' ``?source=searchResults&placement=…``). Keeping it would churn
    the stored URL on every crawl and leak a session identifier into the database
    and the apply hand-off.
    """
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def leaf_texts(root: Tag, max_len: int = 60) -> list[str]:
    """Short text nodes with no element children — the labels on a card.

    Returns a list, not a generator: callers scan it more than once, and a
    half-consumed generator silently yields nothing the second time.
    """
    out: list[str] = []
    for el in root.find_all(True):
        if el.find(True):
            continue
        text = clean_text(el.get_text(" ", strip=True))
        if text and len(text) <= max_len:
            out.append(text)
    return out


def html_to_markdown(html: str | None) -> str:
    """Lightweight HTML → Markdown for JD bodies.

    Not a full converter — enough to keep headings, paragraphs and bullet lists
    readable for the tailor step. Falls back to flat text when no block tags are
    present.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    out: list[str] = []
    for el in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]):
        text = clean_text(el.get_text(" ", strip=True))
        if not text:
            continue
        name = el.name
        if name[0] == "h" and name[1:].isdigit():
            out.append("#" * int(name[1:]) + " " + text)
        elif name == "li":
            out.append("- " + text)
        else:
            out.append(text)

    md = "\n\n".join(out)
    if not md:  # no recognizable block tags — return flat text
        md = clean_text(soup.get_text(" ", strip=True))
    return md


def fold(word: str | None) -> str:
    """``"Công"`` → ``"cong"`` — accents stripped, lowercased.

    Lives here rather than next to its first caller (mail matching in
    ``apply/inbox``) because it is the bottom of every name-comparison in the
    app: employers, job titles and city names all arrive spelled three ways.
    ``inbox`` re-exports it, so ``from jobpilot.apply.inbox import fold`` still
    reads naturally where the subject is mail.
    """
    decomposed = unicodedata.normalize("NFD", (word or "").lower())
    # Vietnamese đ/Đ has no combining form, so NFD leaves it alone.
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.replace("đ", "d")


#: Legal-form words that trail an employer name in English and most European
#: registries ("Tinhvan Software **JSC.**", "Acme **Ltd**"). Stripped only from
#: the *end*: "SA Group" and "Co-op Bank" are real names whose first token
#: happens to be one of these, and folding those away would merge two employers
#: into one HR contact list — the failure mode that ends with a CV in a
#: stranger's inbox.
_LEGAL_TAIL_WORDS = frozenset(
    {
        "inc", "incorporated", "llc", "ltd", "limited", "co", "corp",
        "corporation", "company", "plc", "gmbh", "ag", "bv", "nv", "sa",
        "srl", "pte", "pty", "sdn", "bhd", "kk", "jsc",
    }
)

#: The Vietnamese equivalents, which are written in *front* of the name:
#: "**Công ty TNHH** Foo", "**Công ty Cổ phần** Bar". Same reasoning mirrored —
#: head only, because "Cong Ty" never trails a name here.
_LEGAL_HEAD_WORDS = frozenset({"cong", "ty", "cty", "tnhh"})

#: Head words that only count as a legal form once another one has been peeled
#: off in front of them. "MTV" is "một thành viên" and is always written after
#: "Công ty TNHH"; standing first it is an ordinary name, and stripping it
#: turned "MTV Networks" into "networks" — a token generic enough to collide
#: with a different employer, which is the one direction that must not happen.
_LEGAL_HEAD_WORDS_AFTER = frozenset({"mtv"})

#: Multi-word forms, matched as units so no single token has to be listed on its
#: own. "phan" alone is a common Vietnamese surname and "stock" is an ordinary
#: word; each is only a legal form beside its partner.
_LEGAL_HEAD_PHRASES = (("co", "phan"),)
_LEGAL_TAIL_PHRASES = (("joint", "stock"),)

_NON_WORD = re.compile(r"[^a-z0-9]+")


def _strip_legal_forms(tokens: list[str]) -> list[str]:
    """Peel legal-form words off both ends, never down to nothing.

    The ``len > 1`` guard is what makes a company literally called "Company Ltd"
    normalize to the same key as one called "Company", instead of one of them
    falling back to its unstripped spelling and quietly becoming a second row.
    """
    changed = True
    stripped_head = False
    while changed and len(tokens) > 1:
        changed = False
        for phrase in _LEGAL_HEAD_PHRASES:
            n = len(phrase)
            if len(tokens) > n and tuple(tokens[:n]) == phrase:
                tokens, changed, stripped_head = tokens[n:], True, True
        head_words = _LEGAL_HEAD_WORDS | (_LEGAL_HEAD_WORDS_AFTER if stripped_head else frozenset())
        if len(tokens) > 1 and tokens[0] in head_words:
            tokens, changed, stripped_head = tokens[1:], True, True
        for phrase in _LEGAL_TAIL_PHRASES:
            n = len(phrase)
            if len(tokens) > n and tuple(tokens[-n:]) == phrase:
                tokens, changed = tokens[:-n], True
        if len(tokens) > 1 and tokens[-1] in _LEGAL_TAIL_WORDS:
            tokens, changed = tokens[:-1], True
    return tokens


def normalize_company(company: str | None, *, strip_legal: bool = False) -> str:
    """An employer name reduced to what two spellings of it have in common.

    ``strip_legal`` is the *only* thing that separates the two callers, and it
    is a parameter for the same reason ``normalize_title(strip_level=)`` is one:
    two hand-written normalizers for the same string is how ``analytics`` and
    ``dedup_key`` drifted apart before. Cross-source dedup leaves it off — it
    compares two boards' copies of one posting, which spell the employer the
    same way — while ``companies`` turns it on, because that key has to hold
    "Tinhvan Software JSC." and "Tinhvan Software" together for years.
    """
    name = clean_text(fold(company))
    if not strip_legal:
        return name
    tokens = _strip_legal_forms([t for t in _NON_WORD.split(name) if t])
    return " ".join(tokens)


def normalize_title(title: str | None, *, strip_level: bool = True) -> str:
    """Canonicalize a job title for grouping.

    Drops parentheticals and punctuation; keeps tech tokens (``+``/``#``/``.``
    survive so "c++"/"c#"/".net" stay distinct). Folded to ASCII first, or the
    punctuation pass would shred a Vietnamese title into initials — "Lập trình
    viên Java" became ``"l p tr nh vi n java"``, which matches no other spelling
    of itself.

    ``strip_level`` is the *only* thing that separates the two callers, and it
    is a parameter rather than a second function on purpose. Cross-source dedup
    strips the level (see :func:`dedup_key`); repeat-posting detection keeps it,
    because an employer re-advertising the senior role is not re-advertising the
    junior one. Two hand-written normalizers for the same string is how the
    ``analytics`` grouping and this one silently drifted apart in the first
    place.
    """
    t = fold(title)
    t = re.sub(r"\(.*?\)", " ", t)  # drop "(Java, Spring Boot)" etc.
    t = re.sub(r"[^a-z0-9+#. ]", " ", t)
    # A *trailing* dot is abbreviation punctuation, never part of a tech token:
    # ".net" wears its dot in front and "node.js" in the middle. Keeping it made
    # "Sr. Backend Engineer" normalize to `sr. backend engineer` — a token the
    # level list could not recognise, and a key that therefore did not match
    # "Senior Backend Engineer" at the same company at all.
    tokens = [w for w in (raw.rstrip(".") for raw in t.split()) if w]
    return " ".join(w for w in tokens if not (strip_level and w in _LEVEL_WORDS)).strip()


def title_level(title: str | None) -> str | None:
    """The seniority stated *in the title*, or ``None`` when it says nothing.

    Deliberately not ``normalize.infer_level``, which also reads the JD: a
    description that mentions "we hire senior engineers" is evidence about the
    company, not about this opening, and here a wrong level does not merely
    mislabel a job — it decides whether two postings are the same posting. The
    title is the one place a level word is never an accident.
    """
    for token in normalize_title(title, strip_level=False).split():
        level = _LEVEL_ALIASES.get(token)
        if level:
            return level
    return None


def dedup_key(company: str | None, title: str | None) -> str:
    """Cross-source dedup key: normalized ``company|title`` (PLAN §3.2).

    Level-free, so "Java Backend" and "Junior Java Backend" share a key. The
    level is *not* folded in here but carried beside it (``title_level``),
    because two postings only count as different roles when **both** name a
    level and the levels disagree — see ``persist._Index``.
    """
    return f"{normalize_company(company)}|{normalize_title(title)}"
