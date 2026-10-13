"""Anthropic, behind the ``StructuredClient`` contract.

This is the path that has been in production since Phase 5; the only change is
that the three engines used to each carry their own copy of the client setup.
The request shape — adaptive thinking, an ephemeral cache breakpoint on the
system prompt, ``messages.parse`` with a Pydantic output format — is unchanged,
because it was measured and it works.

The cache breakpoint earns more than it looks like: the system prompt is the
whole Master CV and is byte-identical across every job, so the expensive half of
a tailor round is a cache read on the second and subsequent calls.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel

from jobpilot.llm.base import Attachment, Completion, LlmError, Usage, attachments_of
from jobpilot.llm.pricing import estimate_cost

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-opus-4-8"
MAX_TOKENS = 16000


def file_block(attachment: Attachment) -> dict:
    """One attachment as an Anthropic content block.

    Shared with ``claude_cli``: print mode's ``stream-json`` input takes the
    Messages API's own blocks, so the two Claude backends cannot disagree about
    what a PDF looks like on the wire.
    """
    return {
        "type": "document" if attachment.is_pdf else "image",
        "source": {
            "type": "base64",
            "media_type": attachment.media_type,
            "data": attachment.b64(),
        },
    }


def wire_message(message: dict) -> dict:
    """A turn in the Messages API's shape. Text-only turns pass through as-is."""
    files = attachments_of(message)
    if not files:
        return {"role": message.get("role", "user"), "content": message.get("content") or ""}
    # Files first, question last — the order Anthropic's vision docs recommend.
    return {
        "role": message.get("role", "user"),
        "content": [
            *(file_block(a) for a in files),
            {"type": "text", "text": message.get("content") or ""},
        ],
    }


@dataclass
class ClaudeClient:
    model: str = DEFAULT_MODEL
    api_key: str = ""
    #: Injected SDK client; tests pass a fake, production leaves it None.
    client: Any = None
    #: Extended thinking. On for the two judgement-heavy calls, off for
    #: classify — six labels and a copied sentence do not need deliberation.
    #: Also a hard compatibility matter: the cheaper models reject the parameter
    #: outright ("adaptive thinking is not supported on this model"), so leaving
    #: it always-on would make the cheap tier unreachable rather than merely
    #: expensive.
    thinking: bool = True

    provider: str = "claude"

    def _sdk(self) -> Any:
        if self.client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - env dependent
                raise LlmError(
                    "anthropic SDK not installed — run: pip install -e '.[tailor]'"
                ) from exc
            # An empty key is still worth attempting: the SDK also resolves
            # ANTHROPIC_AUTH_TOKEN and an `ant auth login` profile.
            self.client = (
                anthropic.Anthropic(api_key=self.api_key) if self.api_key else anthropic.Anthropic()
            )
        return self.client

    def structured(self, *, system: str, messages: list[dict], schema: type[T]) -> Completion[T]:
        started = time.monotonic()
        try:
            response = self._send(system, messages, schema)
        except Exception as exc:  # SDK raises typed errors; surface them as one kind
            # A model that does not take the thinking parameter says so in a
            # 400. Turn it off for good on this client and ask once more, rather
            # than reporting a compatibility detail as a dead backend — the
            # alternative is a hardcoded list of which models support it, which
            # is wrong the week a model ships.
            if self.thinking and "thinking is not supported" in str(exc):
                self.thinking = False
                try:
                    response = self._send(system, messages, schema)
                except Exception as retry_exc:
                    raise LlmError(f"Claude request failed: {retry_exc}") from retry_exc
            else:
                raise LlmError(f"Claude request failed: {exc}") from exc

        return self._unpack(response, schema, started)

    def _send(self, system: str, messages: list[dict], schema: type[T]) -> Any:
        extra = {"thinking": {"type": "adaptive"}} if self.thinking else {}
        return self._sdk().messages.parse(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": system,
                    # Only takes effect once the prefix clears the model's
                    # minimum cacheable size; harmless below it.
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[wire_message(m) for m in messages],
            output_format=schema,
            **extra,
        )

    def _unpack(self, response: Any, schema: type[T], started: float) -> Completion[T]:
        if getattr(response, "stop_reason", None) == "refusal":
            raise LlmError("Claude declined this request (stop_reason=refusal)")
        value = getattr(response, "parsed_output", None)
        if value is None:
            raise LlmError(f"Claude returned no parsable {schema.__name__}")
        return Completion(value=value, usage=self._usage(response, started))

    def _usage(self, response: Any, started: float) -> Usage:
        raw = getattr(response, "usage", None)
        cached = _int(raw, "cache_read_input_tokens")
        # Cache reads are billed, and are not included in input_tokens — count
        # them in so the token totals match what the invoice will say.
        inp = _int(raw, "input_tokens") + cached
        out = _int(raw, "output_tokens")
        return Usage(
            input_tokens=inp,
            output_tokens=out,
            cached_input_tokens=cached,
            latency_ms=int((time.monotonic() - started) * 1000),
            provider=self.provider,
            model=self.model,
            cost_usd=estimate_cost(self.provider, self.model, inp, out),
        )


def _int(obj: Any, name: str) -> int:
    """A usage field, or 0 — SDKs leave these unset more often than documented."""
    value = getattr(obj, name, None)
    return int(value) if isinstance(value, int) else 0
