"""Unit tests for the per-mode play resolvers extracted in task 6.1 (#73).

Complements — never modifies — the 5.4 characterization suite in
``tests/test_daemon_commands.py``: these pin the play-mode seams that suite
does not exercise, through the same wire-level surfaces (``_command_roundtrip``
for success paths, ``_process_command`` for primary error paths).
"""

import sys
from pathlib import Path
from unittest.mock import patch

from music_cli.history import HistoryEntry
from music_cli.player.base import TrackInfo
from tests.test_daemon_commands import (
    _command_roundtrip,
    _local_track,
    _make_command_daemon,
)


class TestLocalModeResolvers:
    async def test_local_mode_without_source_picks_random_track(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.local_source.get_random_track.return_value = _local_track("random.wav", "Random")
        response = await _command_roundtrip(daemon, "play", {"mode": "local"})
        assert response["status"] == "playing"
        assert response["track"]["source"] == "random.wav"


class TestRadioModeResolverSeams:
    async def test_radio_mode_with_mood_uses_mood_station(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.radio_source.get_mood_station.return_value = TrackInfo(
            source="http://mood.example", source_type="radio", title="Mood Mix"
        )
        response = await _command_roundtrip(daemon, "play", {"mode": "radio", "mood": "happy"})
        assert response["status"] == "playing"
        assert response["track"]["title"] == "Mood Mix"
        daemon.radio_source.get_mood_station.assert_called_once_with("happy")

    async def test_radio_mode_without_source_falls_back_to_random_station(
        self, tmp_path: Path
    ) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.radio_source.get_time_station.return_value = None
        daemon.radio_source.get_random_station.return_value = TrackInfo(
            source="http://random.example", source_type="radio", title="Random Radio"
        )
        response = await _command_roundtrip(daemon, "play", {"mode": "radio"})
        assert response["status"] == "playing"
        assert response["track"]["title"] == "Random Radio"

    async def test_radio_youtube_station_keeps_station_when_resolution_fails(
        self, tmp_path: Path
    ) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.radio_source.get_station_by_name.return_value = TrackInfo(
            source="https://www.youtube.com/watch?v=xyz",
            source_type="radio",
            title="YT Station",
        )
        daemon.youtube_source.get_track.return_value = None
        response = await _command_roundtrip(daemon, "play", {"mode": "radio", "source": "yt"})
        assert response["status"] == "playing"
        assert response["track"]["source"] == "https://www.youtube.com/watch?v=xyz"
        assert response["track"]["title"] == "YT Station"


class TestContextModeResolverSeams:
    async def test_context_mode_without_mood_falls_back_to_random_station(
        self, tmp_path: Path
    ) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon._current_mood = None
        daemon.radio_source.get_time_station.return_value = None
        daemon.radio_source.get_random_station.return_value = TrackInfo(
            source="http://random.example", source_type="radio", title="Random Radio"
        )
        response = await _command_roundtrip(daemon, "play", {"mode": "context"})
        assert response["status"] == "playing"
        assert response["track"]["title"] == "Random Radio"


class TestHistoryModeResolverSeams:
    async def test_history_mode_with_unknown_index_reports_no_track(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.history.get_by_index.return_value = None
        response = await daemon._process_command("play", {"mode": "history", "index": 9})
        assert response == {"error": "Could not find track to play"}

    async def test_history_mode_replays_radio_entry(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.history.get_by_index.return_value = HistoryEntry(
            timestamp="2026-08-21T00:00:00",
            source="http://stream.example",
            source_type="radio",
            title="Evening Jazz",
        )
        daemon.radio_source.get_track.return_value = TrackInfo(
            source="http://stream.example", source_type="radio", title="Evening Jazz"
        )
        response = await _command_roundtrip(daemon, "play", {"mode": "history", "index": 2})
        assert response["status"] == "playing"
        assert response["track"]["title"] == "Evening Jazz"
        daemon.radio_source.get_track.assert_called_once_with(
            "http://stream.example", "Evening Jazz"
        )

    async def test_history_mode_youtube_video_gone_reports_error(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.history.get_by_index.return_value = HistoryEntry(
            timestamp="2026-08-21T00:00:00",
            source="https://youtube.com/watch?v=gone",
            source_type="youtube",
        )
        with (
            patch("music_cli.daemon.is_youtube_available", return_value=True),
            patch.object(daemon.youtube_source, "get_track", return_value=None),
        ):
            response = await daemon._process_command("play", {"mode": "history", "index": 1})
        assert response == {
            "error": "Could not load YouTube video (may be deleted or private): "
            "https://youtube.com/watch?v=gone"
        }


class TestYoutubeAliasAndAvailability:
    async def test_yt_alias_resolves_stream(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.youtube_source.get_track.return_value = TrackInfo(
            source="https://stream.example/audio.m4a", source_type="youtube"
        )
        with patch("music_cli.daemon.is_youtube_available", return_value=True):
            response = await _command_roundtrip(
                daemon, "play", {"mode": "yt", "source": "https://youtu.be/x"}
            )
        assert response["status"] == "playing"
        assert response["track"]["source"] == "https://stream.example/audio.m4a"
        daemon.youtube_source.get_track.assert_called_once_with("https://youtu.be/x")


class TestAiModeErrorPaths:
    async def test_ai_mode_unavailable_reports_install_hint(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        with patch("music_cli.sources.ai_generator.is_ai_available", return_value=False):
            response = await daemon._process_command("play", {"mode": "ai"})
        assert response == {
            "error": "AI generation not available. Install with: pip install 'music-cli[ai]'"
        }

    async def test_ai_mode_import_failure_reports_install_hint(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        with patch.dict(sys.modules, {"music_cli.sources.ai_generator": None}):
            response = await daemon._process_command("play", {"mode": "ai"})
        assert response == {
            "error": "AI generation not available. Install with: pip install 'music-cli[ai]'"
        }
