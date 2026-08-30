"""Tests for the GMI Cloud adapter (issue #133, task P1.2).

Every request is served from a recorded fixture transcript
(``tests/fixtures/gmi_recorded.json``); no test in this module touches
the network.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from music_cli.cloud import (
    AdapterError,
    DiskStrategyCache,
    GMIAdapter,
    PollCancelledError,
    TransientError,
    cache_key,
)
from music_cli.cloud.base import idempotency_key
from music_cli.cloud.gmi import GMI_QUEUE_URL, GMI_SERVING_CHAT_URL, MUSIC_MODEL, SPEECH_MODEL

FAKE_API_KEY = "gmi-test-secret-value-9f2c"  # noqa: S105 - fake value, never a real credential

FIXTURES = Path(__file__).parent / "fixtures"

Step = tuple[str, str, int, dict[str, Any]]


def load_fixture() -> dict[str, Any]:
    return json.loads((FIXTURES / "gmi_recorded.json").read_text(encoding="utf-8"))


class RecordedTransport:
    """Replays a recorded fixture transcript and records every request."""

    def __init__(self, script: list[Step]) -> None:
        # script: list of (method, url_substring, status_code, body)
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


def make_adapter(transport, tmp_path=None, **kwargs) -> GMIAdapter:
    cache = DiskStrategyCache(tmp_path / "cache") if tmp_path else None
    options = {
        "backoff_base": 0.001,
        "poll_interval": 0.001,
        "poll_timeout": 5.0,
        **kwargs,
    }
    return GMIAdapter(FAKE_API_KEY, cache=cache, transport=transport, **options)


def chat_script(entry: dict, times: int = 1) -> list[Step]:
    return [("POST", GMI_SERVING_CHAT_URL, entry["status_code"], entry["body"])] * times


def queue_script(*entries: dict) -> list[Step]:
    return [
        (method, GMI_QUEUE_URL, entry["status_code"], entry["body"]) for method, entry in entries
    ]


def music_script(fixture: dict) -> list[Step]:
    return queue_script(
        ("POST", fixture["music_submit"]),
        ("GET", fixture["music_poll_queued"]),
        ("GET", fixture["music_poll_running"]),
        ("GET", fixture["music_poll_completed"]),
    )


def speech_script(fixture: dict) -> list[Step]:
    return queue_script(
        ("POST", fixture["speech_submit"]),
        ("GET", fixture["speech_poll_queued"]),
        ("GET", fixture["speech_poll_completed"]),
    )


# ---------------------------------------------------------------------------
# acceptance criteria: exposed task methods
# ---------------------------------------------------------------------------


def test_gmi_adapter_exposes_task_methods():
    adapter = make_adapter(RecordedTransport([]))
    for name in (
        "m3_plan",
        "m3_critique",
        "music3_generate",
        "speech28_synthesize",
        "h3_generate",
    ):
        method = getattr(adapter, name, None)
        assert callable(method), f"GMIAdapter missing task method {name}"
        assert inspect.iscoroutinefunction(method)


# ---------------------------------------------------------------------------
# text models
# ---------------------------------------------------------------------------


async def test_m3_plan_returns_recorded_text(tmp_path):
    fixture = load_fixture()
    adapter = make_adapter(RecordedTransport(chat_script(fixture["m3_chat_completion"])), tmp_path)
    result = await adapter.m3_plan("plan a 60s focus track")
    expected = fixture["m3_chat_completion"]["body"]["choices"][0]["message"]["content"]
    assert result["text"] == expected


async def test_m3_critique_uses_critique_system_prompt(tmp_path):
    fixture = load_fixture()
    transport = RecordedTransport(chat_script(fixture["m3_chat_completion"]))
    adapter = make_adapter(transport, tmp_path)
    await adapter.m3_critique("the chorus drags")
    payload = transport.calls[0]["payload"]
    assert payload["messages"][0]["role"] == "system"
    assert "critic" in payload["messages"][0]["content"].lower()


async def test_m3_plan_honors_caller_system_prompt(tmp_path):
    fixture = load_fixture()
    transport = RecordedTransport(chat_script(fixture["m3_chat_completion"]))
    adapter = make_adapter(transport, tmp_path)
    custom = "Return the runtime plan shape."
    await adapter.m3_plan("build a plan", system=custom)
    payload = transport.calls[0]["payload"]
    assert payload["messages"][0] == {"role": "system", "content": custom}
    assert "system" not in payload


async def test_h3_generate_returns_recorded_text(tmp_path):
    fixture = load_fixture()
    adapter = make_adapter(RecordedTransport(chat_script(fixture["h3_chat_completion"])), tmp_path)
    result = await adapter.h3_generate("hello")
    expected = fixture["h3_chat_completion"]["body"]["choices"][0]["message"]["content"]
    assert result["text"] == expected


async def test_m3_plan_cache_hit_returns_instantly(tmp_path):
    fixture = load_fixture()
    transport = RecordedTransport(chat_script(fixture["m3_chat_completion"]))
    adapter = make_adapter(transport, tmp_path)
    first = await adapter.m3_plan("plan a 60s focus track")
    second = await adapter.m3_plan("plan a 60s focus track")
    assert first == second
    # The cache hit must not issue a second HTTP request.
    assert len(transport.calls) == 1


async def test_different_system_prompts_do_not_share_cache(tmp_path):
    fixture = load_fixture()
    transport = RecordedTransport(chat_script(fixture["m3_chat_completion"], times=2))
    adapter = make_adapter(transport, tmp_path)
    await adapter.m3_plan("same prompt")
    await adapter.m3_critique("same prompt")
    assert len(transport.calls) == 2


# ---------------------------------------------------------------------------
# audio models (async jobs)
# ---------------------------------------------------------------------------


async def test_music3_generate_polls_async_job(tmp_path):
    fixture = load_fixture()
    transport = RecordedTransport(music_script(fixture))
    adapter = make_adapter(transport, tmp_path)
    result = await adapter.music3_generate("indie folk, melancholic")
    expected = fixture["music_poll_completed"]["body"]["audio_url"]
    assert result["audio_url"] == expected
    assert [call["method"] for call in transport.calls] == ["POST", "GET", "GET", "GET"]
    # The poll hits the per-job queue URL.
    assert "rec-music-001" in transport.calls[-1]["url"]


async def test_music3_payload_uses_queue_audio_settings(tmp_path):
    fixture = load_fixture()
    transport = RecordedTransport(music_script(fixture))
    adapter = make_adapter(transport, tmp_path)
    await adapter.music3_generate("indie folk, melancholic", duration=60)
    payload = transport.calls[0]["payload"]["payload"]
    assert payload["format"] == "mp3"
    assert payload["sample_rate"] == 44100
    assert payload["bitrate"] == 256000
    assert "duration" not in payload
    assert UUID(transport.calls[0]["headers"]["Idempotency-Key"]).version == 4


async def test_music3_accepts_gmi_success_terminal_status(tmp_path):
    fixture = load_fixture()
    fixture["music_poll_completed"]["body"]["status"] = "success"
    transport = RecordedTransport(music_script(fixture))
    adapter = make_adapter(transport, tmp_path)
    result = await adapter.music3_generate("indie folk, melancholic")
    assert result["audio_url"] == fixture["music_poll_completed"]["body"]["audio_url"]


async def test_gmi_nested_outcome_audio_url_is_normalized(tmp_path):
    fixture = load_fixture()
    body = fixture["music_poll_completed"]["body"]
    audio_url = body.pop("audio_url")
    body["status"] = "success"
    body["outcome"] = {"audio_url": audio_url}
    transport = RecordedTransport(music_script(fixture))
    adapter = make_adapter(transport, tmp_path)
    result = await adapter.music3_generate("indie folk, melancholic")
    assert result["audio_url"] == audio_url


async def test_speech28_synthesize_extracts_media_url(tmp_path):
    fixture = load_fixture()
    transport = RecordedTransport(speech_script(fixture))
    adapter = make_adapter(transport, tmp_path)
    result = await adapter.speech28_synthesize("hello world")
    expected = fixture["speech_poll_completed"]["body"]["media_urls"][0]["url"]
    assert result["audio_url"] == expected


async def test_speech28_payload_uses_voice_id_and_audio_settings(tmp_path):
    fixture = load_fixture()
    transport = RecordedTransport(speech_script(fixture))
    adapter = make_adapter(transport, tmp_path)
    await adapter.speech28_synthesize("hello world", duration=5)
    payload = transport.calls[0]["payload"]["payload"]
    assert payload["voice_id"] == "English_expressive_narrator"
    assert payload["format"] == "mp3"
    assert payload["audio_sample_rate"] == "32000"
    assert payload["bitrate"] == "128000"
    assert payload["channel"] == "2"
    assert "duration" not in payload


async def test_music3_generate_cache_hit_skips_queue(tmp_path):
    fixture = load_fixture()
    transport = RecordedTransport(music_script(fixture))
    adapter = make_adapter(transport, tmp_path)
    first = await adapter.music3_generate("indie folk, melancholic")
    second = await adapter.music3_generate("indie folk, melancholic")
    assert first == second
    assert len(transport.calls) == 4  # only the first run's traffic


async def test_pending_job_is_resumed_not_resubmitted(tmp_path):
    fixture = load_fixture()
    cache = DiskStrategyCache(tmp_path / "cache")
    prompt = "indie folk, melancholic"
    key = cache_key(MUSIC_MODEL, prompt, {})
    cache.put(key, {"status": "pending", "provider": "gmi", "job_id": "rec-music-001"})
    # Only the completion poll is available — a resubmission would fail the
    # transport with "unexpected request".
    transport = RecordedTransport(
        [("GET", GMI_QUEUE_URL, 200, fixture["music_poll_completed"]["body"])]
    )
    adapter = make_adapter(transport, tmp_path)
    result = await adapter.music3_generate(prompt)
    assert result["audio_url"] == fixture["music_poll_completed"]["body"]["audio_url"]
    assert [call["method"] for call in transport.calls] == ["GET"]
    # The cache entry is upgraded to completed.
    assert cache.get(key)["status"] == "completed"


async def test_stale_pending_job_is_resubmitted_after_gone(tmp_path):
    """A resumed job that has vanished (404) must not poison the key forever."""
    fixture = load_fixture()
    cache = DiskStrategyCache(tmp_path / "cache")
    prompt = "indie folk, melancholic"
    key = cache_key(MUSIC_MODEL, prompt, {})
    cache.put(key, {"status": "pending", "provider": "gmi", "job_id": "dead-job"})
    transport = RecordedTransport(
        [("GET", GMI_QUEUE_URL, 404, {"error": "no such request"})] + music_script(fixture)
    )
    adapter = make_adapter(transport, tmp_path)
    result = await adapter.music3_generate(prompt)
    assert result["audio_url"] == fixture["music_poll_completed"]["body"]["audio_url"]
    # 404 poll of the dead job, then a fresh submit + full poll cycle.
    assert [call["method"] for call in transport.calls] == [
        "GET",
        "POST",
        "GET",
        "GET",
        "GET",
    ]
    assert cache.get(key)["status"] == "completed"


async def test_invalid_pending_job_id_is_ignored(tmp_path):
    fixture = load_fixture()
    cache = DiskStrategyCache(tmp_path / "cache")
    prompt = "indie folk, melancholic"
    key = cache_key(MUSIC_MODEL, prompt, {})
    cache.put(key, {"status": "pending", "provider": "gmi", "job_id": None})
    transport = RecordedTransport(music_script(fixture))
    adapter = make_adapter(transport, tmp_path)
    result = await adapter.music3_generate(prompt)
    assert result["audio_url"] == fixture["music_poll_completed"]["body"]["audio_url"]
    assert [call["method"] for call in transport.calls] == ["POST", "GET", "GET", "GET"]


async def test_hostile_pending_job_id_is_ignored(tmp_path):
    """A tampered cache id must not rewrite the poll URL path or query."""
    fixture = load_fixture()
    cache = DiskStrategyCache(tmp_path / "cache")
    prompt = "indie folk, melancholic"
    key = cache_key(MUSIC_MODEL, prompt, {})
    cache.put(
        key,
        {"status": "pending", "provider": "gmi", "job_id": "../../other/endpoint?x=1"},
    )
    transport = RecordedTransport(music_script(fixture))
    adapter = make_adapter(transport, tmp_path)
    result = await adapter.music3_generate(prompt)
    assert result["audio_url"] == fixture["music_poll_completed"]["body"]["audio_url"]
    # The hostile id was never polled: a fresh submit happened instead.
    assert [call["method"] for call in transport.calls] == ["POST", "GET", "GET", "GET"]
    assert all("other/endpoint" not in call["url"] for call in transport.calls)


async def test_resumed_job_failure_with_404_text_is_not_resubmitted(tmp_path):
    """A *failed* job whose error text mentions "HTTP 404" must fail, not resubmit.

    The stale-job recovery branches on the structural status code, never on
    the exception message.
    """
    cache = DiskStrategyCache(tmp_path / "cache")
    prompt = "indie folk, melancholic"
    key = cache_key(MUSIC_MODEL, prompt, {})
    cache.put(key, {"status": "pending", "provider": "gmi", "job_id": "rec-music-001"})
    transport = RecordedTransport(
        [("GET", GMI_QUEUE_URL, 200, {"status": "failed", "error": "upstream returned HTTP 404"})]
    )
    adapter = make_adapter(transport, tmp_path)
    with pytest.raises(AdapterError, match="job failed"):
        await adapter.music3_generate(prompt)
    assert [call["method"] for call in transport.calls] == ["GET"]


async def test_corrupt_completed_entry_without_result_is_a_miss(tmp_path):
    """A completed record missing ``result`` is corrupt: ignored, then rebuilt."""
    fixture = load_fixture()
    cache = DiskStrategyCache(tmp_path / "cache")
    prompt = "indie folk, melancholic"
    key = cache_key(MUSIC_MODEL, prompt, {})
    cache.put(key, {"status": "completed"})
    assert cache.get(key) is None  # shape-validated at the cache boundary
    transport = RecordedTransport(music_script(fixture))
    adapter = make_adapter(transport, tmp_path)
    result = await adapter.music3_generate(prompt)
    assert result["audio_url"] == fixture["music_poll_completed"]["body"]["audio_url"]
    assert len(transport.calls) == 4
    assert cache.get(key)["status"] == "completed"


# ---------------------------------------------------------------------------
# run(): retries with exponential backoff
# ---------------------------------------------------------------------------


async def test_run_retries_transient_errors_with_exponential_backoff(tmp_path, monkeypatch):
    fixture = load_fixture()
    transport = RecordedTransport(
        [("POST", GMI_SERVING_CHAT_URL, 500, {"error": "boom"})]
        + [("POST", GMI_SERVING_CHAT_URL, 503, {"error": "busy"})]
        + chat_script(fixture["m3_chat_completion"])
    )
    adapter = make_adapter(transport, tmp_path, backoff_base=0.01)

    delays: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay, *args, **kwargs):
        delays.append(delay)
        await real_sleep(0)

    monkeypatch.setattr("music_cli.cloud.base.asyncio.sleep", fake_sleep)

    result = await adapter.m3_plan("retry me")
    expected = fixture["m3_chat_completion"]["body"]["choices"][0]["message"]["content"]
    assert result["text"] == expected
    assert delays == [0.01, 0.02]  # exponential: base, base*2
    assert len(transport.calls) == 3


async def test_run_gives_up_after_three_attempts(tmp_path):
    transport = RecordedTransport(
        [("POST", GMI_SERVING_CHAT_URL, 500, {"error": "down"}) for _ in range(3)]
    )
    adapter = make_adapter(transport, tmp_path)
    with pytest.raises(AdapterError) as excinfo:
        await adapter.m3_plan("still down")
    assert "3 attempts" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, TransientError)
    assert len(transport.calls) == 3


async def test_run_does_not_retry_client_errors(tmp_path):
    transport = RecordedTransport([("POST", GMI_SERVING_CHAT_URL, 401, {"error": "bad key"})])
    adapter = make_adapter(transport, tmp_path)
    with pytest.raises(AdapterError, match="HTTP 401"):
        await adapter.m3_plan("nope")
    assert len(transport.calls) == 1


# ---------------------------------------------------------------------------
# cooperative cancellation and polling bounds
# ---------------------------------------------------------------------------


async def test_poll_cancellation_is_cooperative(tmp_path):
    adapter = make_adapter(RecordedTransport([]), tmp_path)
    cancelled = adapter.poll(
        f"{GMI_QUEUE_URL}/job-1",
        should_cancel=lambda: True,
    )
    with pytest.raises(PollCancelledError):
        await cancelled


async def test_task_cancellation_propagates_from_poll(tmp_path):
    """Genuine task cancellation must surface as CancelledError, not AdapterError."""
    transport = RecordedTransport(
        [("GET", GMI_QUEUE_URL, 200, {"status": "running"}) for _ in range(50)]
    )
    adapter = make_adapter(transport, tmp_path)
    task = asyncio.ensure_future(adapter.poll(f"{GMI_QUEUE_URL}/job-1"))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_cache_key_distinguishes_model_prompt_and_params():
    assert cache_key("m", "prompt") == cache_key("m", "prompt")
    assert cache_key("m", "prompt") != cache_key("m2", "prompt")
    assert cache_key("m", "prompt") != cache_key("m", "prompt2")
    assert cache_key("m", "prompt", {"a": 1}) != cache_key("m", "prompt", {"a": 2})
    assert cache_key("m", "prompt", {"a": 1}) == cache_key("m", "prompt", {"a": 1})


async def test_poll_times_out_when_job_never_completes(tmp_path):
    transport = RecordedTransport(
        [("GET", GMI_QUEUE_URL, 200, {"status": "running"}) for _ in range(50)]
    )
    adapter = make_adapter(transport, tmp_path, poll_timeout=0.01)
    with pytest.raises(AdapterError, match="did not finish"):
        await adapter.poll(f"{GMI_QUEUE_URL}/job-1")


async def test_poll_raises_on_failed_job(tmp_path):
    transport = RecordedTransport(
        [("GET", GMI_QUEUE_URL, 200, {"status": "failed", "error": "gpu"})]
    )
    adapter = make_adapter(transport, tmp_path)
    with pytest.raises(AdapterError, match="job failed: gpu"):
        await adapter.poll(f"{GMI_QUEUE_URL}/job-1")


# ---------------------------------------------------------------------------
# idempotency keys
# ---------------------------------------------------------------------------


async def test_idempotency_key_sent_and_deterministic():
    fixture = load_fixture()
    transport = RecordedTransport(chat_script(fixture["m3_chat_completion"], times=2))
    adapter = make_adapter(transport)  # no cache: both calls hit the transport
    await adapter.m3_plan("same request")
    await adapter.m3_plan("same request")
    key1 = transport.calls[0]["headers"]["Idempotency-Key"]
    key2 = transport.calls[1]["headers"]["Idempotency-Key"]
    assert key1 == key2
    # Different prompts must produce different keys.
    assert key1 != idempotency_key("gmi", "MiniMax-M3", "different request")


def test_speech_model_constants_are_exposed():
    assert MUSIC_MODEL == "minimax-music-3.0"
    assert SPEECH_MODEL == "minimax-tts-speech-2.8-hd"
