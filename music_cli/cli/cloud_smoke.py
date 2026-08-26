"""One-call smoke tests for the free MiniMax models served by GMI Cloud (#152).

Fires a single real API call at each free model (M3 text reasoning, Music 3.0
song generation, Speech 2.8 TTS), captures latency/size/format, and writes the
outputs plus a ``summary.json`` record under an output directory (default
``dist/_smoke``). Requires a GMI Cloud API key stored via
``mc cloud key set gmi`` and the ``gmi`` extra installed.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import click

# OpenAI-compatible serving endpoint for MiniMax M3 (text reasoning).
GMI_SERVING_CHAT_URL = "https://api.gmi-serving.com/v1/chat/completions"
# Inference-engine request queue for the audio models (Music 3.0, Speech 2.8).
GMI_QUEUE_URL = "https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey/requests"

DEFAULT_M3_MODEL = "MiniMax-M3"
MUSIC_MODEL = "minimax-music-3.0"
SPEECH_MODEL = "minimax-tts-speech-2.8-hd"

DEFAULT_POLL_TIMEOUT = 300.0
DEFAULT_POLL_INTERVAL = 5.0

MUSIC_LYRICS = (
    "[verse]\nSmoke curls through the neon rain\nA quiet bar, a window seat\n\n"
    "[chorus]\nHold the night a little longer\nLet the small hours hum"
)
MUSIC_PROMPT = "Indie folk, melancholic, warm acoustic guitar, slow tempo"
SPEECH_TEXT = "coder-music-cli smoke test: MiniMax Speech 2.8 via GMI Cloud."


def _load_httpx():
    try:
        import httpx
    except ImportError as exc:
        raise click.ClickException(
            "The 'httpx' package is not installed.\n"
            "Install it with: pip install 'coder-music-cli[gmi]'"
        ) from exc
    return httpx


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _result(check, model, status="ok", **extra) -> dict:
    record = {
        "check": check,
        "model": model,
        "status": status,
        "timestamp": _utc_now_iso(),
        "latency_s": None,
        "size_bytes": None,
        "format": None,
        "output_path": None,
        "error": None,
    }
    record.update(extra)
    return record


def _first_audio_url(outcome: dict) -> str | None:
    if outcome.get("audio_url"):
        return outcome["audio_url"]
    media_urls = outcome.get("media_urls") or []
    for entry in media_urls:
        if entry.get("url"):
            return entry["url"]
    return None


def run_m3(client, api_key: str, model: str = DEFAULT_M3_MODEL, timeout: float = 30.0) -> dict:
    """One real chat-completions call against MiniMax M3."""
    started = time.monotonic()
    try:
        response = client.post(
            GMI_SERVING_CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with exactly: smoke ok"}],
                "max_tokens": 32,
            },
            timeout=timeout,
        )
        latency = time.monotonic() - started
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        return _result(
            "m3",
            model,
            status="error",
            latency_s=round(time.monotonic() - started, 3),
            error=str(exc),
        )
    return _result(
        "m3", model, latency_s=round(latency, 3), format="text", size_bytes=len(text), text=text
    )


def run_queue_model(
    client,
    api_key: str,
    *,
    check: str,
    model: str,
    payload: dict,
    output_path: Path,
    poll_timeout: float = DEFAULT_POLL_TIMEOUT,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
) -> dict:
    """Submit one request-queue job (music/TTS), poll it, download the audio."""
    headers = {"Authorization": f"Bearer {api_key}"}
    started = time.monotonic()
    try:
        response = client.post(
            GMI_QUEUE_URL,
            headers=headers,
            json={"model": model, "payload": payload},
            timeout=poll_timeout,
        )
        response.raise_for_status()
        request_id = response.json()["request_id"]

        deadline = time.monotonic() + poll_timeout
        while True:
            poll = client.get(f"{GMI_QUEUE_URL}/{request_id}", headers=headers, timeout=30.0)
            poll.raise_for_status()
            body = poll.json()
            state = body.get("status")
            if state == "success":
                break
            if state == "failed":
                raise RuntimeError(
                    f"request {request_id} failed: {body.get('outcome', {}).get('status')}"
                )
            if time.monotonic() > deadline:
                raise TimeoutError(f"request {request_id} not done after {poll_timeout}s")
            time.sleep(poll_interval)

        audio_url = _first_audio_url(body.get("outcome") or {})
        if not audio_url:
            raise RuntimeError(f"request {request_id} succeeded without an audio URL")
        audio_response = client.get(audio_url, timeout=poll_timeout)
        audio_response.raise_for_status()
        content = audio_response.content
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(content)
    except Exception as exc:
        return _result(
            check,
            model,
            status="error",
            latency_s=round(time.monotonic() - started, 3),
            error=str(exc),
        )
    return _result(
        check,
        model,
        latency_s=round(time.monotonic() - started, 3),
        format=payload.get("format", "mp3"),
        size_bytes=len(content),
        output_path=str(output_path),
    )


def run_all_checks(
    client_factory,
    api_key: str,
    output_dir: Path,
    m3_model: str = DEFAULT_M3_MODEL,
    skips: tuple[str, ...] = (),
    poll_timeout: float = DEFAULT_POLL_TIMEOUT,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
) -> list[dict]:
    """Run each enabled smoke check with its own client; never raises."""
    results: list[dict] = []
    plans = [
        ("m3", run_m3),
        ("music", run_music_plan),
        ("speech", run_speech_plan),
    ]
    plan_kwargs = {
        "m3": {"model": m3_model},
        "music": {
            "output_path": output_dir / "music.mp3",
            "poll_timeout": poll_timeout,
            "poll_interval": poll_interval,
        },
        "speech": {
            "output_path": output_dir / "speech.mp3",
            "poll_timeout": poll_timeout,
            "poll_interval": poll_interval,
        },
    }
    for name, runner in plans:
        if name in skips:
            results.append(_result(name, "-", status="skipped"))
            continue
        client = client_factory()
        try:
            result = runner(client, api_key, **plan_kwargs[name])
        finally:
            close = getattr(client, "close", None)
            if close is not None:
                close()
        results.append(result)
    return results


def run_music_plan(client, api_key, output_path, poll_timeout, poll_interval) -> dict:
    return run_queue_model(
        client,
        api_key,
        check="music",
        model=MUSIC_MODEL,
        payload={
            "lyrics": MUSIC_LYRICS,
            "prompt": MUSIC_PROMPT,
            "sample_rate": 44100,
            "bitrate": 256000,
            "format": "mp3",
        },
        output_path=output_path,
        poll_timeout=poll_timeout,
        poll_interval=poll_interval,
    )


def run_speech_plan(client, api_key, output_path, poll_timeout, poll_interval) -> dict:
    return run_queue_model(
        client,
        api_key,
        check="speech",
        model=SPEECH_MODEL,
        payload={
            "text": SPEECH_TEXT,
            "voice_id": "English_expressive_narrator",
            "format": "mp3",
            "audio_sample_rate": "32000",
            "bitrate": "128000",
            "channel": "2",
        },
        output_path=output_path,
        poll_timeout=poll_timeout,
        poll_interval=poll_interval,
    )


def write_summary(output_dir: Path, results: list[dict]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps({"results": results}, indent=2) + "\n", encoding="utf-8")
    return summary_path


def register_cloud_smoke(cloud_group):
    @cloud_group.command("smoke")
    @click.option(
        "--output-dir",
        type=click.Path(path_type=Path),
        default=Path("dist/_smoke"),
        show_default=True,
        help="Where outputs and summary.json are written.",
    )
    @click.option("--poll-timeout", type=float, default=DEFAULT_POLL_TIMEOUT, show_default=True)
    @click.option("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL, show_default=True)
    @click.option("--m3-model", default=DEFAULT_M3_MODEL, show_default=True)
    @click.option(
        "--skip",
        "skips",
        multiple=True,
        type=click.Choice(["m3", "music", "speech"]),
        help="Skip a check (repeatable).",
    )
    def cloud_smoke(output_dir, poll_timeout, poll_interval, m3_model, skips):
        """Fire one real API call at each free MiniMax model on GMI Cloud (#152).

        Writes m3_response.txt / music.mp3 / speech.mp3 plus summary.json under
        --output-dir and prints timestamp/latency/size/format per check.
        """
        from .cloud import KEYRING_SERVICE, _load_keyring

        api_key = _load_keyring().get_password(KEYRING_SERVICE, "gmi")
        if not api_key:
            raise click.ClickException(
                "No GMI Cloud API key stored.\nSet one with: mc cloud key set gmi"
            )

        httpx = _load_httpx()

        def client_factory():
            return httpx.Client(timeout=poll_timeout)

        results = run_all_checks(
            client_factory,
            api_key,
            output_dir=output_dir,
            m3_model=m3_model,
            skips=tuple(skips),
            poll_timeout=poll_timeout,
            poll_interval=poll_interval,
        )

        # Persist the M3 text response so three files land in dist/_smoke.
        for result in results:
            if result["check"] == "m3" and result["status"] == "ok":
                m3_path = output_dir / "m3_response.txt"
                m3_path.parent.mkdir(parents=True, exist_ok=True)
                m3_path.write_text(result.pop("text") or "(empty)", encoding="utf-8")
                result["output_path"] = str(m3_path)

        summary_path = write_summary(output_dir, results)

        failed = False
        for result in results:
            line = (
                f"{result['check']:>6}: {result['status']}"
                + (f" in {result['latency_s']}s" if result.get("latency_s") is not None else "")
                + (
                    f", {result['size_bytes']} bytes"
                    if result.get("size_bytes") is not None
                    else ""
                )
                + (f" [{result['format']}]" if result.get("format") else "")
            )
            click.echo(line)
            if result["status"] == "error":
                click.echo(f"        error: {result['error']}", err=True)
                failed = True

        click.echo(f"summary: {summary_path}")
        if failed:
            raise SystemExit(1)
