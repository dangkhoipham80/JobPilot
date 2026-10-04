"""The `claude_cli` provider: Claude through the local CLI, on a subscription.

No real subprocess here — `runner` stands in for `subprocess.run` and records
what it was asked to run. A live call is in PHASES.md, not in CI: it spends the
user's plan, and CI has no logged-in `claude`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from pydantic import BaseModel

from jobpilot.llm.base import LlmError
from jobpilot.llm.claude_cli import ClaudeCliClient, _prompt


class Verdict(BaseModel):
    label: str
    reason: str


class FakeRun:
    """Records the call; answers with a canned CLI JSON result."""

    def __init__(
        self, payload: dict | None = None, *, returncode: int = 0, stdout: str | None = None
    ):
        self.payload = payload
        self.returncode = returncode
        self.stdout = stdout
        self.calls: list[dict] = []

    def __call__(self, argv, **kwargs):
        call = {"argv": argv, **kwargs}
        if "--system-prompt-file" in argv:
            # Read while the call is "running": the file lives in a temp dir
            # that is gone once structured() returns.
            call["system_file"] = argv[argv.index("--system-prompt-file") + 1]
            call["system"] = Path(call["system_file"]).read_text(encoding="utf-8")
        self.calls.append(call)
        out = self.stdout if self.stdout is not None else json.dumps(self.payload)
        return subprocess.CompletedProcess(argv, self.returncode, stdout=out, stderr="boom")


OK = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": '{"label":"interview","reason":"invited"}',
    "structured_output": {"label": "interview", "reason": "invited"},
    "total_cost_usd": 0.0029,
    "usage": {
        "input_tokens": 1194,
        "cache_creation_input_tokens": 10,
        "cache_read_input_tokens": 100,
        "output_tokens": 345,
    },
}


def _call(run: FakeRun, **client_kw):
    client = ClaudeCliClient(model="claude-haiku-4-5", runner=run, **client_kw)
    return client.structured(
        system="You classify recruiter email.",
        messages=[{"role": "user", "content": "Thư mời phỏng vấn"}],
        schema=Verdict,
    )


def test_the_answer_comes_from_structured_output_and_costs_nothing():
    done = _call(FakeRun(OK))
    assert done.value == Verdict(label="interview", reason="invited")
    assert done.usage.provider == "claude_cli"
    assert done.usage.model == "claude-haiku-4-5"
    # The plan is paid for either way: zero, and *known* to be zero — not the
    # CLI's API-equivalent `total_cost_usd`, and not None ("price unknown").
    assert done.usage.cost_usd == 0.0
    assert done.usage.input_tokens == 1194 + 10 + 100
    assert done.usage.cached_input_tokens == 100
    assert done.usage.output_tokens == 345


def test_the_cli_is_locked_down_and_replaces_its_own_system_prompt():
    run = FakeRun(OK)
    _call(run, effort="low")
    argv = run.calls[0]["argv"]

    def value(flag):
        return argv[argv.index(flag) + 1]

    assert argv[1] == "-p"
    # Without this the CLI's own ~32k-token prompt rides along on every call.
    # A file, never argv: for tailor it is the whole Master CV, and argv is
    # readable by every process on the machine.
    assert run.calls[0]["system"] == "You classify recruiter email."
    assert "--system-prompt" not in argv
    assert not any("recruiter email" in a for a in argv)
    assert run.calls[0]["system_file"].startswith(run.calls[0]["cwd"])
    assert value("--tools") == ""
    assert value("--setting-sources") == ""
    assert "--strict-mcp-config" in argv
    assert "--no-session-persistence" in argv  # no Master CV left under ~/.claude
    assert value("--output-format") == "json"
    assert value("--model") == "claude-haiku-4-5"
    assert value("--effort") == "low"
    assert json.loads(value("--json-schema"))["required"] == ["label", "reason"]
    # The prompt goes in on stdin, not argv — as UTF-8 on every platform.
    assert run.calls[0]["input"] == "Thư mời phỏng vấn"
    assert run.calls[0]["encoding"] == "utf-8"


def test_it_runs_outside_the_repo_so_no_claude_md_is_picked_up():
    run = FakeRun(OK)
    _call(run)
    cwd = Path(run.calls[0]["cwd"])
    assert "jobpilot-claude-" in cwd.name
    assert not (cwd / "CLAUDE.md").exists()


def test_an_api_key_in_the_environment_cannot_turn_this_into_api_billing(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-pass")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "also-not")
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://proxy.example")
    run = FakeRun(OK)
    _call(run, token="oauth-token-from-setup-token")
    env = run.calls[0]["env"]
    for var in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_CODE_USE_BEDROCK",
        "ANTHROPIC_BASE_URL",
    ):
        assert var not in env
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "oauth-token-from-setup-token"


def test_a_cli_error_is_reported_with_its_own_words():
    run = FakeRun(
        {"type": "result", "subtype": "error", "is_error": True, "result": "Usage limit reached"},
        returncode=1,
    )
    with pytest.raises(LlmError, match="Usage limit reached"):
        _call(run)


def test_output_that_is_not_json_is_an_error_not_a_crash():
    with pytest.raises(LlmError, match="exit 1"):
        _call(FakeRun(stdout="Error: not logged in", returncode=1))


def test_an_answer_that_does_not_fit_the_schema_is_refused():
    bad = {**OK, "structured_output": {"label": "interview"}}
    with pytest.raises(LlmError, match="does not fit Verdict"):
        _call(FakeRun(bad))


def test_a_retry_is_laid_out_as_a_transcript():
    prompt = _prompt(
        [
            {"role": "user", "content": "Tailor this."},
            {"role": "assistant", "content": '{"plan": 1}'},
            {"role": "user", "content": "Bullet 7 does not exist."},
        ]
    )
    assert prompt.index("<user>\nTailor this.") < prompt.index("<assistant>")
    assert prompt.rstrip().endswith("Bullet 7 does not exist.\n</user>")
    assert "final user turn" in prompt


def test_a_token_is_optional_but_the_cli_is_not(monkeypatch):
    from jobpilot import llm
    from jobpilot.config import Config, LlmCfg, Secrets

    cfg = Config()
    cfg.llm = LlmCfg(provider="claude_cli")
    monkeypatch.setattr("jobpilot.config.get_config", lambda *a, **k: cfg)

    monkeypatch.setattr(
        "jobpilot.config.get_secrets", lambda *a, **k: Secrets(claude_code_oauth_token="")
    )
    from jobpilot.llm.registry import ready

    # No token: fine — a logged-in `claude` on this machine is enough.
    monkeypatch.setattr("jobpilot.llm.claude_cli.find_claude", lambda: "/usr/local/bin/claude")
    monkeypatch.setattr("jobpilot.llm.claude_cli.subscription_problem", lambda *a, **k: "")
    assert llm.blocker("tailor") == ""
    assert ready("claude_cli") is True

    # Installed but not on a subscription: blocked, with the CLI's reason.
    monkeypatch.setattr(
        "jobpilot.llm.claude_cli.subscription_problem",
        lambda *a, **k: "claude is logged in with console, which bills per token",
    )
    assert "bills per token" in llm.blocker("tailor")
    assert ready("claude_cli") is False

    # No binary: blocked, token or not — and shown as unusable, not "has key".
    monkeypatch.setattr("jobpilot.llm.claude_cli.find_claude", lambda: None)
    assert "claude CLI is not installed" in llm.blocker("tailor")
    assert ready("claude_cli") is False
    monkeypatch.setattr(
        "jobpilot.config.get_secrets", lambda *a, **k: Secrets(claude_code_oauth_token="tok")
    )
    assert "claude CLI is not installed" in llm.blocker("tailor")

    # The API backends still need their key.
    monkeypatch.setattr("jobpilot.config.get_secrets", lambda *a, **k: Secrets())
    assert ready("openai") is False


def test_the_subscription_terms_are_spelled_out_before_the_cv_goes(monkeypatch):
    """Same models as `claude`, different contract: consumer terms, where
    training follows the account's "Help improve Claude" setting."""
    from jobpilot import llm
    from jobpilot.config import Config, LlmCfg

    cfg = Config()
    cfg.llm = LlmCfg(provider="claude_cli")
    monkeypatch.setattr("jobpilot.config.get_config", lambda *a, **k: cfg)
    warned = " ".join(llm.warnings("tailor"))
    assert "Help improve Claude" in warned
    assert "Master CV" in warned


