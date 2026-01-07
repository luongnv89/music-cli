"""Platform abstraction layer for cross-platform support.

This module provides a clean abstraction for platform-specific operations,
enabling music-cli to run on Windows, macOS, and Linux.

Key Components:
- Platform detection and factory functions
- IPC abstraction (Unix sockets vs TCP)
- Player control abstraction (signals vs stdin)
- Path provider abstraction (config directories)
- Media controller abstraction (MPRIS, macOS Now Playing, Windows SMTC)
"""

from __future__ import annotations

import logging
import sys
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ipc import IPCClient, IPCServer
    from .media_controller import MediaController
    from .paths import PathProvider
    from .player_control import PlayerController

logger = logging.getLogger(__name__)


class Platform(Enum):
    """Supported platforms."""

    LINUX = "linux"
    DARWIN = "darwin"
    WINDOWS = "windows"


def get_platform() -> Platform:
    """Detect the current platform.

    Returns:
        Platform enum value for the current OS.

    Raises:
        RuntimeError: If running on an unsupported platform.
    """
    if sys.platform.startswith("linux"):
        return Platform.LINUX
    elif sys.platform == "darwin":
        return Platform.DARWIN
    elif sys.platform == "win32":
        return Platform.WINDOWS
    raise RuntimeError(f"Unsupported platform: {sys.platform}")


def is_windows() -> bool:
    """Check if running on Windows.

    Returns:
        True if running on Windows, False otherwise.
    """
    return get_platform() == Platform.WINDOWS


def is_unix() -> bool:
    """Check if running on a Unix-like system (Linux or macOS).

    Returns:
        True if running on Linux or macOS, False otherwise.
    """
    return get_platform() in (Platform.LINUX, Platform.DARWIN)


def get_ipc_server() -> IPCServer:
    """Factory: Get platform-appropriate IPC server.

    Returns:
        UnixIPCServer on Linux/macOS, TCPIPCServer on Windows.
    """
    from .ipc import TCPIPCServer, UnixIPCServer

    if is_unix():
        return UnixIPCServer()
    return TCPIPCServer()


def get_ipc_client() -> IPCClient:
    """Factory: Get platform-appropriate IPC client.

    Returns:
        UnixIPCClient on Linux/macOS, TCPIPCClient on Windows.
    """
    from .ipc import TCPIPCClient, UnixIPCClient

    if is_unix():
        return UnixIPCClient()
    return TCPIPCClient()


def get_player_controller() -> PlayerController:
    """Factory: Get platform-appropriate player controller.

    Returns:
        SignalPlayerController on Linux/macOS, StdinPlayerController on Windows.
    """
    from .player_control import SignalPlayerController, StdinPlayerController

    if is_unix():
        return SignalPlayerController()
    return StdinPlayerController()


def get_path_provider() -> PathProvider:
    """Factory: Get platform-appropriate path provider.

    Returns:
        UnixPathProvider on Linux/macOS, WindowsPathProvider on Windows.
    """
    from .paths import UnixPathProvider, WindowsPathProvider

    if is_unix():
        return UnixPathProvider()
    return WindowsPathProvider()


def supports_unix_signals() -> bool:
    """Check if platform supports Unix signals (SIGSTOP, SIGCONT, etc.).

    Returns:
        True on Linux/macOS, False on Windows.
    """
    return is_unix()


def get_media_controller() -> MediaController:
    """Factory: Get platform-appropriate media controller.

    Returns platform-specific media controller for OS integration:
    - macOS: Disabled (ffplay owns audio session, not music-cli)
    - Linux: LinuxMediaController (MPRIS D-Bus interface)
    - Windows: WindowsMediaController (SystemMediaTransportControls)
    - Fallback: NoOpMediaController if platform libraries unavailable

    The media controller allows music-cli to:
    - Respond to media keys (play/pause/next from headphones/keyboards)
    - Display track metadata in OS media UI (lock screen, control center)

    Note: macOS media controller is disabled because ffplay (external subprocess)
    owns the audio session, so macOS ignores our Now Playing updates. The NSRunLoop
    polling also causes audio quality issues due to event loop interference.

    Returns:
        Platform-appropriate MediaController instance.
    """
    from .media_controller import NoOpMediaController

    platform = get_platform()

    # macOS: Disabled - ffplay owns the audio session so macOS ignores our
    # Now Playing updates. The NSRunLoop polling also degrades audio quality.
    if platform == Platform.DARWIN:
        logger.debug("macOS media controller disabled (ffplay owns audio session)")
        return NoOpMediaController()

    try:
        if platform == Platform.LINUX:
            from .media_controller_linux import LinuxMediaController

            controller = LinuxMediaController()
            if controller.is_available:
                return controller
            logger.info("D-Bus not available. Install with: pip install dbus-next")

        elif platform == Platform.WINDOWS:
            from .media_controller_windows import WindowsMediaController

            controller = WindowsMediaController()
            if controller.is_available:
                return controller
            logger.info(
                "Windows Runtime not available. "
                "Install with: pip install winrt-Windows.Media.Playback"
            )

    except ImportError as e:
        logger.debug(f"Media controller import failed: {e}")
    except Exception as e:
        logger.warning(f"Media controller initialization failed: {e}")

    # Fallback to no-op controller
    return NoOpMediaController()


__all__ = [
    "Platform",
    "get_platform",
    "is_windows",
    "is_unix",
    "get_ipc_server",
    "get_ipc_client",
    "get_player_controller",
    "get_path_provider",
    "get_media_controller",
    "supports_unix_signals",
]
