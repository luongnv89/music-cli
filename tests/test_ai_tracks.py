"""Tests for AI tracks management."""

import json
import tempfile
from pathlib import Path

import pytest

from music_cli.ai_tracks import AITrack, AITracksManager


class TestAITrack:
    """Tests for AITrack dataclass."""

    def test_to_dict(self):
        """Test AITrack serialization to dict."""
        track = AITrack(
            prompt="jazz piano",
            file_path="/path/to/file.wav",
            timestamp="2025-01-01T12:00:00",
            duration=30,
            model="musicgen-small",
        )
        result = track.to_dict()

        assert result["prompt"] == "jazz piano"
        assert result["file_path"] == "/path/to/file.wav"
        assert result["timestamp"] == "2025-01-01T12:00:00"
        assert result["duration"] == 30
        assert result["model"] == "musicgen-small"

    def test_from_dict(self):
        """Test AITrack deserialization from dict."""
        data = {
            "prompt": "ambient music",
            "file_path": "/path/to/ambient.wav",
            "timestamp": "2025-01-02T10:00:00",
            "duration": 60,
            "model": "musicgen-small",
        }
        track = AITrack.from_dict(data)

        assert track.prompt == "ambient music"
        assert track.file_path == "/path/to/ambient.wav"
        assert track.timestamp == "2025-01-02T10:00:00"
        assert track.duration == 60
        assert track.model == "musicgen-small"

    def test_from_dict_with_defaults(self):
        """Test AITrack deserialization with missing optional fields."""
        data = {
            "prompt": "test",
            "file_path": "/path/to/test.wav",
            "timestamp": "2025-01-01T00:00:00",
        }
        track = AITrack.from_dict(data)

        assert track.duration == 30  # Default
        assert track.model == "musicgen-small"  # Default

    def test_file_exists_false(self):
        """Test file_exists returns False for non-existent file."""
        track = AITrack(
            prompt="test",
            file_path="/nonexistent/path.wav",
            timestamp="2025-01-01T00:00:00",
            duration=30,
        )
        assert track.file_exists() is False

    def test_file_exists_true(self):
        """Test file_exists returns True for existing file."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            track = AITrack(
                prompt="test",
                file_path=f.name,
                timestamp="2025-01-01T00:00:00",
                duration=30,
            )
            assert track.file_exists() is True
            # Clean up
            Path(f.name).unlink()

    def test_display_prompt_short(self):
        """Test display_prompt for short prompts."""
        track = AITrack(
            prompt="jazz",
            file_path="/path.wav",
            timestamp="2025-01-01T00:00:00",
            duration=30,
        )
        assert track.display_prompt() == "jazz"

    def test_display_prompt_long(self):
        """Test display_prompt truncates long prompts."""
        long_prompt = "a" * 100
        track = AITrack(
            prompt=long_prompt,
            file_path="/path.wav",
            timestamp="2025-01-01T00:00:00",
            duration=30,
        )
        result = track.display_prompt(max_length=50)
        assert len(result) == 50
        assert result.endswith("...")


class TestAITracksManager:
    """Tests for AITracksManager class."""

    @pytest.fixture
    def temp_tracks_file(self):
        """Create a temporary tracks file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("[]")
            yield Path(f.name)
        # Clean up
        Path(f.name).unlink(missing_ok=True)

    @pytest.fixture
    def manager(self, temp_tracks_file):
        """Create a manager with temp file."""
        return AITracksManager(tracks_file=temp_tracks_file)

    def test_empty_list(self, manager):
        """Test get_all returns empty list initially."""
        assert manager.get_all() == []

    def test_add_track(self, manager):
        """Test adding a track."""
        track = manager.add_track(
            prompt="jazz piano",
            file_path="/path/to/jazz.wav",
            duration=30,
        )

        assert track.prompt == "jazz piano"
        assert track.file_path == "/path/to/jazz.wav"
        assert track.duration == 30

        # Verify it's stored
        tracks = manager.get_all()
        assert len(tracks) == 1
        assert tracks[0].prompt == "jazz piano"

    def test_add_multiple_tracks(self, manager):
        """Test adding multiple tracks returns in reverse order."""
        manager.add_track("track1", "/path1.wav", 30)
        manager.add_track("track2", "/path2.wav", 30)
        manager.add_track("track3", "/path3.wav", 30)

        tracks = manager.get_all()
        assert len(tracks) == 3
        # Newest first
        assert tracks[0].prompt == "track3"
        assert tracks[1].prompt == "track2"
        assert tracks[2].prompt == "track1"

    def test_get_by_index_valid(self, manager):
        """Test get_by_index with valid index."""
        manager.add_track("track1", "/path1.wav", 30)
        manager.add_track("track2", "/path2.wav", 30)

        # Index 1 should be newest (track2)
        track = manager.get_by_index(1)
        assert track is not None
        assert track.prompt == "track2"

        # Index 2 should be older (track1)
        track = manager.get_by_index(2)
        assert track is not None
        assert track.prompt == "track1"

    def test_get_by_index_invalid(self, manager):
        """Test get_by_index with invalid index."""
        manager.add_track("track1", "/path1.wav", 30)

        assert manager.get_by_index(0) is None
        assert manager.get_by_index(2) is None
        assert manager.get_by_index(-1) is None

    def test_remove_by_index(self, manager, tmp_path):
        """Test removing a track by index."""
        # Create a real temp file
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake audio data")

        manager.add_track("track1", "/path1.wav", 30)
        manager.add_track("track2", str(audio_file), 30)

        # Remove index 1 (track2, the newest)
        removed = manager.remove_by_index(1)
        assert removed is not None
        assert removed.prompt == "track2"

        # Verify file was deleted
        assert not audio_file.exists()

        # Verify track list is updated
        tracks = manager.get_all()
        assert len(tracks) == 1
        assert tracks[0].prompt == "track1"

    def test_remove_by_index_invalid(self, manager):
        """Test removing with invalid index."""
        manager.add_track("track1", "/path1.wav", 30)

        assert manager.remove_by_index(0) is None
        assert manager.remove_by_index(2) is None

    def test_update_file_path(self, manager):
        """Test updating file path for a track."""
        manager.add_track("track1", "/old/path1.wav", 30)
        manager.add_track("track2", "/old/path2.wav", 30)

        # Update track at index 1 (newest = track2)
        result = manager.update_file_path(1, "/new/path2.wav")
        assert result is True

        # Verify the update
        track = manager.get_by_index(1)
        assert track is not None
        assert track.file_path == "/new/path2.wav"

        # Verify track1 is unchanged
        track1 = manager.get_by_index(2)
        assert track1 is not None
        assert track1.file_path == "/old/path1.wav"

    def test_update_file_path_invalid_index(self, manager):
        """Test updating with invalid index."""
        manager.add_track("track1", "/path1.wav", 30)

        assert manager.update_file_path(0, "/new.wav") is False
        assert manager.update_file_path(2, "/new.wav") is False

    def test_count(self, manager):
        """Test count method."""
        assert manager.count() == 0

        manager.add_track("track1", "/path1.wav", 30)
        assert manager.count() == 1

        manager.add_track("track2", "/path2.wav", 30)
        assert manager.count() == 2

    def test_persistence(self, temp_tracks_file):
        """Test that tracks persist across manager instances."""
        # Add with one manager
        manager1 = AITracksManager(tracks_file=temp_tracks_file)
        manager1.add_track("persistent track", "/path.wav", 45)

        # Read with a new manager
        manager2 = AITracksManager(tracks_file=temp_tracks_file)
        tracks = manager2.get_all()

        assert len(tracks) == 1
        assert tracks[0].prompt == "persistent track"
        assert tracks[0].duration == 45

    def test_corrupted_file_handling(self, temp_tracks_file):
        """Test handling of corrupted JSON file."""
        # Write invalid JSON
        temp_tracks_file.write_text("not valid json")

        manager = AITracksManager(tracks_file=temp_tracks_file)
        # Should return empty list instead of crashing
        assert manager.get_all() == []
