"""The API token: comparing it, and refusing to run without a real one.

Shared by the REST dependency and the WebSocket handshake so the two cannot
drift into checking the same secret by different rules.

What this token is *not*: a defence against a stranger who can reach the port.
The dashboard is a static bundle, and a static bundle has to be downloadable
before it can ask for credentials — so the token it authenticates with is
compiled into it (``web/src/lib/api.ts``). Anyone able to load the page can read
it out of the JavaScript. That is acceptable exactly as long as reaching the
page requires being on the Tailnet; the network is the authentication, and this
token only stops stray same-machine callers. Expose the port publicly and the
token buys nothing — see ``jobpilot/api/CLAUDE.md``.
"""

from __future__ import annotations

import hmac
import secrets

#: Long enough that ``llm/redact.py`` will also scrub it out of logs, whose
#: floor is 12 characters. A token below that leaks into every traceback that
#: happens to quote a request URL.
MIN_API_TOKEN_LEN = 20

#: Values that mean "nobody chose a token". Checked case-insensitively.
PLACEHOLDER_TOKENS = frozenset({"changeme", "change-me", "changethis", "secret", "token", "test"})


def generate_token() -> str:
    """A fresh token worth putting in ``.env``."""
    return secrets.token_urlsafe(32)


def token_problem(token: str | None) -> str:
    """Why ``token`` is unfit to protect the API, or '' if it is fine."""
    if not token:
        return "JOBPILOT_API_TOKEN is empty"
    if token.lower() in PLACEHOLDER_TOKENS:
        return f"JOBPILOT_API_TOKEN is still the placeholder {token!r}"
    if len(token) < MIN_API_TOKEN_LEN:
        return (
            f"JOBPILOT_API_TOKEN is {len(token)} characters — "
            f"at least {MIN_API_TOKEN_LEN} are required"
        )
    return ""


def check_api_token(token: str | None = None) -> None:
    """Raise unless the configured token is a real one.

    Called at startup rather than on first request: a server that boots and then
    rejects everything looks like a bug in the dashboard, while one that refuses
    to boot names the problem once, in the log, where somebody is already
    looking.
    """
    if token is None:
        from jobpilot.config import get_secrets

        token = get_secrets().jobpilot_api_token

    problem = token_problem(token)
    if problem:
        raise RuntimeError(
            f"refusing to start: {problem}.\n"
            f"Put this in .env and in web/.env.local (as VITE_API_TOKEN), "
            f"then rebuild the dashboard:\n\n"
            f"    JOBPILOT_API_TOKEN={generate_token()}\n"
        )


def token_matches(given: str | None, expected: str | None) -> bool:
    """Constant-time token comparison.

    ``==`` on strings returns as soon as two bytes differ, so the time it takes
    to say "no" describes how much of the token was right. Over a network that
    is noisy, but this process also answers on loopback, where it is not.
    """
    if not given or not expected:
        return False
    return hmac.compare_digest(given, expected)
