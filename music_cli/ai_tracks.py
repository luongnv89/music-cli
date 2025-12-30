"""AI track management for music-cli."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import get_config

logger = logging.getLogger(__name__)


@dataclass
class AITrack:
    """A single AI-generated track entry."""

    prompt: str
    file_path: str
    timestamp: str
    duration: int
    model: str = "musicgen-small"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "prompt": self.prompt,
            "file_path": self.file_path,
            "timestamp": self.timestamp,
            "duration": self.duration,
            "model": self.model,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AITrack":
        """Create from dictionary."""
        return cls(
            prompt=data.get("prompt", ""),
            file_path=data.get("file_path", ""),
            timestamp=data.get("timestamp", ""),
            duration=data.get("duration", 30),
            model=data.get("model", "musicgen-small"),
        )

    def file_exists(self) -> bool:
        """Check if the audio file still exists."""
        return Path(self.file_path).exists()

    def display_prompt(self, max_length: int = 50) -> str:
        """Get a truncated prompt for display."""
        if len(self.prompt) <= max_length:
            return self.prompt
        return self.prompt[: max_length - 3] + "..."


class AITracksManager:
    """Manages AI-generated tracks storage and retrieval."""

    def __init__(self, tracks_file: Path | None = None):
        """Initialize AI tracks manager.

        Args:
            tracks_file: Path to the ai_tracks.json file.
                        Defaults to config directory.
        """
        if tracks_file is None:
            tracks_file = get_config().ai_tracks_file
        self.tracks_file = tracks_file
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Create the tracks file if it doesn't exist."""
        if not self.tracks_file.exists():
            self.tracks_file.write_text("[]")

    def _load_tracks(self) -> list[AITrack]:
        """Load tracks from JSON file."""
        try:
            data = json.loads(self.tracks_file.read_text())
            return [AITrack.from_dict(item) for item in data]
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load AI tracks: {e}")
            return []

    def _save_tracks(self, tracks: list[AITrack]) -> None:
        """Save tracks to JSON file."""
        data = [track.to_dict() for track in tracks]
        self.tracks_file.write_text(json.dumps(data, indent=2))

    def get_all(self) -> list[AITrack]:
        """Get all AI tracks.

        Returns tracks in reverse chronological order (newest first).
        """
        tracks = self._load_tracks()
        tracks.reverse()
        return tracks

    def add_track(
        self,
        prompt: str,
        file_path: str,
        duration: int,
        model: str = "musicgen-small",
    ) -> AITrack:
        """Add a new AI track.

        Args:
            prompt: The prompt used for generation.
            file_path: Path to the generated audio file.
            duration: Duration in seconds.
            model: Model name used for generation.

        Returns:
            The newly created AITrack.
        """
        track = AITrack(
            prompt=prompt,
            file_path=file_path,
            timestamp=datetime.now().isoformat(),
            duration=duration,
            model=model,
        )

        tracks = self._load_tracks()
        tracks.append(track)
        self._save_tracks(tracks)

        return track

    def get_by_index(self, index: int) -> AITrack | None:
        """Get a track by its 1-based index (newest first).

        Args:
            index: 1-based index of the track.

        Returns:
            AITrack if found, None otherwise.
        """
        tracks = self.get_all()
        if 1 <= index <= len(tracks):
            return tracks[index - 1]
        return None

    def remove_by_index(self, index: int) -> AITrack | None:
        """Remove a track by its 1-based index (newest first).

        Also deletes the associated audio file.

        Args:
            index: 1-based index of the track.

        Returns:
            The removed AITrack if found, None otherwise.
        """
        tracks = self.get_all()
        if not (1 <= index <= len(tracks)):
            return None

        removed = tracks[index - 1]

        # Delete the audio file if it exists
        file_path = Path(removed.file_path)
        if file_path.exists():
            try:
                file_path.unlink()
                logger.info(f"Deleted audio file: {file_path}")
            except OSError as e:
                logger.warning(f"Failed to delete audio file: {e}")

        # Remove from list and save
        # Note: tracks is reversed, so we need to work with original order
        original_tracks = self._load_tracks()
        # Index in original order (0-based from end)
        original_index = len(original_tracks) - index
        del original_tracks[original_index]
        self._save_tracks(original_tracks)

        return removed

    def update_file_path(self, index: int, new_file_path: str) -> bool:
        """Update the file path for a track (used after regeneration).

        Args:
            index: 1-based index of the track.
            new_file_path: New path to the audio file.

        Returns:
            True if updated, False if track not found.
        """
        tracks = self._load_tracks()
        # Convert to reversed index
        reversed_index = len(tracks) - index
        if not (0 <= reversed_index < len(tracks)):
            return False

        tracks[reversed_index].file_path = new_file_path
        tracks[reversed_index].timestamp = datetime.now().isoformat()
        self._save_tracks(tracks)
        return True

    def count(self) -> int:
        """Get the total number of AI tracks."""
        return len(self._load_tracks())


# Global AI tracks manager instance
_ai_tracks: AITracksManager | None = None


def get_ai_tracks() -> AITracksManager:
    """Get the global AI tracks manager instance."""
    global _ai_tracks
    if _ai_tracks is None:
        _ai_tracks = AITracksManager()
    return _ai_tracks
