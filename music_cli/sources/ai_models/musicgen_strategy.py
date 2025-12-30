"""MusicGen model strategy implementation."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from .model_strategy import ModelStrategy

logger = logging.getLogger(__name__)


class MusicGenStrategy(ModelStrategy):
    """Strategy for Meta's MusicGen models (facebook/musicgen-*).

    Supports all MusicGen variants:
    - musicgen-small (~1.5GB)
    - musicgen-medium (~3.3GB)
    - musicgen-large (~6.5GB)
    - musicgen-melody (~3.3GB, supports melody conditioning)

    Uses HuggingFace Transformers library for model loading and generation.
    """

    def load_model(self) -> tuple[Any, Any]:
        """Load MusicGen model and processor from HuggingFace.

        Returns:
            Tuple of (MusicgenForConditionalGeneration, AutoProcessor).

        Raises:
            ImportError: If transformers is not installed.
            Exception: If model download or loading fails.
        """
        from transformers import AutoProcessor, MusicgenForConditionalGeneration

        logger.info(f"Loading MusicGen model ({self.model_id})...")

        processor = AutoProcessor.from_pretrained(self.model_id)  # nosec B615
        model = MusicgenForConditionalGeneration.from_pretrained(self.model_id)  # nosec B615

        return model, processor

    def generate_audio(
        self,
        prompt: str,
        duration: int,
    ) -> tuple[np.ndarray, int]:
        """Generate audio from a text prompt using MusicGen.

        Args:
            prompt: Text description of the music to generate.
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

        import torch

        model = self._model
        processor = self._processor

        # Calculate tokens based on duration
        max_new_tokens = self.get_max_tokens(duration)

        logger.info(f"Generating {duration}s of audio with {self.model_id}...")

        # Process the prompt
        inputs = processor(
            text=[prompt],
            padding=True,
            return_tensors="pt",
        )

        # Generate audio
        with torch.no_grad():
            audio_values = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=True,
            )

        # Extract audio array and sample rate
        # MusicGen outputs shape: [batch, channels, samples]
        sample_rate = model.config.audio_encoder.sampling_rate
        audio = audio_values[0, 0].cpu().numpy()

        # Clip audio to [-1, 1] range to prevent distortion, then normalize to int16
        audio_clipped = np.clip(audio, -1.0, 1.0)
        audio_int16 = (audio_clipped * 32767).astype(np.int16)

        logger.info(f"Generated {len(audio_int16) / sample_rate:.1f}s of audio")

        return audio_int16, sample_rate

    def generate_with_melody(
        self,
        prompt: str,
        melody_audio: np.ndarray,
        melody_sample_rate: int,
        duration: int,
    ) -> tuple[np.ndarray, int]:
        """Generate audio conditioned on a melody (musicgen-melody only).

        This method is only supported by the musicgen-melody model variant.

        Args:
            prompt: Text description of the music style/genre.
            melody_audio: Numpy array of melody audio samples.
            melody_sample_rate: Sample rate of the melody audio.
            duration: Duration in seconds.

        Returns:
            Tuple of (audio_array, sample_rate).

        Raises:
            RuntimeError: If model is not loaded.
            ValueError: If model does not support melody conditioning.
            Exception: If generation fails.
        """
        if not self.is_loaded:
            raise RuntimeError(f"Model {self.model_id} is not loaded")

        if "melody" not in self.model_id.lower():
            raise ValueError(
                f"Model {self.model_id} does not support melody conditioning. "
                "Use musicgen-melody instead."
            )

        import torch

        model = self._model
        processor = self._processor

        max_new_tokens = self.get_max_tokens(duration)

        logger.info(f"Generating {duration}s with melody conditioning...")

        # Process with melody
        inputs = processor(
            text=[prompt],
            audio=melody_audio,
            sampling_rate=melody_sample_rate,
            padding=True,
            return_tensors="pt",
        )

        with torch.no_grad():
            audio_values = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=True,
            )

        sample_rate = model.config.audio_encoder.sampling_rate
        audio = audio_values[0, 0].cpu().numpy()
        audio_clipped = np.clip(audio, -1.0, 1.0)
        audio_int16 = (audio_clipped * 32767).astype(np.int16)

        return audio_int16, sample_rate
