"""Progress callback for HuggingFace model downloads."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class DownloadProgressCallback:
    """Progress callback for HuggingFace model downloads.

    Shows a tqdm progress bar when running interactively in CLI,
    falls back to logging progress when non-interactive.

    Usage:
        callback = DownloadProgressCallback("model-name")
        model = Model.from_pretrained("model-id", progress_callback=callback)
        callback.close()  # Clean up when done
    """

    def __init__(self, model_name: str, disable: bool = False):
        """Initialize the progress callback.

        Args:
            model_name: Human-readable name for the model being downloaded.
            disable: If True, disable progress display entirely.
        """
        self.model_name = model_name
        self.disable = disable
        self._pbar: Any = None
        self._last_logged_percent: int = 0
        self._use_tqdm = self._can_use_tqdm()

    def _can_use_tqdm(self) -> bool:
        """Check if we can use tqdm for progress display.

        Returns:
            True if tqdm is available and stdout is a TTY.
        """
        if self.disable:
            return False

        try:
            import tqdm  # noqa: F401

            # Check if stdout is a TTY (interactive terminal)
            return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
        except ImportError:
            return False

    def __call__(
        self,
        current: int,
        total: int,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Handle progress update.

        This is the callback signature expected by HuggingFace.

        Args:
            current: Current bytes downloaded.
            total: Total bytes to download.
            *args: Additional positional arguments (ignored).
            **kwargs: Additional keyword arguments (ignored).
        """
        if self.disable:
            return

        if total <= 0:
            return

        if self._use_tqdm:
            self._update_tqdm(current, total)
        else:
            self._update_log(current, total)

    def _update_tqdm(self, current: int, total: int) -> None:
        """Update tqdm progress bar.

        Args:
            current: Current bytes downloaded.
            total: Total bytes to download.
        """
        from tqdm import tqdm

        if self._pbar is None:
            self._pbar = tqdm(
                total=total,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                desc=f"Downloading {self.model_name}",
                leave=True,
            )

        # Update progress
        self._pbar.n = current
        self._pbar.refresh()

    def _update_log(self, current: int, total: int) -> None:
        """Update progress via logging.

        Only logs at 10% intervals to avoid spam.

        Args:
            current: Current bytes downloaded.
            total: Total bytes to download.
        """
        if total <= 0:
            return
        percent = int((current / total) * 100)

        # Only log at 10% intervals
        if percent >= self._last_logged_percent + 10:
            self._last_logged_percent = (percent // 10) * 10
            mb_current = current / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            logger.info(
                f"Downloading {self.model_name}: {percent}% ({mb_current:.1f}/{mb_total:.1f} MB)"
            )

    def close(self) -> None:
        """Close and clean up the progress display."""
        if self._pbar is not None:
            self._pbar.close()
            self._pbar = None


def create_hf_progress_callback(model_name: str) -> Callable[[int, int], None] | None:
    """Create a HuggingFace-compatible progress callback.

    This creates a callback that works with huggingface_hub's file download.

    Args:
        model_name: Human-readable name for the model.

    Returns:
        A callback function, or None if progress display is disabled.
    """
    callback = DownloadProgressCallback(model_name)
    return callback


def configure_hf_progress(enabled: bool = True) -> None:
    """Configure HuggingFace Hub progress display.

    This sets environment variables to control HuggingFace's built-in
    progress bars.

    Args:
        enabled: Whether to enable progress display.
    """
    import os

    if enabled:
        # Enable HuggingFace progress bars
        os.environ.pop("HF_HUB_DISABLE_PROGRESS_BARS", None)
    else:
        # Disable HuggingFace progress bars
        os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"


def with_progress(
    model_name: str,
    download_func: Callable[[], Any],
) -> Any:
    """Execute a download function with progress display.

    This is a helper that ensures proper progress display during model
    downloads.

    Args:
        model_name: Human-readable name for the model.
        download_func: Function that downloads/loads the model.

    Returns:
        Result of the download function.

    Example:
        def load_model():
            return Model.from_pretrained("model-id")

        model = with_progress("MyModel", load_model)
    """
    # Configure HuggingFace to show progress
    configure_hf_progress(enabled=True)

    # Log start of download
    logger.info(f"Loading {model_name}... (first run will download the model)")

    try:
        result = download_func()
        logger.info(f"Model {model_name} loaded successfully")
        return result
    except Exception as e:
        logger.error(f"Failed to load {model_name}: {e}")
        raise
