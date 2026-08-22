"""History logging and management for music-cli."""

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .config import DEFAULT_HISTORY_MAX_ENTRIES, get_config

# Backward reads for get_by_index work in chunks of this many bytes.
_TAIL_CHUNK_SIZE = 8192
# Above this index, get_by_index falls back to a full parse of the file.
_TAIL_MAX_INDEX = 128


@dataclass
class HistoryEntry:
    """A single history entry."""

    # Stamped at construction when omitted so callers can build an entry
    # directly and hand it to History.log (F-CLEAN-011 dataclass params).
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = ""
    source_type: str = "unknown"
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

    def __init__(
        self,
        history_file: Path | None = None,
        max_entries: int = DEFAULT_HISTORY_MAX_ENTRIES,
    ):
        """Initialize history with optional custom file path and entry cap.

        The cap keeps the JSONL file bounded: once ``max_entries`` entries are
        present, logging a new entry rotates the oldest lines out (F-PERF-002).
        """
        if history_file is None:
            history_file = get_config().history_file
        self.history_file = history_file
        self.max_entries = max(1, int(max_entries))

    def log(self, entry: HistoryEntry) -> HistoryEntry:
        """Append a history entry to the history file, enforcing the cap."""
        with self.history_file.open("a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

        self._trim_to_cap()

        return entry

    def _trim_to_cap(self) -> None:
        """Rotate out the oldest entries so at most ``max_entries`` remain."""
        if not self.history_file.exists():
            return

        # Cheap line count first; only pay for a rewrite when over the cap.
        with self.history_file.open("rb") as f:
            line_count = sum(1 for _ in f)
        if line_count <= self.max_entries:
            return

        valid_lines: list[str] = []
        for raw in self.history_file.read_text().splitlines():
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                json.loads(stripped)
            except json.JSONDecodeError:
                continue
            valid_lines.append(stripped)

        keep = valid_lines[-self.max_entries :]
        tmp_file = self.history_file.with_name(self.history_file.name + ".tmp")
        tmp_file.write_text("".join(line + "\n" for line in keep))
        tmp_file.replace(self.history_file)

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
        if index < 1:
            return None

        # Fast path for small indexes: parse only the tail of the file
        # instead of reading it whole (F-PERF-002).
        if index <= _TAIL_MAX_INDEX:
            entries = self._tail_entries(index)
            return entries[-1] if len(entries) >= index else None

        entries = self.get_all()
        if index <= len(entries):
            return entries[index - 1]
        return None

    def _tail_entries(self, count: int) -> list[HistoryEntry]:
        """Read up to ``count`` valid entries from the end of the file.

        Returns them newest-first without parsing the whole file. Skips
        blank and malformed lines, matching :meth:`get_all` semantics.
        """
        entries: list[HistoryEntry] = []
        for raw in self._iter_lines_reverse():
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                entries.append(HistoryEntry.from_dict(data))
            except json.JSONDecodeError:
                continue
            if len(entries) >= count:
                break
        return entries

    def _iter_lines_reverse(self) -> Iterator[bytes]:
        """Yield raw lines from the newest (last) to the oldest (first).

        Reads the file backwards in fixed-size chunks so the cost of a read
        is proportional to what is consumed from the end.
        """
        if not self.history_file.exists():
            return

        with self.history_file.open("rb") as f:
            pos = f.seek(0, os.SEEK_END)
            remainder = b""
            while pos > 0:
                chunk_size = min(_TAIL_CHUNK_SIZE, pos)
                pos -= chunk_size
                f.seek(pos)
                data = f.read(chunk_size) + remainder
                lines = data.split(b"\n")
                remainder = lines[0]
                yield from reversed(lines[1:])
            if remainder.strip():
                yield remainder

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
        max_entries = _configured_max_entries()
        _history = History(max_entries=max_entries)
    return _history


def _configured_max_entries() -> int:
    """Resolve the configured history cap, falling back to the default."""
    config = get_config()
    raw = config.get("history.max_entries", DEFAULT_HISTORY_MAX_ENTRIES)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_HISTORY_MAX_ENTRIES
    return value if value >= 1 else DEFAULT_HISTORY_MAX_ENTRIES
