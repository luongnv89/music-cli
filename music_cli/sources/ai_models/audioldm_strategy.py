"""AudioLDM model strategy implementation."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from .model_strategy import ModelStrategy

logger = logging.getLogger(__name__)


class AudioLDMStrategy(ModelStrategy):
    """Strategy for CVSSP's AudioLDM models.

    AudioLDM is a latent diffusion model for text-to-audio generation.
    It generates general audio including music, sound effects, and speech.

    Supported models:
    - cvssp/audioldm-s-full-v2 (~1GB, recommended)
    - cvssp/audioldm-m-full (~2GB)
    - cvssp/audioldm-l-full (~3GB, best quality)

    Uses HuggingFace Diffusers library for model loading and generation.

    Note: AudioLDM outputs 16kHz audio, which is lower than MusicGen's 32kHz.
    """

    # AudioLDM uses diffusion steps instead of tokens
    # Default 10 steps is fast, 50+ steps for better quality
    DEFAULT_INFERENCE_STEPS = 10

    def load_model(self) -> tuple[Any, Any]:
        """Load AudioLDM pipeline from HuggingFace.

        Returns:
            Tuple of (AudioLDMPipeline, None). AudioLDM uses a pipeline
            architecture so there's no separate processor.

        Raises:
            ImportError: If diffusers is not installed.
            Exception: If model download or loading fails.
        """
        import torch
        from diffusers import AudioLDMPipeline

        logger.info(f"Loading AudioLDM model ({self.model_id})...")

        # Load with float16 for memory efficiency if CUDA available
        torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        device = "cuda" if torch.cuda.is_available() else "cpu"

        pipeline = AudioLDMPipeline.from_pretrained(
            self.model_id,
            torch_dtype=torch_dtype,
        )
        pipeline = pipeline.to(device)

        # AudioLDM doesn't have a separate processor
        return pipeline, None

    def generate_audio(
        self,
        prompt: str,
        duration: int,
    ) -> tuple[np.ndarray, int]:
        """Generate audio from a text prompt using AudioLDM.

        Args:
            prompt: Text description of the audio to generate.
            duration: Duration in seconds.

        Returns:
            Tuple of (audio_array, sample_rate) where audio_array is a
            numpy array of int16 values normalized for WAV output.

        Raises:
            RuntimeError: If model is not loaded.
            Exception: If generation fails.
        """
        if not self.is_loaded:
            raise RuntimeError(f"Model {self.model_id} is not loaded")

        pipeline = self._model

        # Get inference steps from extra_params or use default
        num_inference_steps = self.config.extra_params.get(
            "num_inference_steps", self.DEFAULT_INFERENCE_STEPS
        )

        # Get guidance scale from extra_params or use default
        guidance_scale = self.config.extra_params.get("guidance_scale", 2.5)

        logger.info(
            f"Generating {duration}s of audio with {self.config.id} "
            f"({num_inference_steps} steps)..."
        )

        # Generate audio
        # AudioLDM uses audio_length_in_s instead of tokens
        output = pipeline(
            prompt,
            num_inference_steps=num_inference_steps,
            audio_length_in_s=float(duration),
            guidance_scale=guidance_scale,
        )

        # Extract audio array
        # AudioLDM outputs numpy array directly
        audio = output.audios[0]

        # AudioLDM outputs 16kHz audio
        sample_rate = 16000

        # Clip audio to [-1, 1] range and normalize to int16
        audio_clipped = np.clip(audio, -1.0, 1.0)
        audio_int16 = (audio_clipped * 32767).astype(np.int16)

        logger.info(f"Generated {len(audio_int16) / sample_rate:.1f}s of audio")

        return audio_int16, sample_rate

    def unload(self) -> None:
        """Unload the model and free GPU memory."""
        if self._model is not None:
            # Move to CPU first to free GPU memory
            try:
                self._model.to("cpu")
            except Exception as e:
                logger.debug(f"Could not move model to CPU: {e}")

        self._model = None
        self._processor = None

        # Force GPU memory cleanup
        try:
            import gc

            import torch

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

        logger.info(f"Model {self.model_id} unloaded")
