"""MiniMax Music 3 strategy using the official Diffusers modular pipeline."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .model_strategy import ModelStrategy

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)


class MiniMaxMusic3Strategy(ModelStrategy):
    """Generate lyrics-conditioned songs with MiniMaxAI/MiniMax-Music3.

    MiniMax Music 3 is distributed as a Diffusers modular pipeline rather than
    a Transformers text-to-audio model. Optional runtime imports stay inside
    ``load_model`` so the other AI strategies do not require this integration.
    """

    def load_model(self) -> tuple[Any, Any]:
        """Load the official MiniMax modular pipeline on CUDA."""
        try:
            import torch
        except ImportError as exc:
            raise ImportError(
                "MiniMax Music 3 requires torch; install the 'minimax' extra"
            ) from exc

        try:
            from diffusers import ModularPipeline
        except ImportError as exc:
            raise ImportError(
                "MiniMax Music 3 requires Diffusers ModularPipeline; install the 'minimax' extra"
            ) from exc

        if not callable(getattr(ModularPipeline, "from_pretrained", None)):
            raise RuntimeError(
                "Installed Diffusers does not provide ModularPipeline.from_pretrained; "
                "install the pinned MiniMax-compatible Diffusers revision"
            )
        if not callable(getattr(torch.cuda, "is_available", None)) or not torch.cuda.is_available():
            raise RuntimeError(
                "MiniMax Music 3 inference requires a CUDA-capable GPU; "
                "CPU inference is not supported"
            )
        if not hasattr(torch, "bfloat16"):
            raise RuntimeError("MiniMax Music 3 requires a PyTorch build with bfloat16 support")

        logger.info("Loading MiniMax Music 3 model (%s)...", self.model_id)
        pipeline = ModularPipeline.from_pretrained(self.model_id, revision=self.config.revision)
        if not callable(getattr(pipeline, "load_components", None)):
            raise RuntimeError(
                "Installed MiniMax pipeline is missing load_components; "
                "install the pinned MiniMax-compatible Diffusers revision"
            )
        if not callable(getattr(pipeline, "to", None)):
            raise RuntimeError("Installed MiniMax pipeline cannot be moved to CUDA")

        pipeline.load_components(dtype=torch.bfloat16)
        pipeline.to("cuda")
        return pipeline, None

    def generate_audio(
        self,
        prompt: str,
        duration: int,
        lyrics: str | None = None,
    ) -> tuple[np.ndarray, int]:
        """Generate a 32 kHz stereo WAV-compatible song.

        The official pipeline accepts the music description as ``prompt`` and
        lyrics separately, returning audio in its ``audios`` output list.
        """
        import numpy as np

        if not self.is_loaded:
            raise RuntimeError(f"Model {self.model_id} is not loaded")
        if not lyrics or not lyrics.strip():
            raise ValueError("MiniMax Music 3 requires non-empty lyrics")

        pipeline = self._model
        try:
            output = pipeline(
                prompt=prompt,
                lyrics=lyrics,
                audio_duration=float(duration),
                output="audios",
            )
            audio = output.audios[0] if hasattr(output, "audios") else output[0]
        except (IndexError, KeyError, TypeError, AttributeError) as exc:
            raise RuntimeError("MiniMax Music 3 returned no usable audio") from exc

        if hasattr(audio, "detach"):
            audio = audio.detach().float().cpu().numpy()
        else:
            audio = np.asarray(audio)

        if audio.ndim == 3:
            audio = audio[0]
        if audio.ndim == 2 and audio.shape[0] <= 8 and audio.shape[1] > audio.shape[0]:
            audio = audio.T
        if audio.ndim not in (1, 2):
            raise RuntimeError(f"Unexpected MiniMax audio shape: {audio.shape}")

        if np.issubdtype(audio.dtype, np.integer):
            audio_int16 = np.clip(audio, -32768, 32767).astype(np.int16)
        else:
            audio_int16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)

        sample_rate = int(getattr(pipeline, "sampling_rate", 32000))
        return audio_int16, sample_rate
