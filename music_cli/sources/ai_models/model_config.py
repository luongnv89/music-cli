"""Model configuration schema and validation for AI music generation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Configuration for a single HuggingFace text-to-audio model.

    Attributes:
        id: Unique identifier for this model (e.g., "musicgen-small").
        hf_model_id: Full HuggingFace model ID (e.g., "facebook/musicgen-small").
        model_type: Type of model, determines which strategy to use
                   (e.g., "musicgen", "audioldm", "bark").
        description: Human-readable description of the model.
        expected_size_gb: Approximate download size in gigabytes.
        default_duration: Default generation duration in seconds.
        max_duration: Maximum allowed duration in seconds.
        min_duration: Minimum allowed duration in seconds.
        tokens_per_second: Model-specific token rate for duration calculation.
        enabled: Whether this model is active and available for use.
        extra_params: Model-specific parameters (e.g., guidance_scale).
        revision: Pinned HuggingFace commit SHA for reproducible downloads.
    """

    id: str
    hf_model_id: str
    model_type: str
    revision: str | None = None
    description: str = ""
    expected_size_gb: float = 0.0
    default_duration: int = 30
    max_duration: int = 60
    min_duration: int = 5
    tokens_per_second: int = 50
    enabled: bool = True
    supports_lyrics: bool = False
    requires_lyrics: bool = False
    extra_params: dict[str, Any] = field(default_factory=dict)

    def clamp_duration(self, duration: int) -> int:
        """Clamp duration to model's allowed range.

        Args:
            duration: Requested duration in seconds.

        Returns:
            Duration clamped to [min_duration, max_duration].
        """
        return max(self.min_duration, min(self.max_duration, duration))

    def get_max_tokens(self, duration: int) -> int:
        """Calculate max_new_tokens based on duration.

        Args:
            duration: Duration in seconds.

        Returns:
            Number of tokens to generate.
        """
        return duration * self.tokens_per_second

    @classmethod
    def from_dict(cls, model_id: str, data: dict[str, Any]) -> ModelConfig:
        """Create ModelConfig from a dictionary.

        Args:
            model_id: The unique identifier for this model.
            data: Dictionary with model configuration.

        Returns:
            ModelConfig instance.
        """
        return cls(
            id=model_id,
            hf_model_id=data.get("hf_model_id", f"facebook/{model_id}"),
            model_type=data.get("model_type", "musicgen"),
            revision=data.get("revision"),
            description=data.get("description", ""),
            expected_size_gb=data.get("expected_size_gb", 0.0),
            default_duration=data.get("default_duration", 30),
            max_duration=data.get("max_duration", 60),
            min_duration=data.get("min_duration", 5),
            tokens_per_second=data.get("tokens_per_second", 50),
            enabled=data.get("enabled", True),
            supports_lyrics=data.get("supports_lyrics", False),
            requires_lyrics=data.get("requires_lyrics", False),
            extra_params=data.get("extra_params", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for TOML serialization.

        Returns:
            Dictionary representation of the model config.
        """
        result: dict[str, Any] = {
            "hf_model_id": self.hf_model_id,
            "model_type": self.model_type,
            "description": self.description,
        }
        if self.revision:
            result["revision"] = self.revision
        result["expected_size_gb"] = self.expected_size_gb
        result["default_duration"] = self.default_duration
        result["max_duration"] = self.max_duration
        result["min_duration"] = self.min_duration
        result["tokens_per_second"] = self.tokens_per_second
        result["enabled"] = self.enabled
        result["supports_lyrics"] = self.supports_lyrics
        result["requires_lyrics"] = self.requires_lyrics
        if self.extra_params:
            result["extra_params"] = self.extra_params
        return result


@dataclass
class AIModelsConfig:
    """Container for all AI model configurations.

    Attributes:
        default_model: ID of the default model to use.
        models: Dictionary of model ID to ModelConfig.
    """

    default_model: str
    models: dict[str, ModelConfig] = field(default_factory=dict)

    def get_model(self, model_id: str | None = None) -> ModelConfig | None:
        """Get configuration for a specific model.

        Args:
            model_id: Model ID to look up. If None, returns default model.

        Returns:
            ModelConfig if found and enabled, None otherwise.
        """
        if model_id is None:
            model_id = self.default_model

        model = self.models.get(model_id)
        if model is None:
            logger.warning(f"Model '{model_id}' not found in configuration")
            return None

        if not model.enabled:
            logger.warning(f"Model '{model_id}' is disabled")
            return None

        return model

    def get_default_model(self) -> ModelConfig | None:
        """Get the default model configuration.

        Returns:
            Default ModelConfig if configured and enabled, None otherwise.
        """
        return self.get_model(self.default_model)

    def list_models(self, enabled_only: bool = False) -> list[str]:
        """Get list of available model IDs.

        Args:
            enabled_only: If True, only return enabled models.

        Returns:
            List of model IDs.
        """
        if enabled_only:
            return [mid for mid, m in self.models.items() if m.enabled]
        return list(self.models.keys())

    def validate(self) -> list[str]:
        """Validate the configuration.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors = []

        if not self.default_model:
            errors.append("default_model is required")

        if self.default_model and self.default_model not in self.models:
            errors.append(f"default_model '{self.default_model}' not found in models")

        for model_id, model in self.models.items():
            if not model.hf_model_id:
                errors.append(f"Model '{model_id}' missing hf_model_id")
            if not model.model_type:
                errors.append(f"Model '{model_id}' missing model_type")
            if model.min_duration > model.max_duration:
                errors.append(f"Model '{model_id}' has min_duration > max_duration")

        return errors

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AIModelsConfig:
        """Create AIModelsConfig from a dictionary (typically from TOML).

        Args:
            data: Dictionary with 'default_model' and 'models' keys.

        Returns:
            AIModelsConfig instance.
        """
        default_model = data.get("default_model", "musicgen-small")
        models_data = data.get("models", {})

        models = {}
        for model_id, model_data in models_data.items():
            models[model_id] = ModelConfig.from_dict(model_id, model_data)

        return cls(default_model=default_model, models=models)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for TOML serialization.

        Returns:
            Dictionary representation of the AI models config.
        """
        return {
            "default_model": self.default_model,
            "models": {mid: m.to_dict() for mid, m in self.models.items()},
        }


# Default AI models configuration
DEFAULT_AI_MODELS_CONFIG: dict[str, Any] = {
    "default_model": "musicgen-small",
    "cache": {
        "max_models": 2,  # Maximum models to keep in memory
    },
    "models": {
        # MusicGen models (Meta) - Music generation
        "musicgen-small": {
            "hf_model_id": "facebook/musicgen-small",
            "revision": "4c8334b02c6ec4e8664a91979669a501ec497792",
            "model_type": "musicgen",
            "description": "Fast music generation, good quality",
            "expected_size_gb": 2.0,
            "default_duration": 30,
            "max_duration": 60,
            "min_duration": 5,
            "tokens_per_second": 50,
            "enabled": True,
        },
        "musicgen-medium": {
            "hf_model_id": "facebook/musicgen-medium",
            "revision": "d3bd7b00761b78ad7a8a05145ee31e7832e9916c",
            "model_type": "musicgen",
            "description": "Balanced speed and quality",
            "expected_size_gb": 3.5,
            "default_duration": 30,
            "max_duration": 60,
            "min_duration": 5,
            "tokens_per_second": 50,
            "enabled": True,
        },
        "musicgen-large": {
            "hf_model_id": "facebook/musicgen-large",
            "revision": "15ccdc92099879e47b6da12c350cdb71d4eab3ca",
            "model_type": "musicgen",
            "description": "Best quality, slower generation",
            "expected_size_gb": 7.0,
            "default_duration": 20,
            "max_duration": 45,
            "min_duration": 5,
            "tokens_per_second": 50,
            "enabled": True,
        },
        "musicgen-melody": {
            "hf_model_id": "facebook/musicgen-melody",
            "revision": "68d653a95788ec0d2b0abccab22c0b3a200c2d90",
            "model_type": "musicgen",
            "description": "Melody-conditioned generation",
            "expected_size_gb": 3.5,
            "default_duration": 30,
            "max_duration": 60,
            "min_duration": 5,
            "tokens_per_second": 50,
            "enabled": True,
        },
        # MiniMax models (MiniMaxAI) - lyrics-conditioned music generation
        "minimax-music3": {
            "hf_model_id": "MiniMaxAI/MiniMax-Music3",
            "revision": "fbdf52fbaaca799592917417eb05f1899f1255ec",
            "model_type": "minimax_music3",
            "description": "Long-form lyrics-conditioned music generation",
            "expected_size_gb": 24.0,
            "default_duration": 60,
            "max_duration": 300,
            "min_duration": 5,
            "tokens_per_second": 25,
            "enabled": True,
            "supports_lyrics": True,
            "requires_lyrics": True,
        },
        # AudioLDM models (CVSSP) - General audio/sound effects
        "audioldm-s-full-v2": {
            "hf_model_id": "cvssp/audioldm-s-full-v2",
            "revision": "feeb3d14203495a4b6ac0893cbdedb2159b4819c",
            "model_type": "audioldm",
            "description": "Sound effects and ambient audio",
            "expected_size_gb": 1.5,
            "default_duration": 10,
            "max_duration": 30,
            "min_duration": 2,
            "tokens_per_second": 50,
            "enabled": True,
            "extra_params": {
                "num_inference_steps": 10,
                "guidance_scale": 2.5,
            },
        },
        "audioldm-l-full": {
            "hf_model_id": "cvssp/audioldm-l-full",
            "revision": "26aec6fc5bb4f855a11e8357e0d69c8dc9d0ab95",
            "model_type": "audioldm",
            "description": "High-quality audio generation",
            "expected_size_gb": 3.0,
            "default_duration": 10,
            "max_duration": 30,
            "min_duration": 2,
            "tokens_per_second": 50,
            "enabled": True,
            "extra_params": {
                "num_inference_steps": 10,
                "guidance_scale": 2.5,
            },
        },
        # Bark models (Suno) - Speech and audio synthesis
        "bark": {
            "hf_model_id": "suno/bark",
            "revision": "70a8a7d34168586dc5d028fa9666aceade177992",
            "model_type": "bark",
            "description": "Speech synthesis and audio effects",
            "expected_size_gb": 5.0,
            "default_duration": 10,
            "max_duration": 15,
            "min_duration": 2,
            "tokens_per_second": 50,
            "enabled": True,
        },
        "bark-small": {
            "hf_model_id": "suno/bark-small",
            "revision": "1dbd7a128513b8ae4a4e2130fed57b7ac9da5bcd",
            "model_type": "bark",
            "description": "Faster speech synthesis",
            "expected_size_gb": 2.0,
            "default_duration": 10,
            "max_duration": 15,
            "min_duration": 2,
            "tokens_per_second": 50,
            "enabled": True,
        },
    },
}
