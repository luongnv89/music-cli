"""Tests for history module."""

import json
import time
from pathlib import Path

from music_cli.config import Config
from music_cli.history import History, HistoryEntry


class TestHistoryEntry:
    """Tests for HistoryEntry class."""

    def test_to_dict(self) -> None:
        """Test converting entry to dictionary."""
        entry = HistoryEntry(
            timestamp="2024-01-15T12:00:00",
            source="/path/to/song.mp3",
            source_type="local",
            title="Test Song",
            artist="Test Artist",
        )

        d = entry.to_dict()

        assert d["timestamp"] == "2024-01-15T12:00:00"
        assert d["source"] == "/path/to/song.mp3"
        assert d["source_type"] == "local"
        assert d["title"] == "Test Song"
        assert d["artist"] == "Test Artist"

    def test_from_dict(self) -> None:
        """Test creating entry from dictionary."""
        data = {
            "timestamp": "2024-01-15T12:00:00",
            "source": "/path/to/song.mp3",
            "source_type": "local",
            "title": "Test Song",
        }

        entry = HistoryEntry.from_dict(data)

        assert entry.timestamp == "2024-01-15T12:00:00"
        assert entry.source == "/path/to/song.mp3"
        assert entry.source_type == "local"
        assert entry.title == "Test Song"

    def test_display_str(self) -> None:
        """Test display string generation."""
        entry = HistoryEntry(
            timestamp="2024-01-15T12:00:00",
            source="/path/to/song.mp3",
            source_type="local",
            title="Test Song",
            artist="Test Artist",
        )

        display = entry.display_str()

        assert "2024-01-15" in display
        assert "Test Song" in display
        assert "local" in display


