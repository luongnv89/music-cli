"""Tests for history module."""

from pathlib import Path

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
            source="/path/to/song.mp3",
            source_type="local",
            title="Test Song",
        )

        assert entry.source == "/path/to/song.mp3"
        assert entry.title == "Test Song"
        assert history_file.exists()

    def test_get_all(self, tmp_path: Path) -> None:
        """Test getting all history entries."""
        history_file = tmp_path / "history.jsonl"
        history = History(history_file=history_file)

        # Log some entries
        history.log(source="song1.mp3", source_type="local", title="Song 1")
        history.log(source="song2.mp3", source_type="local", title="Song 2")
        history.log(source="song3.mp3", source_type="local", title="Song 3")

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
            history.log(source=f"song{i}.mp3", source_type="local", title=f"Song {i}")

        entries = history.get_all(limit=5)

        assert len(entries) == 5

    def test_get_by_index(self, tmp_path: Path) -> None:
        """Test getting history entry by index."""
        history_file = tmp_path / "history.jsonl"
        history = History(history_file=history_file)

        history.log(source="song1.mp3", source_type="local", title="Song 1")
        history.log(source="song2.mp3", source_type="local", title="Song 2")

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

        history.log(source="song1.mp3", source_type="local", title="Song 1")

        assert history.get_by_index(0) is None
        assert history.get_by_index(99) is None

    def test_search(self, tmp_path: Path) -> None:
        """Test searching history."""
        history_file = tmp_path / "history.jsonl"
        history = History(history_file=history_file)

        history.log(source="song1.mp3", source_type="local", title="Rock Song")
        history.log(source="song2.mp3", source_type="local", title="Pop Song")
        history.log(source="song3.mp3", source_type="local", title="Rock Ballad")

        results = history.search("rock")

        assert len(results) == 2
        assert all("rock" in r.title.lower() for r in results)

    def test_clear(self, tmp_path: Path) -> None:
        """Test clearing history."""
        history_file = tmp_path / "history.jsonl"
        history = History(history_file=history_file)

        history.log(source="song1.mp3", source_type="local", title="Song 1")
        history.log(source="song2.mp3", source_type="local", title="Song 2")

        history.clear()

        assert len(history.get_all()) == 0
