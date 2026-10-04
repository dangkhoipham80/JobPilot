"""Claude through the local ``claude`` CLI, billed to a Claude subscription.

The ``claude`` provider pays per token through an API key. This one runs the
same models through Claude Code's print mode (``claude -p``), authenticated with
the user's own Pro/Max plan: the calls count against the plan's usage limits
instead of costing money. It exists because JobPilot runs on the user's own
machine, where Claude Code is already installed and paid for.

Personal use only. Anthropic does not allow *products* to offer claude.ai login
to their users; one person automating their own subscription on their own
machine is a different thing, but it is not the documented path for scripts
either (that is "bare mode", which requires an API key). If this stops working
one day, the ``claude`` provider is the fallback and nothing above this module
has to change.

What the subprocess is told, and why each flag is there:

- ``--json-schema`` + ``--output-format json``: the answer comes back in
  ``structured_output``, validated against the schema by the CLI, then again by
  Pydantic here.
- ``--system-prompt-file`` *replaces* Claude Code's own ~32k-token system prompt.
  Measured: 32,198 input tokens per call with the default, ~1,200 without. On a
  plan, tokens are the currency, so this is the difference between a few
  hundred calls and a few dozen. A file, not ``--system-prompt <text>``: for
  tailor the system prompt is the whole Master CV, and argv is readable by every
  process on the machine (``ps``) for the minute a tailor takes. On Windows an
  npm-installed ``claude.cmd`` also runs through cmd.exe, which cuts a
  multi-line argument at its first newline — the model would get a CV with
  everything after line one missing, and still answer.
- ``--tools ""``, ``--strict-mcp-config``, ``--setting-sources ""``: a call that
  extracts JSON has no business reading files, running commands, reaching MCP
  servers or inheriting the user's hooks.
- ``--no-session-persistence``: every tailor would otherwise leave a resumable
  session containing the whole Master CV under ``~/.claude``.
- An empty temporary working directory, so no ``CLAUDE.md`` is picked up — the
  repo's own would add tokens and pour project notes into a CV prompt.
- ``ANTHROPIC_API_KEY`` (and the Bedrock/Vertex/base-URL switches) are removed
  from the child's environment. The CLI prefers them over the subscription, and
  the result would be per-token billing recorded as free.
- Before the first call, ``claude auth status`` must say the login *is* a
  subscription. A Console login bills per token too; recording that as $0 is a
  wrong answer that looks right.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from jobpilot.llm.base import Completion, LlmError, Usage

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-opus-4-8"

#: A tailor round on Opus is the slowest call JobPilot makes; this is generous
#: on purpose. A hung CLI (network, a prompt it is waiting on) must still end.
TIMEOUT_S = 600

#: Where installers put the binary. launchd hands agents a PATH without
#: ``~/.local/bin``, which is where the native installer puts ``claude`` — so a
#: lookup that only trusts PATH works from a terminal and fails as a service.
_CANDIDATES = (
    "~/.local/bin/claude",
    "~/.claude/local/claude",
    "/opt/homebrew/bin/claude",
    "/usr/local/bin/claude",
)


def find_claude() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    for candidate in _CANDIDATES:
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


#: Credentials and switches that would move the CLI off the subscription onto
#: per-token billing — removed from the child's environment.
_API_BILLING_VARS = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_FOUNDRY",
    }
)

#: How long one `claude auth status` answer is trusted. Long enough that the
#: dashboard (which asks for every task's blocker on each load) does not spawn
#: the CLI four times per page view; short enough that a logout shows up.
_AUTH_TTL_S = 300
_auth_cache: dict[str, tuple[float, str]] = {}


def child_env(token: str = "") -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _API_BILLING_VARS}
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    return env


def subscription_problem(token: str = "", *, runner: Any = None) -> str:
    """Why the CLI's login is not a Claude subscription, or '' when it is.

    The whole point of this provider is that a call costs nothing extra, and it
    records ``cost_usd = 0.0`` on that basis. That is only true for a claude.ai
    login: the same CLI logged in to a Console account, or pointed at Bedrock,
    bills per token. Fail closed — an answer that cannot be read is a reason,
    not a pass.
    """
    key = "token" if token else "login"
    cached = _auth_cache.get(key)
    if runner is None and cached and time.monotonic() - cached[0] < _AUTH_TTL_S:
        return cached[1]
    binary = find_claude()
    if binary is None and runner is None:
        return _NOT_INSTALLED
    try:
        proc = (runner or subprocess.run)(
            [binary or "claude", "auth", "status", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=child_env(token),
            timeout=30,
        )
        status = json.loads(proc.stdout or "")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        reason = f"could not confirm the claude login is a subscription (claude auth status: {exc})"
    else:
        reason = _judge(status if isinstance(status, dict) else {})
    if runner is None:
        _auth_cache[key] = (time.monotonic(), reason)
    return reason


def _judge(status: dict) -> str:
    if not status.get("loggedIn"):
        return "claude is not logged in on this machine — run `claude` and /login"
    if status.get("apiProvider", "firstParty") != "firstParty":
        return f"claude is set to bill through {status['apiProvider']}, not a Claude subscription"
    if status.get("authMethod") != "claude.ai" and not status.get("subscriptionType"):
        return (
            f"claude is logged in with {status.get('authMethod') or 'an unknown method'}, which "
            "bills per token — log in with your Claude subscription (/login) or use the "
            "`claude` provider"
        )
    return ""


_NOT_INSTALLED = (
    "the claude CLI is not installed (or not where JobPilot looks: PATH, "
    "~/.local/bin, ~/.claude/local, /opt/homebrew/bin, /usr/local/bin)"
)


def preflight() -> str:
    """Why this provider can't run here, or '' — checked before a task queues."""
    if find_claude() is None:
        return _NOT_INSTALLED
    from jobpilot.llm.registry import api_key

    return subscription_problem(api_key("claude_cli"))