class TestHistory:
    """Tests for History class."""

    def test_log_entry(self, tmp_path: Path) -> None:
        """Test logging a history entry."""
        history_file = tmp_path / "history.jsonl"
        history = History(history_file=history_file)

        entry = history.log(
            HistoryEntry(source="/path/to/song.mp3", source_type="local", title="Test Song")
        )

        assert entry.source == "/path/to/song.mp3"
        assert entry.title == "Test Song"
        assert history_file.exists()

    def test_log_stamps_timestamp_when_entry_has_none(self, tmp_path: Path) -> None:
        """Entries built without a timestamp get one at construction."""
        history_file = tmp_path / "history.jsonl"
        history = History(history_file=history_file)

        entry = HistoryEntry(source="a.mp3", source_type="local")
        assert entry.timestamp  # default_factory stamped it
        assert history.log(entry).timestamp == entry.timestamp

    def test_get_all(self, tmp_path: Path) -> None:
        """Test getting all history entries."""
        history_file = tmp_path / "history.jsonl"
        history = History(history_file=history_file)

        # Log some entries
        history.log(HistoryEntry(source="song1.mp3", source_type="local", title="Song 1"))
        history.log(HistoryEntry(source="song2.mp3", source_type="local", title="Song 2"))
        history.log(HistoryEntry(source="song3.mp3", source_type="local", title="Song 3"))

        entries = history.get_all()

        # Newest first
        assert len(entries) == 3
        assert entries[0].title == "Song 3"
        assert entries[2].title == "Song 1"

    def test_get_all_with_limit(self, tmp_path: Path) -> None:
        """Test getting limited history entries."""
        history_file = tmp_path / "history.jsonl"
        history = History(history_file=history_file)

        for i in range(10):
            history.log(HistoryEntry(source=f"song{i}.mp3", source_type="local", title=f"Song {i}"))

        entries = history.get_all(limit=5)

        assert len(entries) == 5

    def test_get_by_index(self, tmp_path: Path) -> None:
        """Test getting history entry by index."""
        history_file = tmp_path / "history.jsonl"
        history = History(history_file=history_file)

        history.log(HistoryEntry(source="song1.mp3", source_type="local", title="Song 1"))
        history.log(HistoryEntry(source="song2.mp3", source_type="local", title="Song 2"))

        entry = history.get_by_index(1)  # Most recent
        assert entry is not None
        assert entry.title == "Song 2"

        entry = history.get_by_index(2)  # Second most recent
        assert entry is not None
        assert entry.title == "Song 1"

    def test_get_by_index_invalid(self, tmp_path: Path) -> None:
        """Test getting entry with invalid index."""
        history_file = tmp_path / "history.jsonl"
        history = History(history_file=history_file)

        history.log(HistoryEntry(source="song1.mp3", source_type="local", title="Song 1"))

        assert history.get_by_index(0) is None
        assert history.get_by_index(99) is None

    def test_log_enforces_cap(self, tmp_path: Path) -> None:
        """Logging past max_entries rotates the oldest entries out."""
        history_file = tmp_path / "history.jsonl"
        history = History(history_file=history_file, max_entries=3)

        for i in range(5):
            history.log(HistoryEntry(source=f"song{i}.mp3", source_type="local", title=f"Song {i}"))

        entries = history.get_all()

        assert len(entries) == 3
        # Newest kept, oldest rotated out.
        assert entries[0].title == "Song 4"
        assert entries[-1].title == "Song 2"

    def test_log_under_cap_keeps_everything(self, tmp_path: Path) -> None:
        """Logging below the cap never rewrites the file."""
        history_file = tmp_path / "history.jsonl"
        history = History(history_file=history_file, max_entries=10)

        for i in range(4):
            history.log(HistoryEntry(source=f"song{i}.mp3", source_type="local", title=f"Song {i}"))

        assert len(history.get_all()) == 4

    def test_trim_drops_malformed_lines(self, tmp_path: Path) -> None:
        """Rotation keeps only valid JSON lines, like get_all."""
        history_file = tmp_path / "history.jsonl"
        history = History(history_file=history_file, max_entries=2)

        history.log(HistoryEntry(source="a.mp3", source_type="local", title="A"))
        with history_file.open("a") as f:
            f.write("{corrupt\n")
        history.log(HistoryEntry(source="b.mp3", source_type="local", title="B"))
        history.log(HistoryEntry(source="c.mp3", source_type="local", title="C"))

        entries = history.get_all()

        assert len(entries) == 2
        assert [e.title for e in entries] == ["C", "B"]
        assert not history_file.with_name("history.jsonl.tmp").exists()

    def test_get_by_index_across_chunk_boundary(self, tmp_path: Path) -> None:
        """Backward reads stay correct when lines span chunk boundaries."""
        history_file = tmp_path / "history.jsonl"
        history = History(history_file=history_file)

        # Long titles push the newest entries across the 8 KiB read chunk.
        big_title = "X" * 400
        total = 60
        for i in range(total):
            history.log(
                HistoryEntry(
                    source=f"song{i}.mp3",
                    source_type="local",
                    title=f"{i} {big_title}",
                )
            )

        entry = history.get_by_index(1)
        assert entry is not None
        assert entry.title.startswith("59 ")
        entry = history.get_by_index(37)
        assert entry is not None
        assert entry.title.startswith(f"{total - 37} ")

    def test_get_by_index_skips_malformed_tail(self, tmp_path: Path) -> None:
        """Malformed trailing lines are skipped, matching get_all."""
        history_file = tmp_path / "history.jsonl"
        history = History(history_file=history_file)

        history.log(HistoryEntry(source="song1.mp3", source_type="local", title="Song 1"))
        history.log(HistoryEntry(source="song2.mp3", source_type="local", title="Song 2"))
        with history_file.open("a") as f:
            f.write("{truncated\n")

        entry = history.get_by_index(1)
        assert entry is not None
        assert entry.title == "Song 2"

    def test_default_config_caps_history(self) -> None:
        """The default config ships a cap matching youtube_history's bound."""
        assert Config.DEFAULT_CONFIG["history"]["max_entries"] == 1000

    def test_get_by_index_benchmark_50k_entries(self, tmp_path: Path) -> None:
        """Benchmark: get_by_index(1) stays under 5 ms on 50k entries (F-PERF-002)."""
        history_file = tmp_path / "history.jsonl"
        total = 50_000
        lines = [
            json.dumps(
                {
                    "timestamp": f"2024-01-01T00:00:{i % 60:02d}",
                    "source": f"/music/song{i}.mp3",
                    "source_type": "local",
                    "title": f"Song {i}",
                    "artist": None,
                    "mood": None,
                    "context": None,
                }
            )
            for i in range(total)
        ]
        history_file.write_text("\n".join(lines) + "\n")
        history = History(history_file=history_file)

        start = time.perf_counter()
        entry = history.get_by_index(1)
        elapsed = time.perf_counter() - start

        assert entry is not None
        assert entry.title == f"Song {total - 1}"
        assert elapsed <= 0.005, f"get_by_index(1) took {elapsed * 1000:.2f} ms (> 5 ms)"

    def test_search(self, tmp_path: Path) -> None:
        """Test searching history."""
        history_file = tmp_path / "history.jsonl"
        history = History(history_file=history_file)

        history.log(HistoryEntry(source="song1.mp3", source_type="local", title="Rock Song"))
        history.log(HistoryEntry(source="song2.mp3", source_type="local", title="Pop Song"))
        history.log(HistoryEntry(source="song3.mp3", source_type="local", title="Rock Ballad"))

        results = history.search("rock")

        assert len(results) == 2
        assert all("rock" in r.title.lower() for r in results)

    def test_clear(self, tmp_path: Path) -> None:
        """Test clearing history."""
        history_file = tmp_path / "history.jsonl"
        history = History(history_file=history_file)

        history.log(HistoryEntry(source="song1.mp3", source_type="local", title="Song 1"))
        history.log(HistoryEntry(source="song2.mp3", source_type="local", title="Song 2"))

        history.clear()

        assert len(history.get_all()) == 0
