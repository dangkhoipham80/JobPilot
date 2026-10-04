"""What a call costs, and what the provider is allowed to do with it.

Two tables that go stale in different ways, kept together because both are
"facts about a provider that live outside the code and change without warning".

``PRICES`` is an *estimate*. Rates move, discounts apply that this table doesn't
model (batch, long-context surcharges), and a model missing from the table
returns ``None`` rather than a guess — see ``estimate_cost``.

``DATA_POLICY`` is the part that matters more. Tailoring puts the entire Master
CV in the system prompt (``tailor/prompt.py:system_prompt``), so "what does this
company do with my input" is a real question with a per-provider answer. The
entries quote and link the official terms rather than paraphrasing them; the
reader is meant to go read the page.
"""

from __future__ import annotations

from dataclasses import dataclass

#: When the numbers and the policy notes below were last read off the official
#: pages. Print it next to anything derived from them.
CHECKED_ON = "2026-08-08"

#: (input, output) US dollars per million tokens.
PRICES: dict[tuple[str, str], tuple[float, float]] = {
    # https://platform.claude.com/docs/en/about-claude/models/overview
    ("claude", "claude-opus-4-8"): (5.0, 25.0),
    ("claude", "claude-opus-5"): (5.0, 25.0),
    ("claude", "claude-sonnet-5"): (3.0, 15.0),
    ("claude", "claude-sonnet-4-6"): (3.0, 15.0),
    ("claude", "claude-haiku-4-5"): (1.0, 5.0),
    ("claude", "claude-haiku-4-5-20251001"): (1.0, 5.0),
    ("claude", "claude-fable-5"): (10.0, 50.0),
    # The subscription provider: nothing per call, the plan is already paid
    # for. Listed so the /models picker offers these models for it — the picker
    # is built from this table — and at 0.0 rather than absent, because absent
    # means "price unknown" and this price is known.
    ("claude_cli", "claude-haiku-4-5"): (0.0, 0.0),
    ("claude_cli", "claude-sonnet-5"): (0.0, 0.0),
    ("claude_cli", "claude-opus-4-8"): (0.0, 0.0),
    ("claude_cli", "claude-opus-5"): (0.0, 0.0),
    # https://openai.com/api/pricing/
    ("openai", "gpt-4.1"): (2.0, 8.0),
    ("openai", "gpt-4.1-mini"): (0.40, 1.60),
    ("openai", "gpt-4o"): (2.50, 10.0),
    ("openai", "gpt-4o-mini"): (0.15, 0.60),
    ("openai", "gpt-5"): (1.25, 10.0),
    ("openai", "o4-mini"): (1.10, 4.40),
    # https://ai.google.dev/gemini-api/docs/pricing
    ("gemini", "gemini-3.6-flash"): (1.50, 7.50),
    ("gemini", "gemini-3.5-flash"): (1.50, 9.0),
    ("gemini", "gemini-3.5-flash-lite"): (0.30, 2.50),
    ("gemini", "gemini-3.1-flash-lite"): (0.25, 1.50),
    # The 2.5 line still bills for keys that already had it, but answers new
    # keys with 404 "no longer available to new users". Kept priced rather than
    # deleted: the rate is right for whoever still has access, and a missing
    # price would read as "we don't know" when we do.
    ("gemini", "gemini-2.5-flash"): (0.30, 2.50),
    ("gemini", "gemini-2.5-pro"): (1.25, 10.0),
}

#: Measured on the five-message classify benchmark, 2026-08-08, all scoring 5/5.
#: Kept as a comment rather than code because it is evidence, not configuration —
#: rerun ``jobpilot llm bench --task classify --provider X --model Y`` to refresh.
#:
#:   gpt-4o-mini            $0.0005   p50 1324ms
#:   gemini-3.1-flash-lite  $0.0007   p50  705ms   <- cheapest that is also fastest
#:   gemini-3.5-flash-lite  $0.0010   p50  773ms
#:   gpt-4.1-mini           $0.0013   p50 1185ms
#:   claude-haiku-4-5       $0.0043   p50 1256ms
#:   gemini-3.5-flash       $0.0187   p50 2110ms   <- thinking tokens bill as output


