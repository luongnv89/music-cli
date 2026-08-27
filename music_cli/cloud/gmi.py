"""GMI Cloud adapter: MiniMax M3, Music 3.0, Speech 2.8, H3 (#133, task P1.2).

Endpoints mirror the ``mc cloud smoke`` harness (#152):

- text models (MiniMax M3, H3) are served OpenAI-compatible at
  ``GMI_SERVING_CHAT_URL`` — a single synchronous chat completion
- audio models (Music 3.0, Speech 2.8) run as async jobs on the GMI request
  queue at ``GMI_QUEUE_URL`` — submit, then poll until ``completed``

All task methods route through :meth:`BaseAdapter.run` (3 attempts,
exponential backoff, idempotency keys) and, when a
:class:`~music_cli.cloud.strategy_cache.DiskStrategyCache` is attached,
return instantly on a cache hit and resume journaled jobs after a restart.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .base import BaseAdapter

# OpenAI-compatible serving endpoint for the MiniMax text models.
GMI_SERVING_CHAT_URL = "https://api.gmi-serving.com/v1/chat/completions"
# Inference-engine request queue for the audio models.
GMI_QUEUE_URL = "https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey/requests"

DEFAULT_M3_MODEL = "MiniMax-M3"
DEFAULT_H3_MODEL = "MiniMax-H3"
MUSIC_MODEL = "minimax-music-3.0"
SPEECH_MODEL = "minimax-tts-speech-2.8-hd"

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
    """Normalize a completed audio job into ``{"audio_url", "outcome"}``."""
    return {"audio_url": _first_audio_url(outcome), "outcome": outcome}


class GMIAdapter(BaseAdapter):
    """Async client for the free MiniMax models hosted on GMI Cloud."""

    provider = "gmi"
    base_url = GMI_SERVING_CHAT_URL
    queue_url = GMI_QUEUE_URL

    # -- text models (synchronous chat completions) --------------------
    async def m3_plan(self, prompt: str, **params: Any) -> dict[str, Any]:
        """Ask MiniMax M3 for a structured project plan."""
        return await self.chat(
            model=DEFAULT_M3_MODEL,
            prompt=prompt,
            params=params,
            system=_PLAN_SYSTEM,
        )

    async def m3_critique(self, prompt: str, **params: Any) -> dict[str, Any]:
        """Ask MiniMax M3 to critique the given material."""
        return await self.chat(
            model=DEFAULT_M3_MODEL,
            prompt=prompt,
            params=params,
            system=_CRITIQUE_SYSTEM,
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

        def payload(idem: str) -> dict[str, Any]:
            body: dict[str, Any] = {
                "model": MUSIC_MODEL,
                "prompt": prompt,
                "idempotency_key": idem,
                **clean,
            }
            if lyrics is not None:
                body["lyrics"] = lyrics
            return body

        return await self.submit_and_poll(
            model=MUSIC_MODEL,
            prompt=prompt,
            params={**clean, "lyrics": lyrics} if lyrics else clean,
            submit_url=self.queue_url,
            submit_payload=payload,
            result_of=_audio_result,
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

        def payload(idem: str) -> dict[str, Any]:
            body: dict[str, Any] = {
                "model": SPEECH_MODEL,
                "text": text,
                "idempotency_key": idem,
                **clean,
            }
            if voice is not None:
                body["voice"] = voice
            return body

        return await self.submit_and_poll(
            model=SPEECH_MODEL,
            prompt=text,
            params={**clean, "voice": voice} if voice else clean,
            submit_url=self.queue_url,
            submit_payload=payload,
            result_of=_audio_result,
        )


# Re-exported for callers wiring the adapter without touching internals.
AudioResultFactory = Callable[[dict[str, Any]], dict[str, Any]]