@dataclass
class ClaudeCliClient:
    model: str = DEFAULT_MODEL
    #: ``CLAUDE_CODE_OAUTH_TOKEN`` from ``claude setup-token``. Optional: empty
    #: means the CLI uses the machine's own claude.ai login, which a launchd
    #: agent in the user's session can reach (verified). Set it only where no
    #: login session exists — ssh, or a machine nobody logs in to.
    token: str = ""
    #: ``--effort`` for the reading tasks; None leaves the CLI's default.
    effort: str | None = None
    #: Injected ``subprocess.run`` stand-in for tests.
    runner: Any = None

    provider: str = "claude_cli"

    def structured(self, *, system: str, messages: list[dict], schema: type[T]) -> Completion[T]:
        binary = find_claude()
        if self.runner is None:
            # Here as well as in the blocker: not every caller goes through a
            # route (`cli tailor`, `llm bench`), and a $0 row for a billed call
            # is the failure this exists to prevent. Cached, so it is one
            # `claude auth status` per few minutes, not one per call.
            problem = _NOT_INSTALLED if binary is None else subscription_problem(self.token)
            if problem:
                raise LlmError(f"claude_cli: {problem}")
        started = time.monotonic()
        # 0700, removed on exit — the system prompt file holds the Master CV.
        with tempfile.TemporaryDirectory(prefix="jobpilot-claude-") as workdir:
            system_file = Path(workdir) / "system.txt"
            system_file.write_text(system, encoding="utf-8")
            argv = [
                binary or "claude",
                "-p",
                "--output-format",
                "json",
                "--no-session-persistence",
                "--tools",
                "",
                "--strict-mcp-config",
                "--setting-sources",
                "",
                "--model",
                self.model,
                "--system-prompt-file",
                str(system_file),
                "--json-schema",
                json.dumps(schema.model_json_schema()),
            ]
            if self.effort:
                argv += ["--effort", self.effort]
            run = self.runner or subprocess.run
            try:
                proc = run(
                    argv,
                    input=_prompt(messages),
                    capture_output=True,
                    text=True,
                    # Explicit: on Windows the locale default is cp1252, and a
                    # Vietnamese JD on stdin raises UnicodeEncodeError.
                    encoding="utf-8",
                    cwd=workdir,
                    env=child_env(self.token),
                    timeout=TIMEOUT_S,
                )
            except subprocess.TimeoutExpired as exc:
                raise LlmError(f"claude CLI did not answer within {TIMEOUT_S}s") from exc
            except OSError as exc:
                raise LlmError(f"could not start the claude CLI: {exc}") from exc
        return self._unpack(proc, schema, started)

    def _unpack(self, proc: Any, schema: type[T], started: float) -> Completion[T]:
        try:
            data = json.loads(proc.stdout or "")
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, dict):
            detail = (proc.stderr or proc.stdout or "").strip()[-500:]
            raise LlmError(f"claude CLI failed (exit {proc.returncode}): {detail or 'no output'}")
        if data.get("is_error") or proc.returncode != 0:
            # The CLI puts its own explanation in `result` — a usage limit, a
            # rejected token, a schema it could not satisfy. Passed on verbatim
            # (LlmError scrubs credentials) rather than translated: its wording
            # for the limit case is undocumented, and a guess at it would be
            # wrong the first time it changes.
            reason = str(data.get("result") or data.get("subtype") or "unknown error")
            raise LlmError(f"claude CLI error (exit {proc.returncode}): {reason[:500]}")
        raw = data.get("structured_output")
        if raw is None:
            raise LlmError(f"claude CLI returned no structured output for {schema.__name__}")
        try:
            value = schema.model_validate(raw)
        except ValidationError as exc:
            raise LlmError(f"claude CLI output does not fit {schema.__name__}: {exc}") from exc
        return Completion(value=value, usage=self._usage(data, started))

    def _usage(self, data: dict, started: float) -> Usage:
        raw = data.get("usage") or {}
        cached = _int(raw, "cache_read_input_tokens")
        inp = _int(raw, "input_tokens") + cached + _int(raw, "cache_creation_input_tokens")
        return Usage(
            input_tokens=inp,
            output_tokens=_int(raw, "output_tokens"),
            cached_input_tokens=cached,
            latency_ms=int((time.monotonic() - started) * 1000),
            provider=self.provider,
            model=self.model,
            # Zero, not None. None means "we don't know the price"; here we do —
            # the plan is paid for whether or not JobPilot calls it, so a call
            # costs nothing extra. The CLI's own `total_cost_usd` is what the
            # same tokens would cost on the API, which is not what anyone paid.
            cost_usd=0.0,
        )


def _prompt(messages: list[dict]) -> str:
    """The turns as one prompt — print mode takes a single user message.

    A first attempt is one user turn and goes through as-is. A retry carries the
    rejected answer and the correction, and those are laid out as a transcript
    so the model can see what it said and what was wrong with it.
    """
    if len(messages) == 1:
        return str(messages[0].get("content") or "")
    turns = [
        f"<{m.get('role', 'user')}>\n{m.get('content') or ''}\n</{m.get('role', 'user')}>"
        for m in messages
    ]
    return "The conversation so far is below. Answer the final user turn.\n\n" + "\n\n".join(turns)


def _int(obj: dict, name: str) -> int:
    value = obj.get(name)
    return int(value) if isinstance(value, int) else 0
