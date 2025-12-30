"""AI music generation using HuggingFace Transformers models (optional feature).

This module provides a unified interface for generating music using various
HuggingFace text-to-audio models through the strategy pattern. Model selection
is configuration-driven, allowing users to choose from multiple models like
MusicGen variants or add custom models.
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..player.base import TrackInfo

if TYPE_CHECKING:
    from .ai_models import ModelStrategy

logger = logging.getLogger(__name__)

# Looping instruction appended to all AI prompts for seamless playback
LOOP_INSTRUCTION = (
    "seamlessly looping, smooth transitions, perfect for continuous playback, no abrupt endings"
)

# Flag to track if AI dependencies are available
_AI_AVAILABLE: bool | None = None


def is_ai_available() -> bool:
    """Check if AI music generation dependencies are available."""
    global _AI_AVAILABLE

    if _AI_AVAILABLE is not None:
        return _AI_AVAILABLE

    try:
        import scipy  # noqa: F401
        import torch  # noqa: F401
        from transformers import AutoProcessor, MusicgenForConditionalGeneration  # noqa: F401

        _AI_AVAILABLE = True
        logger.info("AI music generation is available (using HuggingFace Transformers)")
    except ImportError as e:
        _AI_AVAILABLE = False
        logger.info(f"AI music generation not available: {e}")

    return _AI_AVAILABLE


def _get_strategy_cache():
    """Get the LRU strategy cache with configured max size.

    Returns:
        LRUStrategyCache instance.
    """
    from ..config import get_config
    from .ai_models import get_strategy_cache

    config = get_config()
    max_models = config.get_ai_cache_max_models()
    cache = get_strategy_cache(max_size=max_models)

    # Update max size if config changed
    if cache.max_size != max_models:
        cache.max_size = max_models

    return cache


def _get_strategy(model_id: str) -> ModelStrategy | None:
    """Get or create a strategy for the specified model.

    Uses an LRU cache to manage model memory. When the cache is full,
    the least recently used model is evicted and its memory is freed.

    Args:
        model_id: The model ID (e.g., 'musicgen-small').

    Returns:
        Loaded ModelStrategy instance or None if loading fails.
    """
    cache = _get_strategy_cache()

    # Return cached strategy if available and loaded
    cached = cache.get(model_id)
    if cached is not None and cached.is_loaded:
        return cached

    # Create new strategy
    try:
        from ..config import get_config
        from .ai_models import ModelRegistry

        config = get_config()
        models_config = config.get_ai_models_config()
        model_config = models_config.get_model(model_id)

        if model_config is None:
            logger.error(f"Model '{model_id}' not found in configuration")
            return None

        strategy = ModelRegistry.create_strategy(model_config)

        if not strategy.ensure_loaded():
            logger.error(f"Failed to load model '{model_id}'")
            return None

        # Add to LRU cache (may evict oldest model if at capacity)
        cache.put(model_id, strategy)
        return strategy

    except ValueError as e:
        logger.error(f"Failed to create strategy for model '{model_id}': {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error loading model '{model_id}': {e}")
        return None


def clear_strategy_cache() -> None:
    """Clear the strategy cache and unload all models."""
    from .ai_models import clear_global_cache

    clear_global_cache()
    logger.info("Strategy cache cleared")


class AIGenerator:
    """Generates music using HuggingFace text-to-audio models.

    This class provides a high-level interface for generating music from text
    prompts using configurable HuggingFace models. It handles model selection,
    prompt enhancement, and file output.

    Attributes:
        output_dir: Directory where generated audio files are saved.
    """

    def __init__(
        self,
        output_dir: Path | None = None,
        config: Any | None = None,
    ):
        """Initialize AI generator.

        Args:
            output_dir: Directory to save generated audio files.
                       Defaults to a temp directory.
            config: Config instance for model settings (optional).
        """
        if output_dir is None:
            output_dir = Path(tempfile.gettempdir()) / "music-cli-ai"
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Store config reference
        if config is None:
            from ..config import get_config

            config = get_config()
        self._config = config

    @property
    def available(self) -> bool:
        """Check if AI generation is available."""
        return is_ai_available()

    def get_default_model(self) -> str:
        """Get the default model ID from configuration."""
        return self._config.get_default_ai_model()

    def list_models(self, enabled_only: bool = True) -> list[str]:
        """Get list of available model IDs.

        Args:
            enabled_only: If True, only return enabled models.

        Returns:
            List of model IDs.
        """
        return self._config.list_ai_models(enabled_only=enabled_only)

    def generate(
        self,
        prompt: str,
        duration: int = 30,
        filename: str | None = None,
        add_looping: bool = True,
        model_id: str | None = None,
    ) -> TrackInfo | None:
        """Generate music from a text prompt.

        Args:
            prompt: Text description of the music to generate.
            duration: Duration in seconds.
            filename: Optional output filename.
            add_looping: If True, append looping instructions to prompt.
            model_id: Model to use (e.g., 'musicgen-small').
                     If None, uses the configured default.

        Returns:
            TrackInfo for the generated audio, or None if generation failed.
        """
        if not is_ai_available():
            logger.warning("AI dependencies not available")
            return None

        # Use default model if not specified
        if model_id is None:
            model_id = self.get_default_model()

        # Get or create strategy for this model
        strategy = _get_strategy(model_id)
        if strategy is None:
            logger.error(f"Failed to get strategy for model '{model_id}'")
            return None

        try:
            import scipy.io.wavfile

            # Clamp duration to model's allowed range
            model_config = strategy.config
            duration = model_config.clamp_duration(duration)

            # Enhance prompt with looping instructions for seamless playback
            enhanced_prompt = prompt
            if add_looping:
                enhanced_prompt = f"{prompt}, {LOOP_INSTRUCTION}"

            logger.info(f"Generating {duration}s with {model_id}: {enhanced_prompt[:50]}...")

            # Generate audio using strategy
            audio, sample_rate = strategy.generate_audio(enhanced_prompt, duration)

            # Generate filename if not provided
            if filename is None:
                hash_input = f"{prompt}{time.time()}"
                short_hash = hashlib.md5(  # noqa: S324
                    hash_input.encode(), usedforsecurity=False
                ).hexdigest()[:8]
                filename = f"ai_music_{short_hash}.wav"

            # Save to file
            output_path = self.output_dir / filename
            scipy.io.wavfile.write(str(output_path), sample_rate, audio)

            logger.info(f"Generated audio saved to: {output_path}")

            return TrackInfo(
                source=str(output_path),
                source_type="ai",
                title=f"AI: {prompt[:40]}...",
                metadata={
                    "prompt": prompt,
                    "duration": duration,
                    "model": model_id,
                    "hf_model_id": model_config.hf_model_id,
                },
            )

        except Exception as e:
            logger.error(f"Failed to generate music: {e}")
            import traceback

            traceback.print_exc()
            return None

    def generate_for_context(
        self,
        mood_prompt: str | None = None,
        temporal_prompt: str | None = None,
        duration: int = 30,
        model_id: str | None = None,
    ) -> TrackInfo | None:
        """Generate context-appropriate music.

        Args:
            mood_prompt: Mood-based prompt component.
            temporal_prompt: Time-based prompt component.
            duration: Duration in seconds.
            model_id: Model to use (optional).

        Returns:
            TrackInfo for the generated audio.
        """
        prompts = []

        if mood_prompt:
            prompts.append(mood_prompt)
        if temporal_prompt:
            prompts.append(temporal_prompt)

        if not prompts:
            prompts.append("ambient background music")

        full_prompt = ", ".join(prompts)
        return self.generate(full_prompt, duration, model_id=model_id)

    def cleanup_old_files(self, max_age_hours: int = 24) -> int:
        """Clean up old generated files.

        Args:
            max_age_hours: Maximum age of files to keep.

        Returns:
            Number of files deleted.
        """
        deleted = 0
        cutoff = time.time() - (max_age_hours * 3600)

        for f in self.output_dir.glob("ai_music_*.wav"):
            if f.stat().st_mtime < cutoff:
                try:
                    f.unlink()
                    deleted += 1
                except OSError:
                    pass

        return deleted


# Provide helpful error message if AI is not available
def get_ai_install_instructions() -> str:
    """Get instructions for installing AI dependencies."""
    return """
AI music generation requires additional dependencies.
Install them with:

    pip install 'coder-music-cli[ai]'

Or install manually:

    pip install torch transformers scipy

Note: This requires significant disk space (~5GB) and RAM (~8GB minimum).
The first generation will download the MusicGen model (~1.5GB).
"""
