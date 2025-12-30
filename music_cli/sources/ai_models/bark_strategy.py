"""Bark model strategy implementation."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from .model_strategy import ModelStrategy

logger = logging.getLogger(__name__)


class BarkStrategy(ModelStrategy):
    """Strategy for Suno's Bark models.

    Bark is a transformer-based text-to-audio model that can generate:
    - Realistic speech in multiple languages
    - Music and singing
    - Sound effects and ambient sounds

    Supported models:
    - suno/bark (~5GB, full model, best quality)
    - suno/bark-small (~2GB, faster, lower quality)

    Uses HuggingFace Transformers library for model loading and generation.

    Note: Bark outputs 24kHz audio and has a max token limit of 256,
    which limits generation to short clips (~10-15 seconds).
    """

    # Bark has a hard limit on tokens
    MAX_SEMANTIC_TOKENS = 256

    def load_model(self) -> tuple[Any, Any]:
        """Load Bark model and processor from HuggingFace.

        Returns:
            Tuple of (BarkModel, AutoProcessor).

        Raises:
            ImportError: If transformers is not installed.
            Exception: If model download or loading fails.
        """
        import torch
        from transformers import AutoProcessor, BarkModel

        logger.info(f"Loading Bark model ({self.model_id})...")

        # Load with float16 for memory efficiency if CUDA available
        torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        device = "cuda" if torch.cuda.is_available() else "cpu"

        processor = AutoProcessor.from_pretrained(self.model_id)
        model = BarkModel.from_pretrained(
            self.model_id,
            torch_dtype=torch_dtype,
        )
        model = model.to(device)

        # Enable CPU offload for memory efficiency if available
        if hasattr(model, "enable_cpu_offload") and device == "cuda":
            try:
                model.enable_cpu_offload()
                logger.info("Enabled CPU offload for Bark model")
            except Exception as e:
                logger.debug(f"Could not enable CPU offload: {e}")

        return model, processor

    def generate_audio(
        self,
        prompt: str,
        duration: int,
    ) -> tuple[np.ndarray, int]:
        """Generate audio from a text prompt using Bark.

        Args:
            prompt: Text description or speech to generate.
            duration: Duration in seconds (note: Bark has limited max duration).

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

        # Get voice preset from extra_params if specified
        voice_preset = self.config.extra_params.get("voice_preset", None)

        logger.info(f"Generating audio with {self.config.id}...")

        # Process the text prompt
        if voice_preset:
            inputs = processor(prompt, voice_preset=voice_preset, return_tensors="pt")
        else:
            inputs = processor(prompt, return_tensors="pt")

        # Move inputs to same device as model
        device = next(model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        # Generate audio
        with torch.no_grad():
            audio_values = model.generate(**inputs)

        # Extract audio array
        # Bark outputs shape: [batch, samples]
        audio = audio_values[0].cpu().numpy()

        # Get sample rate from model config
        sample_rate = model.generation_config.sample_rate

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
