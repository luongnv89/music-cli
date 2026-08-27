"""OpenRouter adapter: MiniMax M3, M2.7, Speech 2.8 (#133, task P1.2).

OpenRouter serves every model through one OpenAI-compatible
chat-completions endpoint, so all three task methods are single round
trips (no queue polling). All of them route through
:meth:`BaseAdapter.run` (3 attempts, exponential backoff, idempotency
keys) and, when a
:class:`~music_cli.cloud.strategy_cache.DiskStrategyCache` is attached,
return instantly on a cache hit.
"""

from __future__ import annotations

from typing import Any

from .base import BaseAdapter

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

M3_MODEL = "minimax/minimax-m3"
M27_MODEL = "minimax/minimax-m2.7"
SPEECH_MODEL = "minimax/speech-2.8"


class OpenRouterAdapter(BaseAdapter):
    """Async client for the MiniMax models resold through OpenRouter."""

    provider = "openrouter"
    base_url = OPENROUTER_CHAT_URL

    async def m3_chat(self, prompt: str, **params: Any) -> dict[str, Any]:
        """Chat completion with MiniMax M3 via OpenRouter."""
        return await self.chat(model=M3_MODEL, prompt=prompt, params=params)

    async def m27_chat(self, prompt: str, **params: Any) -> dict[str, Any]:
        """Chat completion with MiniMax M2.7 via OpenRouter."""
        return await self.chat(model=M27_MODEL, prompt=prompt, params=params)

    async def speech28_synthesize(self, text: str, **params: Any) -> dict[str, Any]:
        """Synthesize speech with Speech 2.8 via OpenRouter.

        OpenRouter is text-in/text-out: the model returns a completion whose
        text carries the synthesized-audio reference, so the result is the
        standard ``{"text": ...}`` payload rather than a queue outcome.
        """
        return await self.chat(model=SPEECH_MODEL, prompt=text, params=params)
