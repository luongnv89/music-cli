"""MusicNode — MiniMax Music 3.0 audio node (issue #137, task P3.1).

Writes each generated song into the project's ``nodes/`` directory as
``song-<N>.wav``, probes it, and locks on success. The GMI adapter
(:meth:`~music_cli.cloud.gmi.GMIAdapter.music3_generate`) is duck-typed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import BaseNode


def _audio_url(result: dict[str, Any]) -> str:
    """Pull the playable audio URL out of the adapter's job outcome."""
    url = result.get("audio_url")
    if url:
        return url
    for entry in result.get("media_urls") or []:
        if isinstance(entry, dict) and entry.get("url"):
            return entry["url"]
    raise ValueError(f"music3_generate returned no audio URL: {result}")


class MusicNode(BaseNode):
    """Render a song with MiniMax Music 3.0.

    ``generate(prompt, *, lyrics=None, duration=None)`` calls the adapter's
    ``music3_generate``, downloads the returned audio into
    ``nodes/song-<N>.wav``, probes it, and locks the node on success.
    """

    FILENAME_STEM: str = "song"

    def __init__(self, adapter: Any, *, proj_dir: str | Path, **kwargs: Any) -> None:
        super().__init__(adapter, proj_dir=proj_dir, **kwargs)

    async def _synthesize(
        self,
        prompt: str,
        *,
        lyrics: str | None = None,
        duration: float | None = None,
        **params: Any,
    ) -> tuple[str, Path]:
        dest = self._next_path()
        call_params = dict(params)
        if duration is not None:
            call_params["duration"] = duration
        result = await self.adapter.music3_generate(prompt, lyrics=lyrics, **call_params)
        return _audio_url(result), dest
