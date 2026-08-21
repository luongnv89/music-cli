"""Complementary History tests (issue #72 — coverage raise).

Covers the branches left open by ``test_history.py``: display formatting,
malformed-line tolerance, search limits, type filtering, and the singleton.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import music_cli.history as history_module
from music_cli.history import History, HistoryEntry, get_history


class TestDisplayStr:
    def test_title_preferred_over_source(self) -> None:
        entry = HistoryEntry(
            timestamp="2026-08-21T10:00:00",
            source="/music/song.mp3",
            source_type="local",
            title="Song Title",
        )
        assert entry.display_str() == "2026-08-21T10:00:00 | Song Title | [local]"

    def test_local_source_uses_basename(self) -> None:
        entry = HistoryEntry(
            timestamp="t", source="/music/sub/track.mp3", source_type="local"
        )
        assert "track.mp3" in entry.display_str()

    def test_long_remote_source_is_truncated(self) -> None:
        long_url = "https://example.com/" + "a" * 60
        entry = HistoryEntry(timestamp="t", source=long_url, source_type="radio")
        display = entry.display_str()
        assert "..." in display
        assert long_url not in display

    def test_artist_is_appended(self) -> None:
        entry = HistoryEntry(
            timestamp="t", source="s", source_type="ai", artist="The Coder"
        )
        assert "by The Coder" in entry.display_str()


class TestFromDictDefaults:
    def test_missing_keys_fall_back(self) -> None:
        entry = HistoryEntry.from_dict({})
        assert entry.timestamp == ""
        assert entry.source == ""
        assert entry.source_type == "unknown"
        assert entry.title is None
        assert entry.artist is None
        assert entry.mood is None
        assert entry.context is None


class TestHistoryRobustness:
    def test_get_all_with_missing_file(self, tmp_path: Path) -> None:
        history = History(tmp_path / "absent.jsonl")
        assert history.get_all() == []

    def test_get_all_skips_blank_and_malformed_lines(self, tmp_path: Path) -> None:
        import json

        history_file = tmp_path / "history.jsonl"
        good = HistoryEntry(
            timestamp="t2", source="s2", source_type="local", title="Good"
        )
        history_file.write_text(
            "\n"
            "{not json}\n"
            '{"timestamp": "t1", "source": "s1", "source_type": "local"}\n'
            + json.dumps(good.to_dict())
            + "\n",
            encoding="utf-8",
        )
        entries = History(history_file).get_all()
        # Only the valid JSON lines survive; newest first.
        assert len(entries) == 2
        assert entries[0].title == "Good"
        assert entries[1].source == "s1"

    def test_default_history_file_comes_from_config(self) -> None:
        history = History(None)
        from music_cli.config import get_config

        assert history.history_file == get_config().history_file


class TestSearchAndFiltering:
    @pytest.fixture()
    def populated(self, tmp_path: Path) -> History:
        history = History(tmp_path / "h.jsonl")
        history.log("/m/a.mp3", "local", title="Chill Beats", artist="DJ Code")
        history.log("https://stream.example/jazz", "radio")
        history.log("/m/focus.mp3", "local", title="Deep Focus")
        return history

    def test_search_matches_title_artist_and_source(
        self, populated: History
    ) -> None:
        by_title = populated.search("chill")
        assert len(by_title) == 1 and by_title[0].artist == "DJ Code"

        by_source = populated.search("jazz")
        assert len(by_source) == 1 and by_source[0].source_type == "radio"

        assert populated.search("nothing-matches-this") == []

    def test_search_limit_breaks_early(self, tmp_path: Path) -> None:
        history = History(tmp_path / "h.jsonl")
        for i in range(5):
            history.log(f"/m/{i}.mp3", "local", title=f"same words {i}")
        results = history.search("same", limit=2)
        assert len(results) == 2

    def test_get_recent_by_type_filters_and_limits(self, populated: History) -> None:
        locals_ = populated.get_recent_by_type("local", limit=1)
        assert len(locals_) == 1
        assert locals_[0].source_type == "local"

        radios = populated.get_recent_by_type("radio")
        assert len(radios) == 1


class TestSingleton:
    def test_get_history_creates_and_reuses(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(history_module, "_history", None)
        first = get_history()
        second = get_history()
        assert first is second

    def test_clear_wipes_file(self, tmp_path: Path) -> None:
        history_file = tmp_path / "h.jsonl"
        history = History(history_file)
        history.log("/m/x.mp3", "local")
        history.clear()
        assert history.history_file.read_text() == ""
        assert history.get_all() == []
