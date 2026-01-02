"""Model management business logic layer.

This module provides the ModelManager class which handles all model
management operations: listing, downloading, deleting, and setting defaults.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from . import hf_cache
from .config import Config
from .sources.ai_models import ModelConfig

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Complete model information for display.

    Combines configuration data with cache status for a unified view.

    Attributes:
        id: Model ID (e.g., "musicgen-small").
        hf_model_id: HuggingFace model ID (e.g., "facebook/musicgen-small").
        model_type: Type of model (musicgen, audioldm, bark).
        description: Human-readable description.
        expected_size_gb: Expected download size in GB.
        is_downloaded: Whether model is in cache.
        cached_size_gb: Actual cached size in GB (None if not downloaded).
        is_default: Whether this is the default model.
        enabled: Whether the model is enabled.
        max_duration: Maximum generation duration in seconds.
    """

    id: str
    hf_model_id: str
    model_type: str
    description: str
    expected_size_gb: float
    is_downloaded: bool
    cached_size_gb: float | None
    is_default: bool
    enabled: bool
    max_duration: int


class ModelManager:
    """Manages AI model operations.

    Provides a business logic layer for model management, coordinating
    between configuration, HuggingFace cache, and the CLI.

    Args:
        config: Config instance for model settings.
    """

    def __init__(self, config: Config):
        """Initialize the model manager.

        Args:
            config: Config instance to use for model settings.
        """
        self._config = config

    def list_models(self) -> list[ModelInfo]:
        """List all configured models with their cache status.

        Returns:
            List of ModelInfo objects with complete model information,
            sorted by model type then model ID.
        """
        models_config = self._config.get("ai.models", {})

        # Fall back to DEFAULT_CONFIG if user's config doesn't have ai.models
        if not models_config:
            from .sources.ai_models import DEFAULT_AI_MODELS_CONFIG

            models_config = DEFAULT_AI_MODELS_CONFIG.get("models", {})

        default_model = self._config.get_default_ai_model()

        # Get cache information for all models
        cache_info = hf_cache.scan_all_cached_models()

        result = []
        for model_id, model_data in models_config.items():
            model = ModelConfig.from_dict(model_id, model_data)
            hf_model_id = model.hf_model_id

            # Check if downloaded
            cached = cache_info.get(hf_model_id)
            is_downloaded = cached is not None
            cached_size_gb = cached.size_gb if cached else None

            result.append(
                ModelInfo(
                    id=model_id,
                    hf_model_id=hf_model_id,
                    model_type=model.model_type,
                    description=model.description,
                    expected_size_gb=model.expected_size_gb,
                    is_downloaded=is_downloaded,
                    cached_size_gb=cached_size_gb,
                    is_default=(model_id == default_model),
                    enabled=model.enabled,
                    max_duration=model.max_duration,
                )
            )

        # Sort by model_type, then by id
        type_order = {"musicgen": 0, "audioldm": 1, "bark": 2}
        result.sort(key=lambda m: (type_order.get(m.model_type, 99), m.id))

        return result

    def get_model(self, model_id: str) -> ModelInfo | None:
        """Get information for a specific model.

        Args:
            model_id: The model ID to look up.

        Returns:
            ModelInfo if found, None otherwise.
        """
        models = self.list_models()
        for model in models:
            if model.id == model_id:
                return model
        return None

    def validate_model(self, model_id: str) -> tuple[bool, str]:
        """Validate that a model ID is valid and enabled.

        Args:
            model_id: The model ID to validate.

        Returns:
            Tuple of (is_valid, error_message). error_message is empty if valid.
        """
        model = self.get_model(model_id)
        if model is None:
            available = ", ".join(m.id for m in self.list_models())
            return False, f"Unknown model '{model_id}'. Available: {available}"

        if not model.enabled:
            return False, f"Model '{model_id}' is disabled"

        return True, ""

    def download_model(self, model_id: str) -> tuple[bool, str]:
        """Download a model from HuggingFace Hub.

        Args:
            model_id: The model ID to download.

        Returns:
            Tuple of (success, message).
        """
        # Validate model
        is_valid, error = self.validate_model(model_id)
        if not is_valid:
            return False, error

        model = self.get_model(model_id)
        if model is None:
            return False, f"Model '{model_id}' not found"

        if not hf_cache.is_available():
            return (
                False,
                "HuggingFace Hub utilities not available. "
                "Install with: pip install 'coder-music-cli[ai]'",
            )

        # Check if already downloaded
        if model.is_downloaded:
            size = f"{model.cached_size_gb:.1f} GB" if model.cached_size_gb else "unknown size"
            return True, f"Model '{model_id}' is already downloaded ({size})"

        # Download the model
        success = hf_cache.download_model(model.hf_model_id)
        if success:
            return True, f"Successfully downloaded '{model_id}'"
        else:
            return False, f"Failed to download '{model_id}'. Check your network connection."

    def delete_model(self, model_id: str) -> tuple[bool, str, int]:
        """Delete a model from the HuggingFace cache.

        Args:
            model_id: The model ID to delete.

        Returns:
            Tuple of (success, message, bytes_freed).
        """
        model = self.get_model(model_id)
        if model is None:
            return False, f"Unknown model '{model_id}'", 0

        if not hf_cache.is_available():
            return False, "HuggingFace Hub utilities not available", 0

        if not model.is_downloaded:
            return False, f"Model '{model_id}' is not downloaded", 0

        # Delete from cache
        success, bytes_freed = hf_cache.delete_model(model.hf_model_id)

        if success:
            size_str = hf_cache.format_size(bytes_freed)
            # Also clear from in-memory strategy cache if loaded
            self._clear_strategy_cache(model_id)
            return True, f"Deleted '{model_id}' (freed {size_str})", bytes_freed
        else:
            return False, f"Failed to delete '{model_id}'", 0

    def _clear_strategy_cache(self, model_id: str) -> None:
        """Clear a model from the in-memory strategy cache.

        Args:
            model_id: The model ID to clear.
        """
        try:
            from .sources.ai_models import get_strategy_cache

            cache = get_strategy_cache()
            if cache is not None:
                cache.remove(model_id)
                logger.debug(f"Cleared {model_id} from strategy cache")
        except Exception as e:
            logger.debug(f"Could not clear strategy cache: {e}")

    def set_default_model(self, model_id: str) -> tuple[bool, str]:
        """Set the default AI model.

        Args:
            model_id: The model ID to set as default.

        Returns:
            Tuple of (success, message).
        """
        # Validate model
        is_valid, error = self.validate_model(model_id)
        if not is_valid:
            return False, error

        # Set as default
        self._config.set_default_ai_model(model_id)
        return True, f"Default model set to '{model_id}'"

    def get_summary(self) -> dict:
        """Get a summary of model status.

        Returns:
            Dictionary with:
            - total: Total number of models
            - downloaded: Number of downloaded models
            - total_size_gb: Total cached size in GB
            - default_model: Default model ID
        """
        models = self.list_models()
        downloaded = [m for m in models if m.is_downloaded]
        total_size_gb = sum(m.cached_size_gb or 0 for m in downloaded)

        return {
            "total": len(models),
            "downloaded": len(downloaded),
            "total_size_gb": total_size_gb,
            "default_model": self._config.get_default_ai_model(),
        }
