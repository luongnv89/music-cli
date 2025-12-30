"""AI model strategies for HuggingFace text-to-audio generation.

This package provides a strategy pattern implementation for supporting
multiple HuggingFace text-to-audio models. Each model type (MusicGen,
AudioLDM, Bark) has its own strategy that handles model-specific loading
and generation logic.

Supported model types:
- **MusicGen**: Meta's music generation models (facebook/musicgen-*)
- **AudioLDM**: CVSSP's latent diffusion audio models (cvssp/audioldm-*)
- **Bark**: Suno's text-to-speech/audio models (suno/bark*)

Example usage:
    from music_cli.sources.ai_models import (
        AIModelsConfig,
        ModelConfig,
        ModelRegistry,
    )

    # Load config from TOML
    config = AIModelsConfig.from_dict(toml_data["ai"])

    # Get a model configuration
    model_config = config.get_model("musicgen-small")

    # Create strategy for the model
    strategy = ModelRegistry.create_strategy(model_config)

    # Generate audio
    if strategy.ensure_loaded():
        audio, sample_rate = strategy.generate_audio(prompt, duration)
"""

from .audioldm_strategy import AudioLDMStrategy
from .bark_strategy import BarkStrategy
from .model_config import DEFAULT_AI_MODELS_CONFIG, AIModelsConfig, ModelConfig
from .model_registry import ModelRegistry
from .model_strategy import ModelStrategy
from .musicgen_strategy import MusicGenStrategy
from .strategy_cache import LRUStrategyCache, clear_global_cache, get_strategy_cache

__all__ = [
    "AIModelsConfig",
    "AudioLDMStrategy",
    "BarkStrategy",
    "DEFAULT_AI_MODELS_CONFIG",
    "LRUStrategyCache",
    "ModelConfig",
    "ModelRegistry",
    "ModelStrategy",
    "MusicGenStrategy",
    "clear_global_cache",
    "get_strategy_cache",
]
