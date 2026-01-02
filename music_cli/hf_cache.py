"""HuggingFace cache management utilities.

This module provides functions to inspect, download, and delete models
from the HuggingFace Hub cache. It wraps the huggingface_hub library
for cache operations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Check if huggingface_hub is available
try:
    from huggingface_hub import scan_cache_dir, snapshot_download
    from huggingface_hub.utils import HfHubHTTPError

    HF_HUB_AVAILABLE = True
except ImportError:
    HF_HUB_AVAILABLE = False
    scan_cache_dir = None
    snapshot_download = None
    HfHubHTTPError = Exception


@dataclass
class CacheInfo:
    """Information about a cached model.

    Attributes:
        hf_model_id: HuggingFace model ID (e.g., "facebook/musicgen-small").
        size_bytes: Size on disk in bytes.
        size_gb: Size on disk in gigabytes.
        last_accessed: When the model was last accessed.
        repo_path: Path to the cached repository.
    """

    hf_model_id: str
    size_bytes: int
    size_gb: float
    last_accessed: datetime | None
    repo_path: Path


def is_available() -> bool:
    """Check if HuggingFace Hub utilities are available.

    Returns:
        True if huggingface_hub is installed and importable.
    """
    return HF_HUB_AVAILABLE


def get_hf_cache_dir() -> Path | None:
    """Get the HuggingFace cache directory path.

    Returns:
        Path to the cache directory, or None if not available.
    """
    if not HF_HUB_AVAILABLE:
        return None

    try:
        cache_info = scan_cache_dir()
        return Path(cache_info.cache_dir)
    except Exception as e:
        logger.debug(f"Failed to get cache directory: {e}")
        return None


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Formatted string like "1.5 GB" or "500 MB".
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def scan_all_cached_models() -> dict[str, CacheInfo]:
    """Scan the HuggingFace cache for all cached models.

    Returns:
        Dictionary mapping hf_model_id to CacheInfo.
        Empty dict if cache scan fails or HF Hub unavailable.
    """
    if not HF_HUB_AVAILABLE:
        return {}

    try:
        cache_info = scan_cache_dir()
        result = {}

        for repo in cache_info.repos:
            if repo.repo_type == "model":
                result[repo.repo_id] = CacheInfo(
                    hf_model_id=repo.repo_id,
                    size_bytes=repo.size_on_disk,
                    size_gb=repo.size_on_disk / (1024 * 1024 * 1024),
                    last_accessed=repo.last_accessed,
                    repo_path=repo.repo_path,
                )

        return result
    except Exception as e:
        logger.warning(f"Failed to scan HuggingFace cache: {e}")
        return {}


def get_model_cache_info(hf_model_id: str) -> CacheInfo | None:
    """Get cache information for a specific model.

    Args:
        hf_model_id: HuggingFace model ID (e.g., "facebook/musicgen-small").

    Returns:
        CacheInfo if model is cached, None otherwise.
    """
    cached_models = scan_all_cached_models()
    return cached_models.get(hf_model_id)


def is_model_downloaded(hf_model_id: str) -> bool:
    """Check if a model is downloaded to cache.

    Args:
        hf_model_id: HuggingFace model ID.

    Returns:
        True if model is in cache.
    """
    return get_model_cache_info(hf_model_id) is not None


def download_model(hf_model_id: str, resume: bool = True) -> bool:
    """Download a model from HuggingFace Hub.

    Uses snapshot_download which automatically shows progress bars.

    Args:
        hf_model_id: HuggingFace model ID to download.
        resume: Whether to resume interrupted downloads.

    Returns:
        True if download succeeded, False otherwise.
    """
    if not HF_HUB_AVAILABLE:
        logger.error("HuggingFace Hub not available")
        return False

    try:
        # snapshot_download automatically shows progress via tqdm
        snapshot_download(
            repo_id=hf_model_id,
            resume_download=resume,
        )
        return True
    except HfHubHTTPError as e:
        logger.error(f"HTTP error downloading {hf_model_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to download {hf_model_id}: {e}")
        return False


def delete_model(hf_model_id: str) -> tuple[bool, int]:
    """Delete a model from the HuggingFace cache.

    Args:
        hf_model_id: HuggingFace model ID to delete.

    Returns:
        Tuple of (success, bytes_freed). bytes_freed is 0 if deletion failed.
    """
    if not HF_HUB_AVAILABLE:
        logger.error("HuggingFace Hub not available")
        return False, 0

    try:
        cache_info = scan_cache_dir()

        # Find the repository
        target_repo = None
        for repo in cache_info.repos:
            if repo.repo_id == hf_model_id and repo.repo_type == "model":
                target_repo = repo
                break

        if target_repo is None:
            logger.warning(f"Model {hf_model_id} not found in cache")
            return False, 0

        size_freed = target_repo.size_on_disk

        # Get all revision commit hashes for this repo
        revision_hashes = [rev.commit_hash for rev in target_repo.revisions]

        if not revision_hashes:
            logger.warning(f"No revisions found for {hf_model_id}")
            return False, 0

        # Create delete strategy and execute
        delete_strategy = cache_info.delete_revisions(*revision_hashes)
        delete_strategy.execute()

        logger.info(f"Deleted {hf_model_id}, freed {format_size(size_freed)}")
        return True, size_freed

    except Exception as e:
        logger.error(f"Failed to delete {hf_model_id}: {e}")
        return False, 0