def test_reading_tasks_ask_for_low_effort_writing_tasks_do_not():
    from jobpilot.llm.registry import PROVIDERS

    build = PROVIDERS["claude_cli"].build
    assert build("claude-haiku-4-5", "t", "classify").effort == "low"
    assert build("claude-haiku-4-5", "t", "intake").effort == "low"
    assert build("claude-opus-4-8", "t", "tailor").effort is None


def _status(payload=None, *, stdout=None):
    def run(argv, **kwargs):
        assert argv[1:] == ["auth", "status", "--json"]
        out = stdout if stdout is not None else json.dumps(payload)
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")

    return run


@pytest.mark.parametrize(
    ("status", "verdict"),
    [
        (
            {
                "loggedIn": True,
                "authMethod": "claude.ai",
                "apiProvider": "firstParty",
                "subscriptionType": "max",
            },
            "",
        ),
        ({"loggedIn": False}, "not logged in"),
        (
            {"loggedIn": True, "authMethod": "console", "apiProvider": "firstParty"},
            "bills per token",
        ),
        ({"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "bedrock"}, "bedrock"),
    ],
)
def test_only_a_subscription_login_counts_as_free(status, verdict):
    """`cost_usd = 0.0` is only true on a claude.ai plan. The same CLI on a
    Console login or Bedrock bills per token, and recording that as free is a
    wrong number that looks right."""
    from jobpilot.llm.claude_cli import subscription_problem

    got = subscription_problem(runner=_status(status))
    assert (got == "") if verdict == "" else (verdict in got)


def test_an_unreadable_auth_status_fails_closed():
    from jobpilot.llm.claude_cli import subscription_problem

    assert "could not confirm" in subscription_problem(
        runner=_status(stdout="Error: unknown command")
    )


def test_a_billed_login_stops_the_call_before_it_is_made(monkeypatch):
    monkeypatch.setattr("jobpilot.llm.claude_cli.find_claude", lambda: "/usr/local/bin/claude")
    monkeypatch.setattr(
        "jobpilot.llm.claude_cli.subscription_problem", lambda *a, **k: "bills per token"
    )
    client = ClaudeCliClient(model="claude-haiku-4-5")
    with pytest.raises(LlmError, match="bills per token"):
        client.structured(system="s", messages=[{"role": "user", "content": "x"}], schema=Verdict)
