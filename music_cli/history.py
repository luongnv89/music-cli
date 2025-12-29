"""History logging and management for music-cli."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import get_config


@dataclass
class HistoryEntry:
    """A single history entry."""

    timestamp: str
    source: str
    source_type: str
    title: str | None = None
    artist: str | None = None
    mood: str | None = None
    context: str | None = None  # e.g., "morning", "focus", etc.

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "source": self.source,
            "source_type": self.source_type,
            "title": self.title,
            "artist": self.artist,
            "mood": self.mood,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HistoryEntry":
        """Create from dictionary."""
        return cls(
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            source_type=data.get("source_type", "unknown"),
            title=data.get("title"),
            artist=data.get("artist"),
            mood=data.get("mood"),
            context=data.get("context"),
        )

    def display_str(self) -> str:
        """Get a display-friendly string."""
        parts = [self.timestamp]
        if self.title:
            parts.append(self.title)
        elif self.source:
            # Use filename for local files
            if self.source_type == "local":
                parts.append(Path(self.source).name)
            else:
                parts.append(self.source[:50] + "..." if len(self.source) > 50 else self.source)
        if self.artist:
            parts.append(f"by {self.artist}")
        parts.append(f"[{self.source_type}]")
        return " | ".join(parts)


class History:
    """Manages playback history."""

    def __init__(self, history_file: Path | None = None):
        """Initialize history with optional custom file path."""
        if history_file is None:
            history_file = get_config().history_file
        self.history_file = history_file

    def log(
        self,
        source: str,
        source_type: str,
        title: str | None = None,
        artist: str | None = None,
        mood: str | None = None,
        context: str | None = None,
    ) -> HistoryEntry:
        """Log a new history entry."""
        entry = HistoryEntry(
            timestamp=datetime.now().isoformat(),
            source=source,
            source_type=source_type,
            title=title,
            artist=artist,
            mood=mood,
            context=context,
        )

        with self.history_file.open("a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

        return entry

    def get_all(self, limit: int | None = None) -> list[HistoryEntry]:
        """Get all history entries, optionally limited.

        Returns entries in reverse chronological order (newest first).
        """
        entries: list[HistoryEntry] = []

        if not self.history_file.exists():
            return entries

        for line in self.history_file.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                entries.append(HistoryEntry.from_dict(data))
            except json.JSONDecodeError:
                continue

        # Reverse to get newest first
        entries.reverse()

        if limit:
            entries = entries[:limit]

        return entries

    def get_by_index(self, index: int) -> HistoryEntry | None:
        """Get a history entry by its index (1-based, newest first)."""
        entries = self.get_all()
        if 1 <= index <= len(entries):
            return entries[index - 1]
        return None

    def search(self, query: str, limit: int = 20) -> list[HistoryEntry]:
        """Search history entries by title, artist, or source."""
        query = query.lower()
        results = []

        for entry in self.get_all():
            if (
                (entry.title and query in entry.title.lower())
                or (entry.artist and query in entry.artist.lower())
                or (entry.source and query in entry.source.lower())
            ):
                results.append(entry)
                if len(results) >= limit:
                    break

        return results

    def clear(self) -> None:
        """Clear all history."""
        if self.history_file.exists():
            self.history_file.write_text("")

    def get_recent_by_type(self, source_type: str, limit: int = 10) -> list[HistoryEntry]:
        """Get recent entries of a specific source type."""
        results = []
        for entry in self.get_all():
            if entry.source_type == source_type:
                results.append(entry)
                if len(results) >= limit:
                    break
        return results


# Global history instance
_history: History | None = None


def get_history() -> History:
    """Get the global history instance."""
    global _history
    if _history is None:
        _history = History()
    return _history
