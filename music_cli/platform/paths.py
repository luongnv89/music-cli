"""Cross-platform path resolution for config directories.

This module provides platform-specific paths for:
- Configuration directory
- Socket/IPC address
- PID file location
- AI music storage

Unix systems (Linux/macOS): Uses ~/.config/music-cli/
Windows: Uses %LOCALAPPDATA%\\music-cli\\
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path


class PathProvider(ABC):
    """Abstract interface for platform-specific paths.

    Each platform implements this to provide appropriate
    directories for configuration and data storage.
    """

    @abstractmethod
    def get_config_dir(self) -> Path:
        """Get the config directory for music-cli.

        Returns:
            Path to the config directory.
        """

    @abstractmethod
    def get_socket_path(self, config_dir: Path) -> Path:
        """Get the Unix socket path.

        On Windows, this returns a dummy path since TCP is used instead.

        Args:
            config_dir: The config directory.

        Returns:
            Path to the socket file.
        """

    def get_pid_file(self, config_dir: Path) -> Path:
        """Get PID file path.

        Args:
            config_dir: The config directory.

        Returns:
            Path to the PID file.
        """
        return config_dir / "music-cli.pid"

    def get_ai_music_dir(self, config_dir: Path) -> Path:
        """Get AI-generated music directory.

        Args:
            config_dir: The config directory.

        Returns:
            Path to the AI music directory.
        """
        return config_dir / "ai_music"

    def get_history_file(self, config_dir: Path) -> Path:
        """Get playback history file path."""
        return config_dir / "history.jsonl"

    def get_youtube_cache_dir(self, config_dir: Path) -> Path:
        """Get YouTube cache directory for offline audio storage."""
        return config_dir / "youtube_cache"


class UnixPathProvider(PathProvider):
    """Path provider for Unix-like systems (Linux, macOS).

    Uses XDG-compliant paths with ~/.config/music-cli/ as the default.
    Respects $XDG_CONFIG_HOME if set.
    """

    def get_config_dir(self) -> Path:
        """Get XDG-compliant config directory.

        Returns:
            ~/.config/music-cli/ or $XDG_CONFIG_HOME/music-cli/
        """
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            return Path(xdg_config) / "music-cli"
        return Path.home() / ".config" / "music-cli"

    def get_socket_path(self, config_dir: Path) -> Path:
        """Get Unix socket file path.

        Args:
            config_dir: The config directory.

        Returns:
            Path to music-cli.sock
        """
        return config_dir / "music-cli.sock"


class WindowsPathProvider(PathProvider):
    """Path provider for Windows.

    Uses %LOCALAPPDATA%\\music-cli\\ for local data storage.
    This is the standard location for application data on Windows.
    """

    def get_config_dir(self) -> Path:
        """Get Windows-appropriate config directory.

        Returns:
            %LOCALAPPDATA%\\music-cli\\
        """
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "music-cli"
        # Fallback if LOCALAPPDATA is not set (unlikely on Windows)
        return Path.home() / "AppData" / "Local" / "music-cli"

    def get_socket_path(self, config_dir: Path) -> Path:
        """Get socket path (not used on Windows, TCP is used instead).

        Args:
            config_dir: The config directory.

        Returns:
            Dummy path (not used for actual connection).
        """
        # Windows uses TCP instead of Unix sockets
        # This path is only used for display/config purposes
        return config_dir / "music-cli.sock"


__all__ = [
    "PathProvider",
    "UnixPathProvider",
    "WindowsPathProvider",
]
