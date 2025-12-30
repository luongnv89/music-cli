"""Model registry for managing and creating model strategies."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .model_config import ModelConfig
    from .model_strategy import ModelStrategy

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Registry for model strategy classes.

    The registry maps model types (e.g., "musicgen", "audioldm") to their
    corresponding strategy classes. This allows for easy extension with
    new model types without modifying the core generation logic.

    Example:
        # Register a new strategy
        ModelRegistry.register("audioldm", AudioLDMStrategy)

        # Create strategy for a model
        strategy = ModelRegistry.create_strategy(model_config)
    """

    _strategies: dict[str, type[ModelStrategy]] = {}

    @classmethod
    def register(cls, model_type: str, strategy_class: type[ModelStrategy]) -> None:
        """Register a strategy class for a model type.

        Args:
            model_type: Type identifier (e.g., "musicgen", "audioldm").
            strategy_class: Strategy class to use for this model type.
        """
        cls._strategies[model_type] = strategy_class
        logger.debug(f"Registered strategy for model type: {model_type}")

    @classmethod
    def unregister(cls, model_type: str) -> bool:
        """Unregister a strategy for a model type.

        Args:
            model_type: Type identifier to unregister.

        Returns:
            True if unregistered, False if not found.
        """
        if model_type in cls._strategies:
            del cls._strategies[model_type]
            logger.debug(f"Unregistered strategy for model type: {model_type}")
            return True
        return False

    @classmethod
    def create_strategy(cls, config: ModelConfig) -> ModelStrategy:
        """Create a strategy instance for a model configuration.

        Args:
            config: ModelConfig with model_type specifying which strategy to use.

        Returns:
            Strategy instance configured for the model.

        Raises:
            ValueError: If no strategy is registered for the model type.
        """
        strategy_class = cls._strategies.get(config.model_type)
        if strategy_class is None:
            available = ", ".join(cls._strategies.keys()) or "none"
            raise ValueError(
                f"No strategy registered for model type '{config.model_type}'. "
                f"Available types: {available}"
            )

        return strategy_class(config)

    @classmethod
    def get_supported_types(cls) -> list[str]:
        """Get list of supported model types.

        Returns:
            List of registered model type identifiers.
        """
        return list(cls._strategies.keys())

    @classmethod
    def is_supported(cls, model_type: str) -> bool:
        """Check if a model type is supported.

        Args:
            model_type: Type identifier to check.

        Returns:
            True if a strategy is registered for this type.
        """
        return model_type in cls._strategies

    @classmethod
    def clear(cls) -> None:
        """Clear all registered strategies (mainly for testing)."""
        cls._strategies.clear()


def _register_built_in_strategies() -> None:
    """Register built-in model strategies.

    This function is called automatically when the module is imported.
    """
    from .audioldm_strategy import AudioLDMStrategy
    from .bark_strategy import BarkStrategy
    from .musicgen_strategy import MusicGenStrategy

    ModelRegistry.register("musicgen", MusicGenStrategy)
    ModelRegistry.register("audioldm", AudioLDMStrategy)
    ModelRegistry.register("bark", BarkStrategy)


# Register built-in strategies on module import
_register_built_in_strategies()
