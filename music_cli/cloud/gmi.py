"""GMI Cloud adapter: MiniMax M3, Music 3.0, Speech 2.8, H3 (#133, task P1.2).

Endpoints mirror the ``mc cloud smoke`` harness (#152):

- text models (MiniMax M3, H3) are served OpenAI-compatible at
  ``GMI_SERVING_CHAT_URL`` — a single synchronous chat completion
- audio models (Music 3.0, Speech 2.8) run as async jobs on the GMI request
  queue at ``GMI_QUEUE_URL`` — submit, then poll until ``completed``/``success``

All task methods route through :meth:`BaseAdapter.run` (3 attempts,
exponential backoff, idempotency keys) and, when a
:class:`~music_cli.cloud.strategy_cache.DiskStrategyCache` is attached,
return instantly on a cache hit and resume journaled jobs after a restart.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from .base import BaseAdapter

# OpenAI-compatible serving endpoint for the MiniMax text models.
GMI_SERVING_CHAT_URL = "https://api.gmi-serving.com/v1/chat/completions"
# Inference-engine request queue for the audio models.
GMI_QUEUE_URL = "https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey/requests"

DEFAULT_M3_MODEL = "MiniMaxAI/MiniMax-M3"
DEFAULT_H3_MODEL = "MiniMax-H3"
MUSIC_MODEL = "minimax-music-3.0"
SPEECH_MODEL = "minimax-tts-speech-2.8-hd"
DEFAULT_SPEECH_VOICE = "English_expressive_narrator"

_PLAN_SYSTEM = "You are a music project planner. Output a concrete, ordered plan."
_CRITIQUE_SYSTEM = "You are a rigorous music critic. Critique the input concisely."


def _first_audio_url(outcome: dict[str, Any]) -> str | None:
    """Pull the first playable URL out of a queue-job outcome."""
    if outcome.get("audio_url"):
        return outcome["audio_url"]
    for entry in outcome.get("media_urls") or []:
        if isinstance(entry, dict) and entry.get("url"):
            return entry["url"]
    return None


def _audio_result(outcome: dict[str, Any]) -> dict[str, Any]:
    """Normalize a completed audio job into ``{"audio_url", "outcome"}``.

    The recorded queue fixture exposes audio fields at the top level, while
    the live GMI response nests them under ``outcome``.
    """
    media = outcome.get("outcome")
    if not isinstance(media, dict):
        media = outcome
    return {"audio_url": _first_audio_url(media), "outcome": outcome}


class GMIAdapter(BaseAdapter):
    """Async client for the free MiniMax models hosted on GMI Cloud."""

    provider = "gmi"
    base_url = GMI_SERVING_CHAT_URL
    queue_url = GMI_QUEUE_URL

    async def _send(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        # Both GMI endpoints use the BaseAdapter Bearer authorization header.
        # Keeping one scheme also matches the known-good cloud smoke request.
        # The queue accepts UUID-form idempotency keys only; BaseAdapter uses a
        # deterministic SHA-256 key, so canonicalize it without losing stable
        # retry/deduplication identity.
        if headers is not None and self.queue_url in url:
            headers = dict(headers)
            idem = headers.get("Idempotency-Key")
            if idem:
                try:
                    raw = bytes.fromhex(idem)
                    if len(raw) < 16:
                        raise ValueError
                except ValueError:
                    raw = hashlib.sha256(idem.encode("utf-8")).digest()
                # The queue validates the header as UUIDv4. UUID(...,
                # version=4) keeps the first 128 deterministic bits while
                # setting the version/variant bits required by the service.
                headers["Idempotency-Key"] = str(uuid.UUID(bytes=raw[:16], version=4))
        return await super()._send(method, url, payload, headers)

    # -- text models (synchronous chat completions) --------------------
    async def m3_plan(self, prompt: str, **params: Any) -> dict[str, Any]:
        """Ask MiniMax M3 for a structured project plan."""
        system = params.pop("system", _PLAN_SYSTEM)
        return await self.chat(
            model=DEFAULT_M3_MODEL,
            prompt=prompt,
            params=params,
            system=system,
        )

    async def m3_critique(self, prompt: str, **params: Any) -> dict[str, Any]:
        """Ask MiniMax M3 to critique the given material."""
        system = params.pop("system", _CRITIQUE_SYSTEM)
        return await self.chat(
            model=DEFAULT_M3_MODEL,
            prompt=prompt,
            params=params,
            system=system,
        )

    async def h3_generate(self, prompt: str, **params: Any) -> dict[str, Any]:
        """Generate a completion with the H3 model."""
        return await self.chat(model=DEFAULT_H3_MODEL, prompt=prompt, params=params)

    # -- audio models (async queue jobs) --------------------------------
    async def music3_generate(
        self,
        prompt: str,
        *,
        lyrics: str | None = None,
        **params: Any,
    ) -> dict[str, Any]:
        """Generate a song with MiniMax Music 3.0 (async job, returns audio URL)."""
        clean = {k: v for k, v in params.items() if v is not None}
        # The queue API derives the audio length from the prompt/lyrics. The
        # requested duration is enforced later by MixNode (pad/trim), and is
        # therefore kept for cache identity but not sent as a provider field.
        provider_params = {k: v for k, v in clean.items() if k != "duration"}

        def payload(idem: str) -> dict[str, Any]:
            body: dict[str, Any] = {
                "model": MUSIC_MODEL,
                "payload": {
                    "prompt": prompt,
                    "lyrics": lyrics or "[instrumental]",
                    "sample_rate": 44100,
                    "bitrate": 256000,
                    "format": "mp3",
                    **provider_params,
                },
            }
            return body

        return await self.submit_and_poll(
            model=MUSIC_MODEL,
            prompt=prompt,
            params={**clean, "lyrics": lyrics} if lyrics is not None else clean,
            submit_url=self.queue_url,
            submit_payload=payload,
            result_of=_audio_result,
            terminal_status=("completed", "success"),
        )

    async def speech28_synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        **params: Any,
    ) -> dict[str, Any]:
        """Synthesize speech with MiniMax Speech 2.8 (async job, returns audio URL)."""
        clean = {k: v for k, v in params.items() if v is not None}
        # Speech duration is determined by the text; MixNode positions and
        # trims the resulting narration. Keep duration in the cache key but
        # omit it from the provider payload.
        provider_params = {k: v for k, v in clean.items() if k != "duration"}
        voice_id = provider_params.pop("voice_id", None) or voice or DEFAULT_SPEECH_VOICE

        def payload(idem: str) -> dict[str, Any]:
            body: dict[str, Any] = {
                "model": SPEECH_MODEL,
                "payload": {
                    "text": text,
                    "voice_id": voice_id,
                    "format": "mp3",
                    "audio_sample_rate": "32000",
                    "bitrate": "128000",
                    "channel": "2",
                    **provider_params,
                },
            }
            return body

        return await self.submit_and_poll(
            model=SPEECH_MODEL,
            prompt=text,
            params={**clean, "voice": voice} if voice is not None else clean,
            submit_url=self.queue_url,
            submit_payload=payload,
            result_of=_audio_result,
            terminal_status=("completed", "success"),
        )
