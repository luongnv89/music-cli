import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class YouTubeHistoryEntry:
    video_id: str
    url: str
    title: str
    artist: str | None = None
    duration: float | None = None
    timestamp: str | None = None

    def to_dict(self) -> dict:
        return {
            "video_id": self.video_id,
            "url": self.url,
            "title": self.title,
            "artist": self.artist,
            "duration": self.duration,
            "timestamp": self.timestamp or datetime.now().isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "YouTubeHistoryEntry":
        return cls(
            video_id=data.get("video_id", ""),
            url=data.get("url", ""),
            title=data.get("title", "Unknown"),
            artist=data.get("artist"),
            duration=data.get("duration"),
            timestamp=data.get("timestamp"),
        )


class YouTubeHistory:
    def __init__(self, history_file: Path):
        self.history_file = history_file
        self._entries: list[YouTubeHistoryEntry] = []
        self._load()

    def _load(self) -> None:
        if not self.history_file.exists():
            self._entries = []
            return

        try:
            data = json.loads(self.history_file.read_text())
            if isinstance(data, list):
                self._entries = [YouTubeHistoryEntry.from_dict(e) for e in data]
            else:
                self._entries = []
        except (json.JSONDecodeError, OSError):
            self._entries = []

    def _save(self) -> None:
        try:
            data = [e.to_dict() for e in self._entries]
            self.history_file.write_text(json.dumps(data, indent=2))
        except OSError as e:
            logger.warning(f"Failed to save YouTube history: {e}")

    def get_all(self, limit: int | None = None) -> list[YouTubeHistoryEntry]:
        if limit:
            return self._entries[:limit]
        return self._entries

    def get_by_index(self, index: int) -> YouTubeHistoryEntry | None:
        if 1 <= index <= len(self._entries):
            return self._entries[index - 1]
        return None

    def remove_by_index(self, index: int) -> YouTubeHistoryEntry | None:
        if 1 <= index <= len(self._entries):
            removed = self._entries.pop(index - 1)
            self._save()
            return removed
        return None

    def clear(self) -> None:
        self._entries = []
        self._save()

    def count(self) -> int:
        return len(self._entries)

    def add_entry(
        self,
        video_id: str,
        url: str,
        title: str,
        artist: str | None = None,
        duration: float | None = None,
        max_entries: int = 1000,
    ) -> YouTubeHistoryEntry:
        self._entries = [e for e in self._entries if e.video_id != video_id]

        entry = YouTubeHistoryEntry(
            video_id=video_id,
            url=url,
            title=title,
            artist=artist,
            duration=duration,
            timestamp=datetime.now().isoformat(),
        )
        self._entries.insert(0, entry)

        if len(self._entries) > max_entries:
            self._entries = self._entries[:max_entries]

        self._save()
        return entry


_youtube_history: YouTubeHistory | None = None


def get_youtube_history() -> YouTubeHistory:
    global _youtube_history
    if _youtube_history is None:
        from .config import get_config

        config = get_config()
        _youtube_history = YouTubeHistory(config.youtube_cache_file)
    return _youtube_history
