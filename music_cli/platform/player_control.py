"""Player control abstraction for pause/resume operations.

This module provides platform-specific implementations for controlling
the ffplay process:

On Unix systems (Linux/macOS): Uses SIGSTOP/SIGCONT signals
On Windows: Uses stdin commands ('p' key) since signals aren't available
"""

from __future__ import annotations

import asyncio
import logging
import signal
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class PlayerController(ABC):
    """Abstract interface for controlling player process.

    Provides a unified interface for pause/resume operations
    regardless of the underlying mechanism.
    """

    @abstractmethod
    async def pause(self, process: asyncio.subprocess.Process) -> bool:
        """Pause the player process.

        Args:
            process: The ffplay subprocess to pause.

        Returns:
            True if pause succeeded, False otherwise.
        """

    @abstractmethod
    async def resume(self, process: asyncio.subprocess.Process) -> bool:
        """Resume the player process.

        Args:
            process: The ffplay subprocess to resume.

        Returns:
            True if resume succeeded, False otherwise.
        """

    def reset(self) -> None:  # noqa: B027
        """Reset controller state (called when starting new playback).

        Override in subclasses that maintain state.
        Default implementation does nothing.
        """


class SignalPlayerController(PlayerController):
    """Unix signal-based player control using SIGSTOP/SIGCONT.

    This is the most efficient pause/resume mechanism on Unix systems.
    The kernel immediately suspends/resumes the process without any
    communication overhead.
    """

    async def pause(self, process: asyncio.subprocess.Process) -> bool:
        """Pause via SIGSTOP signal.

        Args:
            process: The ffplay subprocess to pause.

        Returns:
            True if signal was sent successfully, False otherwise.
        """
        if process is None or process.returncode is not None:
            return False

        try:
            process.send_signal(signal.SIGSTOP)
            logger.debug("Sent SIGSTOP to player")
            return True
        except ProcessLookupError:
            logger.warning("Process not found when pausing")
            return False
        except OSError as e:
            logger.warning(f"Failed to pause: {e}")
            return False

    async def resume(self, process: asyncio.subprocess.Process) -> bool:
        """Resume via SIGCONT signal.

        Args:
            process: The ffplay subprocess to resume.

        Returns:
            True if signal was sent successfully, False otherwise.
        """
        if process is None or process.returncode is not None:
            return False

        try:
            process.send_signal(signal.SIGCONT)
            logger.debug("Sent SIGCONT to player")
            return True
        except ProcessLookupError:
            logger.warning("Process not found when resuming")
            return False
        except OSError as e:
            logger.warning(f"Failed to resume: {e}")
            return False


class StdinPlayerController(PlayerController):
    """Stdin-based player control for Windows.

    Uses ffplay's keyboard command interface. The 'p' key toggles
    pause/play state. This requires ffplay to be started with
    stdin=PIPE.

    Note: This approach has slightly higher latency than signals
    (~50-100ms) due to stdin buffering and ffplay processing time.
    """

    def __init__(self) -> None:
        self._is_paused = False

    async def pause(self, process: asyncio.subprocess.Process) -> bool:
        """Pause via stdin 'p' command.

        Args:
            process: The ffplay subprocess to pause (must have stdin=PIPE).

        Returns:
            True if command was sent successfully, False otherwise.
        """
        if process is None or process.returncode is not None:
            return False

        if process.stdin is None:
            logger.warning("Process stdin not available for pause")
            return False

        if self._is_paused:
            # Already paused
            return True

        try:
            # ffplay uses 'p' or space to toggle pause
            process.stdin.write(b"p")
            await process.stdin.drain()
            self._is_paused = True
            logger.debug("Sent 'p' command to player stdin")
            return True
        except (BrokenPipeError, OSError, ConnectionResetError) as e:
            logger.warning(f"Failed to pause via stdin: {e}")
            return False

    async def resume(self, process: asyncio.subprocess.Process) -> bool:
        """Resume via stdin 'p' command (toggle).

        Args:
            process: The ffplay subprocess to resume (must have stdin=PIPE).

        Returns:
            True if command was sent successfully, False otherwise.
        """
        if process is None or process.returncode is not None:
            return False

        if process.stdin is None:
            logger.warning("Process stdin not available for resume")
            return False

        if not self._is_paused:
            # Not paused, nothing to do
            return True

        try:
            # ffplay uses 'p' or space to toggle pause
            process.stdin.write(b"p")
            await process.stdin.drain()
            self._is_paused = False
            logger.debug("Sent 'p' command to player stdin")
            return True
        except (BrokenPipeError, OSError, ConnectionResetError) as e:
            logger.warning(f"Failed to resume via stdin: {e}")
            return False

    def reset(self) -> None:
        """Reset pause state when starting new playback."""
        self._is_paused = False


__all__ = [
    "PlayerController",
    "SignalPlayerController",
    "StdinPlayerController",
]
