"""Resumable on-disk cache for cloud adapter jobs (#133).

Where ``music_cli/sources/ai_models/strategy_cache.py`` keeps *model
strategies* in memory (LRU, GPU-memory aware), this module persists *job
results* for the GMI Cloud / OpenRouter adapters on disk:

- the key is the model + prompt hash + parameters (canonical JSON, sha256)
- a completed hit returns instantly, with no HTTP traffic
- an in-flight job is journaled as ``pending`` with its queue id, so a
  restarted process resumes polling instead of submitting a duplicate job
- writes are atomic (temp file + ``Path.replace``) and corrupt or unreadable
  entries are ignored rather than raised — the cache can always be rebuilt
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


def cache_key(model: str, prompt: str, params: dict[str, Any] | None = None) -> str:
    """Deterministic cache key: model + prompt hash + parameters.

    All three components are folded into one canonical-JSON blob and hashed,
    so any change in model, prompt or parameters produces a different key.
    """
    material = json.dumps(
        {"model": model, "prompt": prompt, "params": params or {}},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class DiskStrategyCache:
    """File-backed ``{key: record}`` store for adapter results.

    Records are JSON objects of one of two shapes::

        {"status": "pending", "provider": "gmi", "job_id": "req-123"}
        {"status": "completed", "result": {...}}

    One JSON file per key under ``root``, written atomically.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(model: str, prompt: str, params: dict[str, Any] | None = None) -> str:
        """Return the cache key for a logical request (see :func:`cache_key`)."""
        return cache_key(model, prompt, params)

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    _VALID_STATUS = frozenset({"pending", "completed"})

    def get(self, key: str) -> dict[str, Any] | None:
        """Return the record for ``key``, or ``None`` if absent/unreadable.

        Records that do not match one of the two documented shapes (a
        ``completed`` record without ``result``, a ``pending`` record without
        a usable ``job_id``, an unknown ``status``) are treated as corrupt and
        ignored, per the module contract.
        """
        try:
            record = json.loads(self._path(key).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(record, dict):
            return None
        status = record.get("status")
        if status not in self._VALID_STATUS:
            return None
        if status == "completed" and "result" not in record:
            logger.warning("cache: ignoring corrupt entry %s (completed, no result)", key)
            return None
        if status == "pending":
            job_id = record.get("job_id")
            if not isinstance(job_id, str) or not job_id:
                logger.warning("cache: ignoring corrupt entry %s (pending, bad job id)", key)
                return None
        return record

    def put(self, key: str, record: dict[str, Any]) -> None:
        """Atomically store ``record`` under ``key``."""
        path = self._path(key)
        tmp = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
        try:
            tmp.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
            tmp.replace(path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def keys(self) -> list[str]:
        """Return every cached key (stem of each ``*.json`` entry)."""
        return sorted(p.stem for p in self.root.glob("*.json"))

    def clear(self) -> None:
        """Delete every cached record (used by tests and `mc cloud` admin)."""
        for path in self.root.glob("*.json"):
            path.unlink(missing_ok=True)
