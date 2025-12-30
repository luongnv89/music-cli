"""Abstract base player interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class PlayerState(Enum):
    """Player state enumeration."""

    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    LOADING = "loading"
    ERROR = "error"


@dataclass
class TrackInfo:
    """Information about the currently playing track."""

    source: str  # File path or URL
    source_type: str  # "local", "radio", "ai"
    title: str | None = None
    artist: str | None = None
    duration: float | None = None  # Duration in seconds, None for streams
    position: float = 0.0  # Current position in seconds
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "source": self.source,
            "source_type": self.source_type,
            "title": self.title,
            "artist": self.artist,
            "duration": self.duration,
            "position": self.position,
            "metadata": self.metadata,
        }


class Player(ABC):
    """Abstract base class for audio players."""

    def __init__(self):
        self._state = PlayerState.STOPPED
        self._current_track: TrackInfo | None = None
        self._volume = 80
        self._on_track_end: Callable[[], None] | None = None

    @property
    def state(self) -> PlayerState:
        """Get current player state."""
        return self._state

    @property
    def current_track(self) -> TrackInfo | None:
        """Get info about the currently playing track."""
        return self._current_track

    @property
    def volume(self) -> int:
        """Get current volume (0-100)."""
        return self._volume

    def set_on_track_end(self, callback: Callable[[], None] | None) -> None:
        """Set callback for when track ends."""
        self._on_track_end = callback

    @abstractmethod
    async def play(self, track: TrackInfo, loop: bool = False) -> bool:
        """Start playing a track. Returns True if successful.

        Args:
            track: Track information to play
            loop: If True, loop the track indefinitely
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop playback."""
        pass

    @abstractmethod
    async def pause(self) -> None:
        """Pause playback."""
        pass

    @abstractmethod
    async def resume(self) -> None:
        """Resume playback."""
        pass

    @abstractmethod
    async def set_volume(self, volume: int) -> None:
        """Set volume (0-100)."""
        pass

    @abstractmethod
    async def get_position(self) -> float:
        """Get current playback position in seconds."""
        pass

    def get_status(self) -> dict:
        """Get current player status as a dictionary."""
        return {
            "state": self._state.value,
            "volume": self._volume,
            "track": self._current_track.to_dict() if self._current_track else None,
        }
