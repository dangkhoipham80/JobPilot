"""Which backend runs which task.

One dict, not a chain of ``if provider == ...``. Adding a provider is adding an
entry here plus a client module — the four call sites and the config type stay
untouched. That is the whole point: the previous shape hard-coded two names into
a ``Literal`` and four factory functions, so a third backend meant editing six
places and remembering all of them.

Keyed by the string that appears in ``config.yaml`` under ``llm``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from jobpilot.llm.base import LlmError, StructuredClient
from jobpilot.llm.claude import DEFAULT_MODEL as CLAUDE_MODEL
from jobpilot.llm.claude import ClaudeClient
from jobpilot.llm.claude_cli import DEFAULT_MODEL as CLAUDE_CLI_MODEL
from jobpilot.llm.claude_cli import ClaudeCliClient
from jobpilot.llm.claude_cli import preflight as claude_cli_preflight
from jobpilot.llm.gemini import DEFAULT_MODEL as GEMINI_MODEL
from jobpilot.llm.gemini import GeminiClient
from jobpilot.llm.openai import DEFAULT_MODEL as OPENAI_MODEL
from jobpilot.llm.openai import OpenAIClient


@dataclass(frozen=True)
class Provider:
    """Everything the rest of the app needs to know about one backend."""

    key: str
    label: str
    default_model: str
    #: Attribute on ``Secrets`` holding this provider's key, and the .env name
    #: to tell the user about when it's missing.
    secret_attr: str
    env_var: str
    #: Extra to install, for the error message when the SDK is absent.
    extra: str
    #: (model, api_key, task) -> client. The task is passed because one
    #: provider's request shape depends on it: Claude's extended thinking is
    #: worth paying for on tailor and letter and pointless on classify.
    build: Callable[[str, str, str], StructuredClient]
    #: Anything besides the credential that must hold for this backend to run
    #: here — returns the reason it can't, or ''. Only the CLI provider needs
    #: one: an API key is the whole precondition for the SDK backends.
    preflight: Callable[[], str] | None = None
    #: The credential is an *option*, not a precondition. True for the CLI
    #: provider: a logged-in `claude` on this machine is enough — verified from
    #: a launchd agent, which is how the API runs — and the token only matters
    #: where no login session is reachable (ssh, a box nobody logs in to).
    key_optional: bool = False


#: Tasks that do not get Claude's extended thinking. Both are reading tasks
#: rather than writing ones — pull six fields off a posting, sort an email into
#: one of six labels — and neither has ever failed in a way more deliberation
#: would fix. A named set rather than ``task != "classify"`` so the third such
#: task doesn't have to rediscover the reasoning.
NO_THINKING: frozenset[str] = frozenset({"classify", "intake"})


PROVIDERS: dict[str, Provider] = {
    "claude": Provider(
        key="claude",
        label="Anthropic Claude",
        default_model=CLAUDE_MODEL,
        secret_attr="anthropic_api_key",
        env_var="ANTHROPIC_API_KEY",
        extra="tailor",
        build=lambda model, key, task: ClaudeClient(
            model=model, api_key=key, thinking=task not in NO_THINKING
        ),
    ),
    # Same models as "claude", billed to the user's Claude subscription through
    # the local `claude` CLI instead of per token. See llm/claude_cli.py.
    "claude_cli": Provider(
        key="claude_cli",
        label="Claude subscription (claude CLI)",
        default_model=CLAUDE_CLI_MODEL,
        secret_attr="claude_code_oauth_token",
        env_var="CLAUDE_CODE_OAUTH_TOKEN",
        extra="",
        # Thinking costs plan usage like any other token, so the reading tasks
        # ask for low effort — the same call ClaudeClient makes by switching
        # thinking off for them.
        build=lambda model, key, task: ClaudeCliClient(
            model=model, token=key, effort="low" if task in NO_THINKING else None
        ),
        preflight=claude_cli_preflight,
        key_optional=True,
    ),
    "openai": Provider(
        key="openai",
        label="OpenAI",
        default_model=OPENAI_MODEL,
        secret_attr="openai_api_key",
        env_var="OPENAI_API_KEY",
        extra="openai",
        build=lambda model, key, _task: OpenAIClient(model=model, api_key=key),
    ),
    "gemini": Provider(
        key="gemini",
        label="Google Gemini",
        default_model=GEMINI_MODEL,
        secret_attr="google_api_key",
        env_var="GOOGLE_API_KEY",
        extra="gemini",
        build=lambda model, key, _task: GeminiClient(model=model, api_key=key),
    ),
}


def provider_for(name: str) -> Provider:
    if name not in PROVIDERS:
        known = ", ".join(sorted(PROVIDERS))
        raise LlmError(f"unknown llm provider {name!r} — known providers: {known}")
    return PROVIDERS[name]


def api_key(name: str) -> str:
    from jobpilot.config import get_secrets

    return getattr(get_secrets(), provider_for(name).secret_attr, "") or ""


def ready(name: str) -> bool:
    """Whether ``name`` can be tried at all: its credential, or no need for one.

    What the dashboard shows as "has key" and uses to grey out a provider. For
    the API backends it is exactly "the key is set"; for the CLI one a missing
    token is fine and a missing binary is not.
    """
    provider = provider_for(name)
    if not (api_key(name) or provider.key_optional):
        return False
    return not (provider.preflight and provider.preflight())


def client_for(task: str) -> StructuredClient:
    """The client ``llm.<task>`` (or ``llm.provider``) asks for."""
    from jobpilot.config import get_config

    cfg = get_config().llm
    name = cfg.for_task(task)
    return provider_for(name).build(cfg.model_for(task), api_key(name), task)


def list_models(name: str) -> list[str]:
    """Model ids the provider says this key can use, newest-looking last.

    Live rather than hardcoded, because a static list rots in the direction that
    hurts: it keeps offering models that have been withdrawn. It is not a
    guarantee either — Gemini happily *lists* ``gemini-2.5-flash`` and then
    answers ``generateContent`` with 404 "no longer available to new users". So
    the picker treats this as a menu, not a promise, and ``llm bench`` remains
    the thing that proves a model works.

    Returns [] rather than raising: a provider you have no key for should leave
    the other two pickers working.
    """
    key = api_key(name)
    if not key:
        return []
    try:
        if name == "claude":
            import anthropic

            return sorted(m.id for m in anthropic.Anthropic(api_key=key).models.list(limit=100))
        if name == "openai":
            import openai

            return sorted(m.id for m in openai.OpenAI(api_key=key).models.list())
        if name == "gemini":
            from google import genai

            # The client is bound to a name on purpose. Inlining it into the
            # comprehension lets it be garbage-collected while the lazy pager is
            # still iterating, and the SDK then fails with "Cannot send a
            # request, as the client has been closed" — which reads like an
            # auth problem and is not one.
            client = genai.Client(api_key=key)
            return sorted(
                m.name.removeprefix("models/")
                for m in client.models.list()
                if "generateContent" in (m.supported_actions or [])
            )
    except Exception as exc:  # network, auth, SDK absent — all "no menu right now"
        # Logged, not silent. An empty picker and a broken picker look identical
        # from the outside, and this repo has already paid once for a swallowed
        # failure nobody could see (see ``llm/usage.record``).
        #
        # Redacted, because a rejected key is the most likely thing in here and
        # a log file is as durable as a database column.
        from jobpilot.llm.redact import redact

        logging.getLogger(__name__).warning(
            "could not list %s models: %s", name, redact(str(exc))
        )
        return []
    return []
