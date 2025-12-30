"""Abstract base class for model strategies."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from .model_config import ModelConfig

logger = logging.getLogger(__name__)


class ModelStrategy(ABC):
    """Abstract base class for HuggingFace model strategies.

    Each strategy encapsulates the loading and generation logic for a specific
    type of text-to-audio model. Implementations handle model-specific details
    like tokenization, generation parameters, and audio extraction.

    Attributes:
        config: The ModelConfig for this strategy.
    """

    def __init__(self, config: ModelConfig):
        """Initialize the strategy with model configuration.

        Args:
            config: ModelConfig instance with model parameters.
        """
        self.config = config
        self._model: Any = None
        self._processor: Any = None

    @property
    def model_id(self) -> str:
        """Get the HuggingFace model ID."""
        return self.config.hf_model_id

    @property
    def is_loaded(self) -> bool:
        """Check if the model is loaded."""
        return self._model is not None

    @abstractmethod
    def load_model(self) -> tuple[Any, Any]:
        """Load the model and processor from HuggingFace.

        This method should handle downloading and initializing the model.
        The returned values are stored in _model and _processor.

        Returns:
            Tuple of (model, processor). Processor may be None for some models.

        Raises:
            ImportError: If required dependencies are not installed.
            Exception: If model loading fails.
        """
        pass

    @abstractmethod
    def generate_audio(
        self,
        prompt: str,
        duration: int,
    ) -> tuple[np.ndarray, int]:
        """Generate audio from a text prompt.

        Args:
            prompt: Text description of the audio to generate.
            duration: Duration in seconds (already clamped to model limits).

        Returns:
            Tuple of (audio_array, sample_rate) where audio_array is a
            numpy array of int16 values.

        Raises:
            Exception: If generation fails.
        """
        pass

    def ensure_loaded(self) -> bool:
        """Ensure the model is loaded, loading it if necessary.

        Returns:
            True if model is loaded and ready, False otherwise.
        """
        if self.is_loaded:
            return True

        try:
            from .progress_callback import with_progress

            def do_load():
                return self.load_model()

            self._model, self._processor = with_progress(self.config.id, do_load)
            return True
        except ImportError as e:
            logger.error(f"Missing dependencies for {self.model_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to load model {self.model_id}: {e}")
            return False

    def get_max_tokens(self, duration: int) -> int:
        """Calculate max_new_tokens based on duration.

        Uses the tokens_per_second from model config.

        Args:
            duration: Duration in seconds.

        Returns:
            Number of tokens to generate.
        """
        return self.config.get_max_tokens(duration)

    def unload(self) -> None:
        """Unload the model to free memory."""
        # Move model to CPU first to free GPU memory
        if self._model is not None:
            try:
                if hasattr(self._model, "to"):
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
