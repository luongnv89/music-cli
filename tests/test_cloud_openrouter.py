"""Tests for the OpenRouter adapter (issue #133, task P1.2).

Every request is served from a recorded fixture transcript
(``tests/fixtures/openrouter_recorded.json``); no test in this module
touches the network.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from music_cli.cloud import AdapterError, DiskStrategyCache, OpenRouterAdapter
from music_cli.cloud.base import idempotency_key
from music_cli.cloud.openrouter import M3_MODEL, M27_MODEL, OPENROUTER_CHAT_URL

FAKE_API_KEY = "or-test-secret-value-4d81"  # noqa: S105 - fake value, never a real credential

FIXTURES = Path(__file__).parent / "fixtures"

Step = tuple[str, str, int, dict[str, Any]]


def load_fixture() -> dict[str, Any]:
    return json.loads((FIXTURES / "openrouter_recorded.json").read_text(encoding="utf-8"))


class RecordedTransport:
    """Replays a recorded fixture transcript and records every request."""

    def __init__(self, script: list[Step]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self, method: str, url: str, headers: dict[str, str], payload: dict | None
    ) -> tuple[int, Any]:
        self.calls.append(
            {"method": method, "url": url, "headers": dict(headers), "payload": payload}
        )
        for i, (want_method, substring, status, body) in enumerate(self.script):
            if want_method == method and substring in url:
                del self.script[i]
                return status, body
        raise AssertionError(f"unexpected request: {method} {url}; remaining={self.script!r}")


def make_adapter(transport, tmp_path=None, **kwargs) -> OpenRouterAdapter:
    cache = DiskStrategyCache(tmp_path / "cache") if tmp_path else None
    return OpenRouterAdapter(
        FAKE_API_KEY,
        cache=cache,
        transport=transport,
        backoff_base=0.001,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# acceptance criteria: exposed task methods
# ---------------------------------------------------------------------------


def test_openrouter_adapter_exposes_task_methods():
    adapter = make_adapter(RecordedTransport([]))
    for name in ("m3_chat", "m27_chat", "speech28_synthesize"):
        method = getattr(adapter, name, None)
        assert callable(method), f"OpenRouterAdapter missing task method {name}"
        assert asyncio.iscoroutinefunction(method)


# ---------------------------------------------------------------------------
# chat completions
# ---------------------------------------------------------------------------


async def test_m3_chat_returns_recorded_text(tmp_path):
    fixture = load_fixture()
    transport = RecordedTransport(chat_script(fixture["m3_chat_completion"]))
    adapter = make_adapter(transport, tmp_path)
    result = await adapter.m3_chat("draft a plan")
    expected = fixture["m3_chat_completion"]["body"]["choices"][0]["message"]["content"]
    assert result["text"] == expected
    assert transport.calls[0]["payload"]["model"] == M3_MODEL


async def test_m27_chat_targets_m27_model(tmp_path):
    fixture = load_fixture()
    transport = RecordedTransport(chat_script(fixture["m27_chat_completion"]))
    adapter = make_adapter(transport, tmp_path)
    result = await adapter.m27_chat("hello")
    expected = fixture["m27_chat_completion"]["body"]["choices"][0]["message"]["content"]
    assert result["text"] == expected
    assert transport.calls[0]["payload"]["model"] == M27_MODEL


async def test_speech28_synthesize_returns_recorded_text(tmp_path):
    fixture = load_fixture()
    transport = RecordedTransport(chat_script(fixture["speech28_completion"]))
    adapter = make_adapter(transport, tmp_path)
    result = await adapter.speech28_synthesize("say hello")
    expected = fixture["speech28_completion"]["body"]["choices"][0]["message"]["content"]
    assert result["text"] == expected


async def test_cache_hit_returns_instantly(tmp_path):
    fixture = load_fixture()
    transport = RecordedTransport(chat_script(fixture["m3_chat_completion"]))
    adapter = make_adapter(transport, tmp_path)
    first = await adapter.m3_chat("draft a plan")
    second = await adapter.m3_chat("draft a plan")
    assert first == second
    assert len(transport.calls) == 1


def chat_script(entry: dict, times: int = 1) -> list[Step]:
    return [("POST", OPENROUTER_CHAT_URL, entry["status_code"], entry["body"])] * times


# ---------------------------------------------------------------------------
# run(): retries with exponential backoff
# ---------------------------------------------------------------------------


async def test_run_retries_transient_errors_then_succeeds(tmp_path):
    fixture = load_fixture()
    transport = RecordedTransport(
        [("POST", OPENROUTER_CHAT_URL, 429, {"error": "rate limited"})]
        + chat_script(fixture["m3_chat_completion"])
    )
    adapter = make_adapter(transport, tmp_path)
    result = await adapter.m3_chat("draft a plan")
    expected = fixture["m3_chat_completion"]["body"]["choices"][0]["message"]["content"]
    assert result["text"] == expected
    assert len(transport.calls) == 2


async def test_run_gives_up_after_three_attempts(tmp_path):
    transport = RecordedTransport(
        [("POST", OPENROUTER_CHAT_URL, 500, {"error": "down"}) for _ in range(3)]
    )
    adapter = make_adapter(transport, tmp_path)
    with pytest.raises(AdapterError) as excinfo:
        await adapter.m3_chat("still down")
    assert "3 attempts" in str(excinfo.value)
    assert len(transport.calls) == 3


# ---------------------------------------------------------------------------
# idempotency keys
# ---------------------------------------------------------------------------


async def test_idempotency_keys_differ_per_logical_request(tmp_path):
    fixture = load_fixture()
    script = chat_script(fixture["m3_chat_completion"]) + chat_script(
        fixture["m27_chat_completion"]
    )
    transport = RecordedTransport(script)
    adapter = make_adapter(transport, tmp_path)
    await adapter.m3_chat("prompt A")
    await adapter.m27_chat("prompt B")
    key_m3 = transport.calls[0]["headers"]["Idempotency-Key"]
    key_m27 = transport.calls[1]["headers"]["Idempotency-Key"]
    assert key_m3 == idempotency_key("openrouter", M3_MODEL, "prompt A")
    assert key_m27 == idempotency_key("openrouter", M27_MODEL, "prompt B")
    assert key_m3 != key_m27


async def test_bearer_token_sent_from_api_key(tmp_path):
    fixture = load_fixture()
    transport = RecordedTransport(chat_script(fixture["m3_chat_completion"]))
    adapter = make_adapter(transport, tmp_path)
    await adapter.m3_chat("hi")
    assert transport.calls[0]["headers"]["Authorization"] == f"Bearer {FAKE_API_KEY}"
