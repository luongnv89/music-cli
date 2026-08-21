"""Characterization tests for the daemon command surface (#70).

Part 1 of F-TEST-006: pins the *current observable behaviour* of every
handler in ``MusicDaemon._process_command``'s dispatch table (19 commands)
before the Sprint 6 restructuring, so refactors 6.1-6.3 have a safety net.

Assertions target client-visible response dicts only — never internal
attributes — so the suite survives handler reorganization. Success paths run
over a real TCP connection through ``_handle_client`` (the same surface the
CLI sees, including JSON serialization); primary error paths exercise the
dispatch surface directly via ``_process_command``.

Hermetic by construction: heavy dependencies (ffplay subprocess, AI
generation, YouTube resolution) are stubbed; the only network is localhost
TCP, which is cross-platform.
"""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from music_cli.ai_tracks import AITrack
from music_cli.history import HistoryEntry
from music_cli.player.base import TrackInfo
from tests.test_daemon import _DaemonTestHarness, _roundtrip, _StubPlayer


class _CommandStubPlayer(_StubPlayer):
    """Stub player extended with the controls the command handlers exercise."""

    def __init__(self, play_succeeds: bool = True) -> None:
        super().__init__()
        self.volume = 80
        self.play_succeeds = play_succeeds

    async def play(self, track: Any) -> bool:
        await self.stop()
        self.events.append(f"play:{track.source}")
        proc = {"id": track.source, "killed": False}
        self.processes.append(proc)
        self._process = proc
        return self.play_succeeds

    async def pause(self) -> None:
        self.events.append("pause")

    async def resume(self) -> None:
        self.events.append("resume")

    async def set_volume(self, level: int) -> None:
        self.volume = level


def _stub_config(tmp_path: Path) -> MagicMock:
    config = MagicMock(name="config")
    config.ai_music_dir = tmp_path / "ai-music"
    config.youtube_cache_dir = tmp_path / "yt-cache"
    config.pid_file = tmp_path / "daemon.pid"
    config.get_youtube_cache_config.return_value = {"max_size_gb": 2.0}
    config.validate_ai_model.return_value = True
    config.list_ai_models.return_value = ["musicgen-small"]
    config.get_ai_models_config.return_value.get_model.return_value = SimpleNamespace(
        id="musicgen-small", supports_lyrics=False, requires_lyrics=False
    )
    return config


def _make_command_daemon(tmp_path: Path, player: Any | None = None) -> Any:
    """Harness daemon with every heavy dependency stubbed out."""
    daemon = _DaemonTestHarness.make_daemon(tmp_path)
    daemon.player = player if player is not None else _CommandStubPlayer()
    daemon._auto_play = False
    daemon._current_mood = None
    daemon.config = _stub_config(tmp_path)
    daemon.local_source = MagicMock(name="local_source")
    daemon.radio_source = MagicMock(name="radio_source")
    daemon.youtube_source = MagicMock(name="youtube_source")
    daemon.history = MagicMock(name="history")
    daemon.youtube_history = MagicMock(name="youtube_history")
    daemon.temporal = MagicMock(name="temporal")
    daemon.temporal.get_time_period.return_value.value = "morning"
    daemon.temporal.get_music_prompt.return_value = "morning music"
    daemon.temporal.get_info.return_value.to_dict.return_value = {"period": "morning"}
    daemon.ai_tracks = MagicMock(name="ai_tracks")
    daemon._ipc_server = AsyncMock(name="ipc_server")
    return daemon