def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Dollars for one call, or ``None`` when the model isn't in the table.

    ``None`` propagates all the way to the dashboard on purpose. An unpriced
    model showing $0.00 would make the cheapest column in the comparison the one
    we know least about — precisely backwards.

    Cached input is deliberately *not* discounted here. Providers discount cache
    reads by up to 90%, which would make this an over-estimate, and an
    over-estimate that errs toward "this costs more than you think" is the safe
    direction for a number a person uses to pick a backend.
    """
    rate = PRICES.get((provider, model))
    if rate is None:
        return None
    return (input_tokens * rate[0] + output_tokens * rate[1]) / 1_000_000


@dataclass(frozen=True)
class PolicyNote:
    """One provider's stance on training with what you send it."""

    #: True when the provider may train on API input/output at this tier.
    trains_on_input: bool
    #: The CLI's wording. The dashboard words the same note in
    #: ``web/src/i18n/dict/models.ts`` — change both; a test compares the English.
    summary: str
    url: str
    #: The answer depends on a setting in the user's own account, which
    #: JobPilot cannot read. Still warned about (``trains_on_input``), but not
    #: printed as if it were certain.
    depends_on_account: bool = False
    #: When *this* note was read, if later than the table-wide ``CHECKED_ON``.
    checked_on: str | None = None


#: Keyed by provider, plus the tiers that differ from their provider default.
#: Only the entries that *differ* are worth spelling out — a warning printed for
#: every provider is a warning nobody reads.
DATA_POLICY: dict[str, PolicyNote] = {
    "claude": PolicyNote(
        trains_on_input=False,
        summary=(
            "Anthropic does not train on API inputs or outputs. Logs are kept 7 days "
            "by default; zero-retention is available on request."
        ),
        url="https://platform.claude.com/docs/en/manage-claude/api-and-data-retention",
    ),
    # A Claude subscription is under the *consumer* terms, not the API's: the
    # same models, a different contract. Claude Code sessions on a Free/Pro/Max
    # account follow the account's "Help improve Claude" setting.
    "claude_cli": PolicyNote(
        trains_on_input=True,
        summary=(
            "This runs on your Claude subscription, which is covered by Anthropic's consumer "
            'terms, not the API terms: if "Help improve Claude" is on in your claude.ai privacy '
            "settings, these conversations may be used to train models. Turn it off there to opt out."
        ),
        url="https://www.anthropic.com/news/updates-to-our-consumer-terms",
        depends_on_account=True,
        checked_on="2026-10-04",
    ),
    "openai": PolicyNote(
        trains_on_input=False,
        summary=(
            "OpenAI does not train on API data unless you explicitly opt in. Abuse-"
            "monitoring logs are kept up to 30 days."
        ),
        url="https://developers.openai.com/api/docs/guides/your-data",
    ),
    "gemini": PolicyNote(
        trains_on_input=False,
        summary="On the paid tier Google does not use your prompts or responses to improve its products.",
        url="https://ai.google.dev/gemini-api/terms",
    ),
    # The one entry that is a real warning rather than reassurance.
    "gemini:free": PolicyNote(
        trains_on_input=True,
        summary=(
            "On the unpaid tier Google uses submitted content to improve its products, and "
            'human reviewers may read it. The terms say: "Do not submit sensitive, '
            'confidential, or personal information to the Unpaid Services."'
        ),
        url="https://ai.google.dev/gemini-api/terms",
    ),
}


def policy_key(provider: str, *, paid_tier: bool = True) -> str | None:
    """The ``DATA_POLICY`` key that applies — ``"gemini:free"`` rather than
    ``"gemini"`` on the unpaid tier — or ``None`` when there is no note.

    It is what the dashboard translates by: the backend says *which* note, the
    frontend owns the sentence in each language.
    """
    if not paid_tier and f"{provider}:free" in DATA_POLICY:
        return f"{provider}:free"
    return provider if provider in DATA_POLICY else None


def policy_for(provider: str, *, paid_tier: bool = True) -> PolicyNote | None:
    """The note that applies, or ``None`` for a provider we have no note for.

    ``None`` is not "it's fine" — it is "nobody has read this one's terms", and
    callers render it as its own kind of warning.
    """
    key = policy_key(provider, paid_tier=paid_tier)
    return DATA_POLICY[key] if key else None
