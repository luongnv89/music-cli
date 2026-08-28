"""SpeechNode — MiniMax Speech 2.8 audio node (issue #137, task P3.1).

Writes each generated narration into the project's ``nodes/`` directory as
``narration-<N>.wav``, probes it, and locks on success. The GMI adapter
(:meth:`~music_cli.cloud.gmi.GMIAdapter.speech28_synthesize`) is duck-typed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import BaseNode
from .music import _audio_url

#: Destination filename stem for generated narrations.
NARRATION_STEM = "narration"


class SpeechNode(BaseNode):
    """Synthesize a narration with MiniMax Speech 2.8.

    ``generate(text, *, voice=None, duration=None)`` calls the adapter's
    ``speech28_synthesize``, downloads the returned audio into
    ``nodes/narration-<N>.wav``, probes it, and locks the node on success.
    """

    FILENAME_STEM: str = "narration"

    def __init__(self, adapter: Any, *, proj_dir: str | Path, **kwargs: Any) -> None:
        super().__init__(adapter, proj_dir=proj_dir, **kwargs)

    async def _synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        duration: float | None = None,
        **params: Any,
    ) -> tuple[str, Path]:
        dest = self._next_path()
        call_params = dict(params)
        if duration is not None:
            call_params["duration"] = duration
        result = await self.adapter.speech28_synthesize(text, voice=voice, **call_params)
        return _audio_url(result), dest
