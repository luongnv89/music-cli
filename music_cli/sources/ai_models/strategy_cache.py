"""LRU cache for model strategies with GPU memory management."""

from __future__ import annotations

import gc
import logging
import threading
from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .model_strategy import ModelStrategy

logger = logging.getLogger(__name__)


class LRUStrategyCache:
    """LRU (Least Recently Used) cache for model strategies.

    This cache manages loaded model strategies with a maximum size limit.
    When the cache is full and a new model needs to be loaded, the least
    recently used model is evicted and its GPU memory is freed.

    Thread-safe implementation using a lock for all operations.

    Attributes:
        max_size: Maximum number of models to keep in memory.
    """

    def __init__(self, max_size: int = 2):
        """Initialize the LRU cache.

        Args:
            max_size: Maximum number of models to keep in memory.
                     Set to 0 for unlimited (not recommended).
        """
        self._cache: OrderedDict[str, ModelStrategy] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()

    @property
    def max_size(self) -> int:
        """Get the maximum cache size."""
        return self._max_size

    @max_size.setter
    def max_size(self, value: int) -> None:
        """Set the maximum cache size and evict if necessary."""
        with self._lock:
            self._max_size = value
            if value > 0:
                self._evict_to_size(value)

    def get(self, model_id: str) -> ModelStrategy | None:
        """Get a strategy from the cache, marking it as recently used.

        Args:
            model_id: The model ID to look up.

        Returns:
            The cached ModelStrategy, or None if not found.
        """
        with self._lock:
            if model_id not in self._cache:
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(model_id)
            return self._cache[model_id]

    def put(self, model_id: str, strategy: ModelStrategy) -> None:
        """Add or update a strategy in the cache.

        If the cache is full, the least recently used strategy is evicted.

        Args:
            model_id: The model ID.
            strategy: The ModelStrategy instance.
        """
        with self._lock:
            # If already in cache, update and move to end
            if model_id in self._cache:
                self._cache[model_id] = strategy
                self._cache.move_to_end(model_id)
                return

            # Evict if at capacity
            if self._max_size > 0 and len(self._cache) >= self._max_size:
                self._evict_oldest()

            # Add new entry
            self._cache[model_id] = strategy

    def remove(self, model_id: str) -> bool:
        """Remove a strategy from the cache and unload it.

        Args:
            model_id: The model ID to remove.

        Returns:
            True if the model was found and removed, False otherwise.
        """
        with self._lock:
            if model_id not in self._cache:
                return False

            strategy = self._cache.pop(model_id)
            self._unload_strategy(strategy)
            return True

    def clear(self) -> None:
        """Clear all strategies from the cache and free memory."""
        with self._lock:
            for strategy in self._cache.values():
                self._unload_strategy(strategy)
            self._cache.clear()
            self._cleanup_gpu_memory()
            logger.info("Strategy cache cleared")

    def contains(self, model_id: str) -> bool:
        """Check if a model is in the cache.

        Args:
            model_id: The model ID to check.

        Returns:
            True if the model is cached, False otherwise.
        """
        with self._lock:
            return model_id in self._cache

    def size(self) -> int:
        """Get the current number of cached models.

        Returns:
            Number of models in the cache.
        """
        with self._lock:
            return len(self._cache)

    def get_cached_models(self) -> list[str]:
        """Get list of currently cached model IDs.

        Returns:
            List of model IDs in cache, ordered from oldest to newest.
        """
        with self._lock:
            return list(self._cache.keys())

    def _evict_oldest(self) -> None:
        """Evict the oldest (least recently used) entry.

        Must be called with lock held.
        """
        if not self._cache:
            return

        # Get oldest entry (first in OrderedDict)
        model_id, strategy = self._cache.popitem(last=False)
        logger.info(f"Evicting model '{model_id}' from cache (LRU)")
        self._unload_strategy(strategy)
        self._cleanup_gpu_memory()

    def _evict_to_size(self, target_size: int) -> None:
        """Evict entries until cache is at target size.

        Must be called with lock held.

        Args:
            target_size: Target cache size.
        """
        while len(self._cache) > target_size:
            self._evict_oldest()

    def _unload_strategy(self, strategy: ModelStrategy) -> None:
        """Unload a strategy and free its resources.

        Args:
            strategy: The strategy to unload.
        """
        try:
            strategy.unload()
        except Exception as e:
            logger.warning(f"Error unloading strategy: {e}")

    def _cleanup_gpu_memory(self) -> None:
        """Force GPU memory cleanup."""
        gc.collect()

        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.debug("GPU memory cache cleared")
        except ImportError:
            pass


# Global cache instance
_global_cache: LRUStrategyCache | None = None
_global_cache_lock = threading.Lock()


def get_strategy_cache(max_size: int = 2) -> LRUStrategyCache:
    """Get the global strategy cache instance.

    Thread-safe singleton pattern with double-checked locking.

    Args:
        max_size: Maximum cache size (only used on first call).

    Returns:
        The global LRUStrategyCache instance.
    """
    global _global_cache
    if _global_cache is None:
        with _global_cache_lock:
            # Double-check pattern to avoid race condition
            if _global_cache is None:
                _global_cache = LRUStrategyCache(max_size=max_size)
    return _global_cache


def clear_global_cache() -> None:
    """Clear the global strategy cache."""
    global _global_cache
    if _global_cache is not None:
        _global_cache.clear()
