"""YouTubeHistory tests (issue #72 — coverage raise)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

import music_cli.youtube_history as yh_module
from music_cli.youtube_history import YouTubeHistory, YouTubeHistoryEntry


@pytest.fixture()
def history_file(tmp_path: Path) -> Path:
    return tmp_path / "youtube_history.json"


class TestLoading:
    def test_missing_file_starts_empty(self, history_file: Path) -> None:
        history = YouTubeHistory(history_file)
        assert history.get_all() == []
        assert history.count() == 0

    def test_loads_existing_entries(self, history_file: Path) -> None:
        payload = [
            {
                "video_id": "vid1",
                "url": "https://youtu.be/vid1",
                "title": "First",
                "artist": "Someone",
                "duration": 123.5,
                "timestamp": "2026-01-01T00:00:00",
            }
        ]
        history_file.write_text(json.dumps(payload))
        history = YouTubeHistory(history_file)
        assert history.count() == 1
        entry = history.get_all()[0]
        assert entry.video_id == "vid1"
        assert entry.artist == "Someone"

    def test_invalid_json_degrades_to_empty(
        self, history_file: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        history_file.write_text("{definitely not json")
        history = YouTubeHistory(history_file)
        assert history.get_all() == []

    def test_non_list_json_degrades_to_empty(self, history_file: Path) -> None:
        history_file.write_text(json.dumps({"not": "a list"}))
        history = YouTubeHistory(history_file)
        assert history.get_all() == []


class TestAddAndDedupe:
    def test_add_entry_inserts_newest_first_and_persists(self, history_file: Path) -> None:
        history = YouTubeHistory(history_file)
        history.add_entry("v1", "https://youtu.be/v1", "One")
        history.add_entry("v2", "https://youtu.be/v2", "Two")

        assert [e.video_id for e in history.get_all()] == ["v2", "v1"]
        # Reload from disk to prove persistence.
        reloaded = YouTubeHistory(history_file)
        assert [e.video_id for e in reloaded.get_all()] == ["v2", "v1"]

    def test_duplicate_video_ids_are_replaced(self, history_file: Path) -> None:
        history = YouTubeHistory(history_file)
        history.add_entry("v1", "https://youtu.be/v1", "Old title")
        history.add_entry("v1", "https://youtu.be/v1", "New title")
        assert history.count() == 1
        assert history.get_all()[0].title == "New title"

    def test_max_entries_trims_oldest(self, history_file: Path) -> None:
        history = YouTubeHistory(history_file)
        for i in range(5):
            history.add_entry(f"v{i}", f"https://youtu.be/v{i}", f"T{i}", max_entries=3)
        assert [e.video_id for e in history.get_all()] == ["v4", "v3", "v2"]


class TestIndexAccessAndRemoval:
    def _populated(self, history_file: Path) -> YouTubeHistory:
        history = YouTubeHistory(history_file)
        history.add_entry("v1", "u1", "One")
        history.add_entry("v2", "u2", "Two")
        return history

    def test_get_by_index_bounds(self, history_file: Path) -> None:
        history = self._populated(history_file)
        assert history.get_by_index(1).video_id == "v2"  # newest first
        assert history.get_by_index(2).video_id == "v1"
        assert history.get_by_index(0) is None
        assert history.get_by_index(3) is None

    def test_remove_by_index_pops_and_saves(self, history_file: Path) -> None:
        history = self._populated(history_file)
        removed = history.remove_by_index(1)
        assert removed is not None and removed.video_id == "v2"
        assert history.count() == 1
        reloaded = YouTubeHistory(history_file)
        assert reloaded.count() == 1

    def test_remove_out_of_range_returns_none(self, history_file: Path) -> None:
        history = self._populated(history_file)
        assert history.remove_by_index(9) is None
        assert history.count() == 2

    def test_clear_removes_everything_and_persists(self, history_file: Path) -> None:
        history = self._populated(history_file)
        history.clear()
        assert history.count() == 0
        assert json.loads(history_file.read_text()) == []


class TestEntrySerialization:
    def test_to_dict_fills_timestamp_when_absent(self) -> None:
        entry = YouTubeHistoryEntry(video_id="v", url="u", title="t")
        data = entry.to_dict()
        assert data["timestamp"]

    def test_from_dict_defaults(self) -> None:
        entry = YouTubeHistoryEntry.from_dict({})
        assert entry.video_id == ""
        assert entry.url == ""
        assert entry.title == "Unknown"
        assert entry.artist is None


class TestSaveFailure:
    def test_oserror_is_logged_not_raised(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Point the backing file at a directory: writes raise OSError.
        history = YouTubeHistory(tmp_path / "absent.json")
        history.history_file = tmp_path
        with caplog.at_level(logging.WARNING):
            history.add_entry("v1", "u1", "One")
        assert any("Failed to save" in r.message for r in caplog.records)


class TestSingleton:
    def test_get_youtube_history_creates_and_reuses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(yh_module, "_youtube_history", None)
        first = yh_module.get_youtube_history()
        second = yh_module.get_youtube_history()
        assert first is second