async def _command_roundtrip(
    daemon: Any,
    command: str,
    args: dict | None = None,
    token: str | None = None,
) -> dict:
    """Send one authenticated command over TCP and return the response dict."""
    if token is None:
        token = daemon._auth_token
    server = await asyncio.start_server(daemon._handle_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        return await _roundtrip(port, {"command": command, "args": args or {}, "token": token})
    finally:
        server.close()
        await server.wait_closed()


def _local_track(source: str = "song.wav", title: str = "Song") -> TrackInfo:
    return TrackInfo(source=source, source_type="local", title=title)


def _ai_entry(tmp_path: Path, *, with_file: bool, prompt: str = "piano loop") -> AITrack:
    file_path = tmp_path / "ai-music" / "gen.wav"
    if with_file:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(b"fake audio")
    return AITrack(
        prompt=prompt,
        file_path=str(file_path),
        timestamp="2026-08-21T00:00:00",
        duration=30,
    )


def _setup_none(daemon: Any, tmp_path: Path) -> None:
    return None


def _setup_auto_play(daemon: Any, tmp_path: Path) -> None:
    daemon._auto_play = True
    daemon.local_source.get_random_track.return_value = _local_track("next.wav", "next")


def _setup_ai_library_with_file(daemon: Any, tmp_path: Path) -> None:
    daemon.ai_tracks.get_by_index.return_value = _ai_entry(tmp_path, with_file=True)


def _setup_ai_remove(daemon: Any, tmp_path: Path) -> None:
    removed = AITrack(
        prompt="jazz drums",
        file_path=str(tmp_path / "ai-music" / "gone.wav"),
        timestamp="2026-08-21T00:00:00",
        duration=15,
    )
    daemon.ai_tracks.remove_by_index.return_value = removed


def _setup_yt_history_empty(daemon: Any, tmp_path: Path) -> None:
    daemon.youtube_history.get_all.return_value = []


def _setup_yt_history_cached_file(daemon: Any, tmp_path: Path) -> None:
    cache_dir = tmp_path / "yt-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "abc123.m4a").write_bytes(b"cached audio")
    daemon.youtube_history.get_by_index.return_value = SimpleNamespace(
        video_id="abc123",
        url="https://youtube.com/watch?v=abc123",
        title="My Video",
        artist="Artist",
        duration=120.0,
        timestamp="2026-08-21T00:00:00",
    )


def _setup_yt_history_remove(daemon: Any, tmp_path: Path) -> None:
    cache_dir = tmp_path / "yt-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "xyz789.m4a").write_bytes(b"cached audio")
    daemon.youtube_history.remove_by_index.return_value = SimpleNamespace(
        video_id="xyz789", title="Removed Video"
    )


def _setup_yt_history_clear(daemon: Any, tmp_path: Path) -> None:
    cache_dir = tmp_path / "yt-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "a.m4a").write_bytes(b"1")
    (cache_dir / "b.m4a").write_bytes(b"2")
    daemon.youtube_history.count.return_value = 2


def _check_exact(expected: dict) -> Any:
    def check(daemon: Any, response: dict, tmp_path: Path) -> None:
        assert response == expected

    return check


def _matches_subset(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _matches_subset(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(_matches_subset(a, e) for a, e in zip(actual, expected, strict=True))
        )
    return actual == expected


def _check_subset(expected: dict) -> Any:
    def check(daemon: Any, response: dict, tmp_path: Path) -> None:
        assert _matches_subset(response, expected), response

    return check


async def _check_shutdown(daemon: Any, response: dict, tmp_path: Path) -> None:
    assert response == {"status": "shutting_down"}
    pending = list(daemon._background_tasks)
    if pending:
        await asyncio.wait_for(asyncio.gather(*pending), timeout=5)


def _check_ping(daemon: Any, response: dict, tmp_path: Path) -> None:
    assert response == {"status": "ok", "message": "pong", "identity": daemon._identity}


def _check_ai_play(daemon: Any, response: dict, tmp_path: Path) -> None:
    assert response["status"] == "playing"
    assert response["prompt"] == "lofi beat"
    assert response["track"]["source"].endswith("gen.wav")
    assert response["track"]["source_type"] == "ai"


def _check_ai_remove(daemon: Any, response: dict, tmp_path: Path) -> None:
    assert response == {
        "status": "removed",
        "prompt": "jazz drums",
        "file_path": str(tmp_path / "ai-music" / "gone.wav"),
    }


def _setup_play_local(daemon: Any, tmp_path: Path) -> None:
    daemon.local_source.get_track.return_value = _local_track()


def _setup_list_radios(daemon: Any, tmp_path: Path) -> None:
    daemon.radio_source.list_stations.return_value = [
        {"name": "Jazz", "url": "http://jazz.example"}
    ]


def _setup_list_history(daemon: Any, tmp_path: Path) -> None:
    daemon.history.get_all.return_value = [
        HistoryEntry(
            timestamp="2026-08-21T00:00:00",
            source="song.wav",
            source_type="local",
            title="Song",
        )
    ]


def _setup_ai_list(daemon: Any, tmp_path: Path) -> None:
    daemon.ai_tracks.get_all.return_value = [
        AITrack(
            prompt="piano loop",
            file_path=str(tmp_path / "missing.wav"),
            timestamp="2026-08-21T00:00:00",
            duration=30,
        )
    ]


SWEEP_CASES = [
    pytest.param("ping", {}, _setup_none, _check_ping, id="ping"),
    pytest.param(
        "play",
        {"mode": "local", "source": "song.wav"},
        _setup_play_local,
        _check_subset(
            {
                "status": "playing",
                "track": {"source": "song.wav", "source_type": "local", "title": "Song"},
            }
        ),
        id="play-local",
    ),
    pytest.param("stop", {}, _setup_none, _check_exact({"status": "stopped"}), id="stop"),
    pytest.param("pause", {}, _setup_none, _check_exact({"status": "paused"}), id="pause"),
    pytest.param("resume", {}, _setup_none, _check_exact({"status": "playing"}), id="resume"),
    pytest.param(
        "status",
        {},
        _setup_none,
        _check_exact(
            {
                "state": "stopped",
                "auto_play": False,
                "mood": None,
                "context": {"period": "morning"},
            }
        ),
        id="status",
    ),
    pytest.param(
        "next",
        {},
        _setup_auto_play,
        _check_exact({"status": "playing_next"}),
        id="next",
    ),
    pytest.param(
        "volume",
        {"level": "50"},
        _setup_none,
        _check_exact({"volume": 50}),
        id="volume-set",
    ),
    pytest.param("volume", {}, _setup_none, _check_exact({"volume": 80}), id="volume-query"),
    pytest.param(
        "list_radios",
        {},
        _setup_list_radios,
        _check_exact({"stations": [{"name": "Jazz", "url": "http://jazz.example"}]}),
        id="list_radios",
    ),
    pytest.param(
        "list_history",
        {},
        _setup_list_history,
        _check_subset(
            {
                "history": [
                    {
                        "index": 1,
                        "source": "song.wav",
                        "source_type": "local",
                        "title": "Song",
                    }
                ]
            }
        ),
        id="list_history",
    ),
    pytest.param(
        "ai_list",
        {},
        _setup_ai_list,
        _check_exact(
            {
                "tracks": [
                    {
                        "index": 1,
                        "prompt": "piano loop",
                        "duration": 30,
                        "timestamp": "2026-08-21T00:00:00",
                        "model": "musicgen-small",
                        "file_exists": False,
                    }
                ]
            }
        ),
        id="ai_list",
    ),
    pytest.param("ai_play", {"prompt": "lofi beat"}, _setup_none, _check_ai_play, id="ai_play"),
    pytest.param(
        "ai_replay",
        {"index": 1},
        _setup_ai_library_with_file,
        _check_subset(
            {
                "status": "playing",
                "track": {"source_type": "ai", "title": "AI: piano loop"},
            }
        ),
        id="ai_replay",
    ),
    pytest.param("ai_remove", {"index": 1}, _setup_ai_remove, _check_ai_remove, id="ai_remove"),
    pytest.param(
        "youtube_history_list",
        {},
        _setup_yt_history_empty,
        _check_exact(
            {
                "tracks": [],
                "stats": {
                    "count": 0,
                    "total_size_mb": 0.0,
                    "max_size_gb": 2.0,
                    "usage_percent": 0.0,
                },
            }
        ),
        id="youtube_history_list",
    ),
    pytest.param(
        "youtube_history_play",
        {"index": 1},
        _setup_yt_history_cached_file,
        _check_subset(
            {
                "status": "playing",
                "track": {"source_type": "youtube", "title": "My Video"},
            }
        ),
        id="youtube_history_play",
    ),
    pytest.param(
        "youtube_history_remove",
        {"index": 1},
        _setup_yt_history_remove,
        _check_exact({"status": "removed", "title": "Removed Video"}),
        id="youtube_history_remove",
    ),
    pytest.param(
        "youtube_history_clear",
        {},
        _setup_yt_history_clear,
        _check_exact({"status": "cleared", "removed_count": 2}),
        id="youtube_history_clear",
    ),
    pytest.param("shutdown", {}, _setup_none, _check_shutdown, id="shutdown"),
]


class TestCommandSurfaceSuccessSweep:
    """Every dispatch-table handler answers its success shape over TCP."""

    @pytest.mark.parametrize(("command", "args", "setup", "check"), SWEEP_CASES)
    async def test_success_paths_over_the_wire(
        self,
        command: str,
        args: dict,
        setup: Any,
        check: Any,
        tmp_path: Path,
    ) -> None:
        daemon = _make_command_daemon(tmp_path)
        setup(daemon, tmp_path)

        # Deterministic regardless of which optional extras are installed;
        # harmless for commands that never touch YouTube.
        with patch("music_cli.daemon.is_youtube_available", return_value=True):
            if command == "ai_play":
                generated = TrackInfo(
                    source=str(tmp_path / "ai-music" / "gen.wav"),
                    source_type="ai",
                    title="AI song",
                    metadata={"model": "musicgen-small", "duration": 5},
                )
                with (
                    patch(
                        "music_cli.sources.ai_generator.is_ai_available",
                        return_value=True,
                    ),
                    patch("music_cli.sources.ai_generator.AIGenerator") as generator_cls,
                ):
                    generator_cls.return_value.generate.return_value = generated
                    response = await _command_roundtrip(daemon, command, args)
            else:
                response = await _command_roundtrip(daemon, command, args)

        assert "error" not in response, response
        result = check(daemon, response, tmp_path)
        if asyncio.iscoroutine(result):
            await result


class TestPlayModeBranches:
    """The play handler's mode dispatch, pinned through the wire surface."""

    async def test_radio_mode_plays_station_by_name(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.radio_source.get_station_by_name.return_value = TrackInfo(
            source="http://stream.example", source_type="radio", title="Jazz FM"
        )
        response = await _command_roundtrip(daemon, "play", {"mode": "radio", "source": "jazz"})
        assert response["status"] == "playing"
        assert response["track"]["title"] == "Jazz FM"
        assert response["track"]["source_type"] == "radio"

    async def test_radio_mode_falls_back_to_url_lookup(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.radio_source.get_station_by_name.return_value = None
        daemon.radio_source.get_track.return_value = TrackInfo(
            source="http://stream.example", source_type="radio", title="Stream"
        )
        response = await _command_roundtrip(
            daemon, "play", {"mode": "radio", "source": "http://stream.example"}
        )
        assert response["status"] == "playing"
        assert response["track"]["source"] == "http://stream.example"

    async def test_radio_mode_without_source_uses_time_period(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.radio_source.get_time_station.return_value = TrackInfo(
            source="http://morning.example", source_type="radio", title="Morning Mix"
        )
        response = await _command_roundtrip(daemon, "play", {"mode": "radio"})
        assert response["status"] == "playing"
        assert response["track"]["title"] == "Morning Mix"

    async def test_radio_station_with_youtube_url_is_swapped_for_stream(
        self, tmp_path: Path
    ) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.radio_source.get_station_by_name.return_value = TrackInfo(
            source="https://www.youtube.com/watch?v=xyz",
            source_type="radio",
            title="YT Station",
        )
        daemon.youtube_source.get_track.return_value = TrackInfo(
            source="https://stream.example/audio.m4a", source_type="youtube"
        )
        response = await _command_roundtrip(
            daemon, "play", {"mode": "radio", "source": "yt-station"}
        )
        assert response["status"] == "playing"
        assert response["track"]["source"] == "https://stream.example/audio.m4a"
        assert response["track"]["title"] == "YT Station"

    async def test_context_mode_with_mood_sets_mood_and_plays(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.radio_source.get_mood_station.return_value = TrackInfo(
            source="http://happy.example", source_type="radio", title="Happy Hits"
        )
        response = await _command_roundtrip(daemon, "play", {"mode": "context", "mood": "happy"})
        assert response["status"] == "playing"
        assert response["track"]["title"] == "Happy Hits"

        follow_up = await _command_roundtrip(daemon, "status", {})
        assert follow_up["mood"] == "happy"

    async def test_history_mode_replays_local_entry(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.history.get_by_index.return_value = HistoryEntry(
            timestamp="2026-08-21T00:00:00",
            source="song.wav",
            source_type="local",
        )
        daemon.local_source.get_track.return_value = _local_track()
        response = await _command_roundtrip(daemon, "play", {"mode": "history", "index": 1})
        assert response["status"] == "playing"
        assert response["track"]["source"] == "song.wav"

    async def test_ai_mode_generates_when_available(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        generated = TrackInfo(
            source=str(tmp_path / "ai-music" / "ctx.wav"),
            source_type="ai",
            title="AI song",
            metadata={"model": "musicgen-small", "duration": 15},
        )
        with (
            patch("music_cli.sources.ai_generator.is_ai_available", return_value=True),
            patch("music_cli.sources.ai_generator.AIGenerator") as generator_cls,
        ):
            generator_cls.return_value.generate_for_context.return_value = generated
            response = await _command_roundtrip(daemon, "play", {"mode": "ai", "duration": 15})
        assert response["status"] == "playing"
        assert response["track"]["source_type"] == "ai"


class TestPlayErrorPaths:
    """Primary client-visible failures of the play handler."""

    async def test_play_error_when_no_track_found(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.local_source.get_track.return_value = None
        response = await daemon._process_command("play", {"mode": "local", "source": "missing.wav"})
        assert response == {"error": "Could not find track to play"}

    async def test_play_error_when_player_fails_to_start(self, tmp_path: Path) -> None:
        player = _CommandStubPlayer(play_succeeds=False)
        daemon = _make_command_daemon(tmp_path, player)
        daemon.local_source.get_track.return_value = _local_track()
        response = await daemon._process_command("play", {"mode": "local", "source": "song.wav"})
        assert response == {"error": "Failed to start playback"}

    async def test_play_youtube_requires_source(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        response = await daemon._process_command("play", {"mode": "youtube"})
        assert response == {
            "error": "YouTube URL is required. Use: -s 'https://youtube.com/watch?v=...'"
        }

    async def test_play_youtube_unavailable(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        with patch("music_cli.daemon.is_youtube_available", return_value=False):
            response = await daemon._process_command(
                "play", {"mode": "youtube", "source": "https://youtu.be/x"}
            )
        assert response == {
            "error": "YouTube playback not available. Install with: pip install 'coder-music-cli[youtube]'"
        }

    async def test_play_history_youtube_unavailable(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.history.get_by_index.return_value = HistoryEntry(
            timestamp="2026-08-21T00:00:00",
            source="https://youtube.com/watch?v=gone",
            source_type="youtube",
        )
        with patch("music_cli.daemon.is_youtube_available", return_value=False):
            response = await daemon._process_command("play", {"mode": "history", "index": 1})
        assert response == {
            "error": "YouTube playback not available. Install with: pip install 'coder-music-cli[youtube]'"
        }


class TestTransportSurface:
    """Auth and dispatch behaviour visible on the wire."""

    async def test_ping_with_wrong_token_is_unauthorized(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        response = await _command_roundtrip(
            daemon,
            "ping",
            {},
            token="wrong-token",  # noqa: S106
        )
        assert response == {"error": "Unauthorized"}

    async def test_unknown_command_lists_the_offender(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        response = await daemon._process_command("teleport", {})
        assert response == {"error": "Unknown command: teleport"}


def _break_player_method(method_name: str) -> Any:
    def setup(daemon: Any) -> None:
        setattr(
            daemon.player,
            method_name,
            AsyncMock(side_effect=RuntimeError("boom")),
        )

    return setup


def _break_player_get_status(daemon: Any) -> None:
    daemon.player.get_status = MagicMock(side_effect=RuntimeError("boom"))


def _break_radio_listing(daemon: Any) -> None:
    daemon.radio_source.list_stations.side_effect = RuntimeError("boom")


def _break_history_listing(daemon: Any) -> None:
    daemon.history.get_all.side_effect = RuntimeError("boom")


def _break_ai_listing(daemon: Any) -> None:
    daemon.ai_tracks.get_all.side_effect = RuntimeError("boom")


def _break_yt_history_listing(daemon: Any) -> None:
    daemon.youtube_history.get_all.side_effect = RuntimeError("boom")


def _break_yt_history_count(daemon: Any) -> None:
    daemon.youtube_history.count.side_effect = RuntimeError("boom")


GENERIC_ERROR_CASES = [
    pytest.param("stop", {}, _break_player_method("stop"), id="stop"),
    pytest.param("pause", {}, _break_player_method("pause"), id="pause"),
    pytest.param("resume", {}, _break_player_method("resume"), id="resume"),
    pytest.param("status", {}, _break_player_get_status, id="status"),
    pytest.param("volume", {"level": 50}, _break_player_method("set_volume"), id="volume"),
    pytest.param("list_radios", {}, _break_radio_listing, id="list_radios"),
    pytest.param("list_history", {}, _break_history_listing, id="list_history"),
    pytest.param("ai_list", {}, _break_ai_listing, id="ai_list"),
    pytest.param("youtube_history_list", {}, _break_yt_history_listing, id="youtube_history_list"),
    pytest.param("youtube_history_clear", {}, _break_yt_history_count, id="youtube_history_clear"),
]


class TestDispatchErrorPaths:
    """Handler failures surface as the generic wrapper, never exception text."""

    @pytest.mark.parametrize(("command", "args", "break_dependency"), GENERIC_ERROR_CASES)
    async def test_broken_dependency_returns_generic_error(
        self,
        command: str,
        args: dict,
        break_dependency: Any,
        tmp_path: Path,
    ) -> None:
        daemon = _make_command_daemon(tmp_path)
        break_dependency(daemon)
        response = await daemon._process_command(command, args)
        assert response == {"error": "Internal error while processing command"}

    async def test_next_requires_auto_play(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        response = await daemon._process_command("next", {})
        assert response == {"error": "Auto-play not enabled"}

    async def test_ai_play_without_ai_extras(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        with patch("music_cli.sources.ai_generator.is_ai_available", return_value=False):
            response = await daemon._process_command("ai_play", {})
        assert response == {
            "error": "AI generation not available. Install with: pip install 'coder-music-cli[ai]'"
        }

    async def test_ai_play_rejects_unknown_model(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.config.validate_ai_model.return_value = False
        daemon.config.list_ai_models.return_value = ["musicgen-small", "musicgen-large"]
        with patch("music_cli.sources.ai_generator.is_ai_available", return_value=True):
            response = await daemon._process_command("ai_play", {"model": "nope"})
        assert response == {
            "error": "Unknown or disabled model: 'nope'. Available: musicgen-small, musicgen-large"
        }

    async def test_ai_play_reports_failed_generation(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        with (
            patch("music_cli.sources.ai_generator.is_ai_available", return_value=True),
            patch("music_cli.sources.ai_generator.AIGenerator") as generator_cls,
        ):
            generator_cls.return_value.generate.return_value = None
            response = await daemon._process_command("ai_play", {"prompt": "lofi"})
        assert response == {"error": "Failed to generate AI music"}

    async def test_ai_replay_with_empty_library(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.ai_tracks.count.return_value = 0
        daemon.ai_tracks.get_by_index.return_value = None
        response = await daemon._process_command("ai_replay", {})
        assert response == {
            "error": "No AI tracks available. Generate one with 'music-cli ai play'"
        }

    async def test_ai_replay_with_out_of_range_index(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.ai_tracks.count.return_value = 3
        daemon.ai_tracks.get_by_index.return_value = None
        response = await daemon._process_command("ai_replay", {"index": 9})
        assert response == {"error": "Invalid index. Choose between 1 and 3"}

    async def test_ai_replay_reports_missing_file(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.ai_tracks.get_by_index.return_value = _ai_entry(tmp_path, with_file=False)
        response = await daemon._process_command("ai_replay", {"index": 1})
        assert response == {
            "status": "file_missing",
            "prompt": "piano loop",
            "message": "Audio file not found. Regenerate with the same prompt?",
        }

    async def test_ai_remove_with_empty_library(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.ai_tracks.count.return_value = 0
        daemon.ai_tracks.get_by_index.return_value = None
        response = await daemon._process_command("ai_remove", {})
        assert response == {"error": "No AI tracks to remove"}

    async def test_ai_remove_with_out_of_range_index(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.ai_tracks.count.return_value = 2
        daemon.ai_tracks.get_by_index.return_value = None
        response = await daemon._process_command("ai_remove", {"index": 9})
        assert response == {"error": "Invalid index. Choose between 1 and 2"}

    async def test_youtube_history_play_with_invalid_index(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.youtube_history.get_by_index.return_value = None
        response = await daemon._process_command("youtube_history_play", {"index": 9})
        assert response == {"error": "Invalid index: 9"}

    async def test_youtube_history_play_unavailable(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.youtube_history.get_by_index.return_value = SimpleNamespace(
            video_id="abc123",
            url="https://youtube.com/watch?v=abc123",
            title="My Video",
            artist="Artist",
            duration=120.0,
        )
        with patch("music_cli.daemon.is_youtube_available", return_value=False):
            response = await daemon._process_command("youtube_history_play", {"index": 1})
        assert response == {"error": "YouTube playback not available."}

    async def test_youtube_history_remove_with_invalid_index(self, tmp_path: Path) -> None:
        daemon = _make_command_daemon(tmp_path)
        daemon.youtube_history.remove_by_index.return_value = None
        response = await daemon._process_command("youtube_history_remove", {"index": 9})
        assert response == {"error": "Invalid index: 9"}
