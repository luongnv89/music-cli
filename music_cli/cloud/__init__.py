"""Cloud adapter layer for GMI Cloud and OpenRouter (#133, plan task P1.2).

Public surface::

    from music_cli.cloud import GMIAdapter, OpenRouterAdapter, DiskStrategyCache

Both adapters import without the ``gmi`` extra installed (``httpx`` is
loaded lazily by :func:`music_cli.cloud.base.httpx_transport`); only
actually issuing live requests requires it.
"""

from __future__ import annotations

from .base import (
    MAX_ATTEMPTS,
    TRANSIENT_STATUSES,
    AdapterError,
    BaseAdapter,
    PollCancelledError,
    TransientError,
    idempotency_key,
)
from .gmi import GMIAdapter
from .openrouter import OpenRouterAdapter
from .strategy_cache import DiskStrategyCache, cache_key

__all__ = [
    "MAX_ATTEMPTS",
    "TRANSIENT_STATUSES",
    "AdapterError",
    "BaseAdapter",
    "DiskStrategyCache",
    "GMIAdapter",
    "PollCancelledError",
    "OpenRouterAdapter",
    "TransientError",
    "cache_key",
    "idempotency_key",
]
