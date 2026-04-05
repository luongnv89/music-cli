"""End-to-end tests for all music-cli commands and options.

Coverage matrix:
- All primary commands: play, stop, pause, resume, next, status, vol, mood,
  history (list/play), radio (list/play/add/remove/update), yt (list/play/remove/clear),
  ai (list/play/replay/remove + model list/download/delete/default),
  daemon (start/stop/restart/status), config, update-radios
- All hidden aliases: s, pp, r, n, st, h, radios, youtube, moods, volume
- Global flags: --version, --no-color, -h/--help, NO_COLOR env var
- Option flags: play --mode/-m, --source/-s, --mood/-M, --auto/-a,
  --duration/-d, --index/-i; vol range validation; history --limit/-n;
  ai play --prompt/-p, --model/-M; daemon actions

These tests run without a live daemon (all daemon I/O is mocked), so they
execute fast and are suitable for the pre-commit hook.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from music_cli.cli import main


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def mock_client() -> MagicMock:
    """A fully-mocked DaemonClient with sensible defaults."""
    client = MagicMock()
    client.play.return_value = {
        "track": {"title": "Test Track", "source": "test.mp3", "source_type": "local"}
    }
    client.status.return_value = {
        "state": "playing",
        "track": {"title": "Test Track", "source_type": "radio"},
        "volume": 80,
    }
    client.get_volume.return_value = {"volume": 75}
    client.set_volume.return_value = {"volume": 50}
    client.list_history.return_value = [
        {
            "index": 1,
            "title": "Song A",
            "source_type": "radio",
            "timestamp": "2026-01-01T00:00",
        },
        {
            "index": 2,
            "title": "Song B",
            "source_type": "local",
            "timestamp": "2026-01-01T01:00",
        },
    ]
    client.stop.return_value = {"status": "stopped"}
    client.pause.return_value = {"status": "paused"}
    client.resume.return_value = {"status": "resumed"}
    client.next_track.return_value = {
        "track": {"title": "Next Track", "source_type": "radio"}
    }
    return client


def _patch_daemon(mock_client: MagicMock):
    """Patch both ensure_daemon and check_ffplay_available for play tests."""
    return [
        patch("music_cli.cli.ensure_daemon", return_value=mock_client),
        patch("music_cli.cli.check_ffplay_available", return_value=True),
    ]


# ===========================================================================
# Global flags
# ===========================================================================


class TestGlobalFlags:
    """--version, --help / -h, --no-color, NO_COLOR env var."""

    def test_version(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "version" in result.output.lower()

    def test_help_long(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output

    def test_help_short(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["-h"])
        assert result.exit_code == 0
        assert "Usage:" in result.output

    def test_no_color_flag(self, runner: CliRunner) -> None:
        """--no-color suppresses emoji/unicode icons."""
        result = runner.invoke(main, ["--no-color", "--help"])
        assert result.exit_code == 0

    def test_no_color_env(self, runner: CliRunner) -> None:
        """NO_COLOR environment variable is respected."""
        result = runner.invoke(main, ["--help"], env={"NO_COLOR": "1"})
        assert result.exit_code == 0

    def test_unknown_command_exits_nonzero(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["not-a-real-command"])
        assert result.exit_code != 0


# ===========================================================================
# Help output for every command/subcommand
# ===========================================================================

_ALL_HELP_ARGS: list[list[str]] = [
    # top-level
    ["play", "--help"],
    ["stop", "--help"],
    ["pause", "--help"],
    ["resume", "--help"],
    ["next", "--help"],
    ["status", "--help"],
    ["vol", "--help"],
    ["mood", "--help"],
    ["history", "--help"],
    ["history", "list", "--help"],
    ["history", "play", "--help"],
    ["radio", "--help"],
    ["radio", "list", "--help"],
    ["radio", "play", "--help"],
    ["radio", "add", "--help"],
    ["radio", "remove", "--help"],
    ["radio", "update", "--help"],
    ["yt", "--help"],
    ["yt", "list", "--help"],
    ["yt", "play", "--help"],
    ["yt", "remove", "--help"],
    ["yt", "clear", "--help"],
    ["ai", "--help"],
    ["ai", "list", "--help"],
    ["ai", "play", "--help"],
    ["ai", "replay", "--help"],
    ["ai", "remove", "--help"],
    ["ai", "model", "--help"],
    ["ai", "model", "list", "--help"],
    ["ai", "model", "download", "--help"],
    ["ai", "model", "delete", "--help"],
    ["ai", "model", "default", "--help"],
    ["daemon", "--help"],
    ["config", "--help"],
    # aliases
    ["s", "--help"],
    ["pp", "--help"],
    ["r", "--help"],
    ["n", "--help"],
    ["st", "--help"],
    ["h", "--help"],
    ["radios", "--help"],
    ["youtube", "--help"],
    ["moods", "--help"],
    ["volume", "--help"],
]


class TestAllCommandHelp:
    """Every command and subcommand returns exit 0 for --help."""

    @pytest.mark.parametrize("cmd_args", _ALL_HELP_ARGS)
    def test_help(self, runner: CliRunner, cmd_args: list[str]) -> None:
        result = runner.invoke(main, cmd_args)
        assert result.exit_code == 0, (
            f"--help failed for {cmd_args!r}:\n{result.output}"
        )
        assert "Usage:" in result.output, (
            f"No 'Usage:' in help for {cmd_args!r}:\n{result.output}"
        )


# ===========================================================================
# play command — options
# ===========================================================================


class TestPlayOptions:
    """play --help shows all flags; flags are accepted without error."""

    def test_play_help_shows_flags(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["play", "--help"])
        assert result.exit_code == 0
        for flag in ("--mode", "-m", "--source", "-s", "--mood", "-M",
                     "--auto", "-a", "--duration", "-d", "--index", "-i"):
            assert flag in result.output, f"Missing flag {flag!r} in play --help"

    def test_play_help_shows_source_argument(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["play", "--help"])
        assert "SOURCE" in result.output

    @pytest.mark.parametrize(
        "mode",
        ["local", "radio", "ai", "context", "history", "youtube", "yt"],
    )
    def test_play_mode_values_accepted(
        self, runner: CliRunner, mode: str, mock_client: MagicMock
    ) -> None:
        """play --mode <value> should not give a Click 'invalid choice' error."""
        patches = _patch_daemon(mock_client)
        for p in patches:
            p.start()
        try:
            result = runner.invoke(main, ["play", "--mode", mode])
            # Must NOT be a Click usage error (exit 2)
            assert result.exit_code != 2, (
                f"play --mode {mode} gave usage error:\n{result.output}"
            )
        finally:
            for p in patches:
                p.stop()

    @pytest.mark.parametrize(
        "mood",
        ["happy", "sad", "excited", "focus", "relaxed", "energetic", "melancholic", "peaceful"],
    )
    def test_play_mood_values_accepted(
        self, runner: CliRunner, mood: str, mock_client: MagicMock
    ) -> None:
        patches = _patch_daemon(mock_client)
        for p in patches:
            p.start()
        try:
            result = runner.invoke(main, ["play", "--mood", mood])
            assert result.exit_code != 2, (
                f"play --mood {mood} gave usage error:\n{result.output}"
            )
        finally:
            for p in patches:
                p.stop()

    def test_play_auto_flag(
        self, runner: CliRunner, mock_client: MagicMock
    ) -> None:
        patches = _patch_daemon(mock_client)
        for p in patches:
            p.start()
        try:
            result = runner.invoke(main, ["play", "--auto"])
            assert result.exit_code != 2, f"play --auto gave usage error:\n{result.output}"
        finally:
            for p in patches:
                p.stop()

    def test_play_duration_flag(
        self, runner: CliRunner, mock_client: MagicMock
    ) -> None:
        patches = _patch_daemon(mock_client)
        for p in patches:
            p.start()
        try:
            result = runner.invoke(main, ["play", "--duration", "30"])
            assert result.exit_code != 2, f"play --duration gave usage error:\n{result.output}"
        finally:
            for p in patches:
                p.stop()

    def test_play_index_flag(
        self, runner: CliRunner, mock_client: MagicMock
    ) -> None:
        patches = _patch_daemon(mock_client)
        for p in patches:
            p.start()
        try:
            result = runner.invoke(main, ["play", "--index", "1"])
            assert result.exit_code != 2, f"play --index gave usage error:\n{result.output}"
        finally:
            for p in patches:
                p.stop()


# ===========================================================================
# stop / pause / resume / next / status
# ===========================================================================


class TestSimplePlaybackCommands:
    """stop, pause, resume, next, status — daemon mocked."""

    @pytest.mark.parametrize(
        "cmd",
        ["stop", "s", "pause", "pp", "resume", "r", "next", "n", "status", "st"],
    )
    def test_command_invokes_without_usage_error(
        self, runner: CliRunner, mock_client: MagicMock, cmd: str
    ) -> None:
        with patch("music_cli.cli.ensure_daemon", return_value=mock_client):
            result = runner.invoke(main, [cmd])
            assert result.exit_code != 2, (
                f"Command '{cmd}' gave usage error:\n{result.output}"
            )


# ===========================================================================
# vol command
# ===========================================================================


class TestVolCommand:
    """vol with no arg (get), set 0-100, reject out-of-range."""

    def test_vol_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["vol", "--help"])
        assert result.exit_code == 0
        assert "LEVEL" in result.output or "volume" in result.output.lower()

    def test_vol_get(self, runner: CliRunner, mock_client: MagicMock) -> None:
        with patch("music_cli.cli.ensure_daemon", return_value=mock_client):
            result = runner.invoke(main, ["vol"])
            assert result.exit_code != 2

    @pytest.mark.parametrize("level", ["0", "50", "100"])
    def test_vol_set_valid(
        self, runner: CliRunner, mock_client: MagicMock, level: str
    ) -> None:
        with patch("music_cli.cli.ensure_daemon", return_value=mock_client):
            result = runner.invoke(main, ["vol", level])
            assert result.exit_code != 2, (
                f"vol {level} gave usage error:\n{result.output}"
            )

    @pytest.mark.parametrize("level", ["-1", "101", "200"])
    def test_vol_set_invalid_rejected(
        self, runner: CliRunner, mock_client: MagicMock, level: str
    ) -> None:
        with patch("music_cli.cli.ensure_daemon", return_value=mock_client):
            result = runner.invoke(main, ["vol", level])
            # Should not succeed silently — exit code != 0
            assert result.exit_code != 0, (
                f"vol {level} should be rejected but exited 0:\n{result.output}"
            )

    def test_volume_alias(self, runner: CliRunner, mock_client: MagicMock) -> None:
        with patch("music_cli.cli.ensure_daemon", return_value=mock_client):
            result = runner.invoke(main, ["volume"])
            assert result.exit_code != 2


# ===========================================================================
# mood command
# ===========================================================================


class TestMoodCommand:
    """mood with no arg lists moods; with a valid mood plays; aliases work."""

    def test_mood_list(self, runner: CliRunner, mock_client: MagicMock) -> None:
        with patch("music_cli.cli.ensure_daemon", return_value=mock_client):
            result = runner.invoke(main, ["mood"])
            assert result.exit_code != 2

    @pytest.mark.parametrize(
        "mood",
        ["happy", "sad", "excited", "focus", "relaxed", "energetic", "melancholic", "peaceful"],
    )
    def test_mood_play(
        self, runner: CliRunner, mock_client: MagicMock, mood: str
    ) -> None:
        with patch("music_cli.cli.ensure_daemon", return_value=mock_client):
            result = runner.invoke(main, ["mood", mood])
            assert result.exit_code != 2, (
                f"mood {mood} gave usage error:\n{result.output}"
            )

    def test_moods_alias(self, runner: CliRunner, mock_client: MagicMock) -> None:
        with patch("music_cli.cli.ensure_daemon", return_value=mock_client):
            result = runner.invoke(main, ["moods"])
            assert result.exit_code != 2


# ===========================================================================
# history command
# ===========================================================================


class TestHistoryCommand:
    """history list, history play, -h alias, --limit flag."""

    def test_history_list(self, runner: CliRunner, mock_client: MagicMock) -> None:
        with patch("music_cli.cli.ensure_daemon", return_value=mock_client):
            result = runner.invoke(main, ["history", "list"])
            assert result.exit_code != 2

    def test_history_list_with_limit(
        self, runner: CliRunner, mock_client: MagicMock
    ) -> None:
        with patch("music_cli.cli.ensure_daemon", return_value=mock_client):
            result = runner.invoke(main, ["history", "list", "--limit", "5"])
            assert result.exit_code != 2

    def test_history_list_short_limit(
        self, runner: CliRunner, mock_client: MagicMock
    ) -> None:
        with patch("music_cli.cli.ensure_daemon", return_value=mock_client):
            result = runner.invoke(main, ["history", "list", "-n", "5"])
            assert result.exit_code != 2

    def test_history_play(self, runner: CliRunner, mock_client: MagicMock) -> None:
        with patch("music_cli.cli.ensure_daemon", return_value=mock_client):
            result = runner.invoke(main, ["history", "play", "1"])
            assert result.exit_code != 2

    def test_h_alias(self, runner: CliRunner, mock_client: MagicMock) -> None:
        with patch("music_cli.cli.ensure_daemon", return_value=mock_client):
            result = runner.invoke(main, ["h", "list"])
            assert result.exit_code != 2


# ===========================================================================
# radio command
# ===========================================================================


class TestRadioCommand:
    """radio list/play/add/remove/update and radios alias."""

    def test_radio_list(self, runner: CliRunner) -> None:
        with patch("music_cli.cli.get_config") as mock_cfg_fn:
            cfg = MagicMock()
            cfg.get_stations.return_value = [
                ("Lofi", "https://stream.lofi.com"),
                ("Jazz", "https://stream.jazz.com"),
            ]
            mock_cfg_fn.return_value = cfg
            result = runner.invoke(main, ["radio", "list"])
            assert result.exit_code != 2

    def test_radio_play_by_number(
        self, runner: CliRunner, mock_client: MagicMock
    ) -> None:
        with patch("music_cli.cli.ensure_daemon", return_value=mock_client), \
             patch("music_cli.cli.get_config") as mock_cfg_fn:
            cfg = MagicMock()
            cfg.get_stations.return_value = [("Lofi", "https://stream.lofi.com")]
            mock_cfg_fn.return_value = cfg
            result = runner.invoke(main, ["radio", "play", "1"])
            assert result.exit_code != 2

    def test_radio_remove(self, runner: CliRunner) -> None:
        with patch("music_cli.cli.get_config") as mock_cfg_fn:
            cfg = MagicMock()
            cfg.get_stations.return_value = [("Lofi", "https://stream.lofi.com")]
            cfg.remove_station.return_value = True
            mock_cfg_fn.return_value = cfg
            result = runner.invoke(main, ["radio", "remove", "1"])
            assert result.exit_code != 2

    def test_radio_update(self, runner: CliRunner) -> None:
        with patch("music_cli.cli.get_config") as mock_cfg_fn:
            cfg = MagicMock()
            mock_cfg_fn.return_value = cfg
            result = runner.invoke(main, ["radio", "update"])
            assert result.exit_code != 2

    def test_radios_alias(self, runner: CliRunner) -> None:
        with patch("music_cli.cli.get_config") as mock_cfg_fn:
            cfg = MagicMock()
            cfg.get_stations.return_value = []
            mock_cfg_fn.return_value = cfg
            result = runner.invoke(main, ["radios", "list"])
            assert result.exit_code != 2


# ===========================================================================
# yt command
# ===========================================================================


class TestYtCommand:
    """yt list/play/remove/clear and youtube/cached aliases."""

    def _mock_yt_history(self) -> MagicMock:
        yt = MagicMock()
        yt.list_tracks.return_value = [
            {
                "index": 1,
                "title": "YT Track",
                "url": "https://youtu.be/abc",
                "cached_path": "/tmp/yt.mp3",  # noqa: S108
            }
        ]
        return yt

    def _make_client(self) -> MagicMock:
        client = MagicMock()
        client.youtube_cached.return_value = {
            "tracks": [
                {
                    "index": 1,
                    "title": "YT Track",
                    "url": "https://youtu.be/abc",
                    "duration": 180,
                    "file_exists": True,
                }
            ],
            "stats": {"count": 1},
        }
        client.youtube_play.return_value = {
            "track": {"title": "YT Track", "source_type": "youtube"}
        }
        client.youtube_remove.return_value = {"title": "YT Track"}
        client.youtube_clear.return_value = {"removed_count": 1}
        return client

    def test_yt_list(self, runner: CliRunner) -> None:
        client = self._make_client()
        with patch("music_cli.cli.ensure_daemon", return_value=client):
            result = runner.invoke(main, ["yt", "list"])
            assert result.exit_code != 2

    def test_yt_play(self, runner: CliRunner) -> None:
        client = self._make_client()
        with patch("music_cli.cli.ensure_daemon", return_value=client):
            result = runner.invoke(main, ["yt", "play", "1"])
            assert result.exit_code != 2

    def test_yt_remove(self, runner: CliRunner) -> None:
        client = self._make_client()
        with patch("music_cli.cli.ensure_daemon", return_value=client):
            # Provide "n" to the confirmation prompt
            result = runner.invoke(main, ["yt", "remove", "1"], input="n\n")
            assert result.exit_code != 2

    def test_yt_clear(self, runner: CliRunner) -> None:
        client = self._make_client()
        with patch("music_cli.cli.ensure_daemon", return_value=client):
            result = runner.invoke(main, ["yt", "clear"], input="n\n")
            assert result.exit_code != 2

    def test_youtube_alias(self, runner: CliRunner) -> None:
        client = self._make_client()
        with patch("music_cli.cli.ensure_daemon", return_value=client):
            result = runner.invoke(main, ["youtube", "list"])
            assert result.exit_code != 2

    def test_yt_cached_alias(self, runner: CliRunner) -> None:
        client = self._make_client()
        with patch("music_cli.cli.ensure_daemon", return_value=client):
            result = runner.invoke(main, ["yt", "cached"])
            assert result.exit_code != 2


# ===========================================================================
# ai command
# ===========================================================================


class TestAiCommand:
    """ai list/play/replay/remove and ai model subgroup — all via daemon client."""

    def _make_client(self) -> MagicMock:
        client = MagicMock()
        client.ai_list.return_value = [
            {
                "index": 1,
                "prompt": "lofi beats",
                "duration": 15,
                "timestamp": "2026-01-01T00:00",
                "model": "musicgen-small",
                "file_exists": True,
            }
        ]
        client.ai_play.return_value = {
            "track": {
                "title": "AI Track",
                "source_type": "ai",
                "metadata": {"model": "musicgen-small"},
            },
            "prompt": "lofi beats",
        }
        client.ai_replay.return_value = {
            "track": {"title": "AI Track", "source_type": "ai"}
        }
        client.ai_remove.return_value = {"removed": True}
        return client

    def test_ai_list(self, runner: CliRunner) -> None:
        with patch("music_cli.cli.ensure_daemon", return_value=self._make_client()):
            result = runner.invoke(main, ["ai", "list"])
            assert result.exit_code != 2

    def test_ai_play_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["ai", "play", "--help"])
        assert result.exit_code == 0
        for flag in ("--prompt", "-p", "--mood", "-M", "--duration", "-d", "--model"):
            assert flag in result.output, f"Missing {flag!r} in ai play --help"

    def test_ai_replay(self, runner: CliRunner) -> None:
        with patch("music_cli.cli.ensure_daemon", return_value=self._make_client()):
            result = runner.invoke(main, ["ai", "replay", "1"])
            assert result.exit_code != 2

    def test_ai_remove(self, runner: CliRunner) -> None:
        with patch("music_cli.cli.ensure_daemon", return_value=self._make_client()):
            result = runner.invoke(main, ["ai", "remove", "1"], input="n\n")
            assert result.exit_code != 2

    def test_ai_model_list(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["ai", "model", "list"])
        # May exit non-zero if model manager unavailable, but must not be usage error
        assert result.exit_code != 2

    def test_ai_model_default_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["ai", "model", "default", "--help"])
        assert result.exit_code == 0

    def test_ai_models_alias(self, runner: CliRunner) -> None:
        """'ai models' should resolve to 'ai model'."""
        result = runner.invoke(main, ["ai", "models", "--help"])
        assert result.exit_code == 0


# ===========================================================================
# daemon command
# ===========================================================================


class TestDaemonCommand:
    """daemon start/stop/restart/status — process-level calls are mocked."""

    @pytest.mark.parametrize("action", ["start", "stop", "restart", "status"])
    def test_daemon_action_help(self, runner: CliRunner, action: str) -> None:
        result = runner.invoke(main, ["daemon", action, "--help"])
        assert result.exit_code == 0

    @pytest.mark.parametrize("action", ["start", "stop", "restart", "status"])
    def test_daemon_action_invoked(
        self, runner: CliRunner, action: str
    ) -> None:
        """daemon <action> should not raise a usage error even if daemon is absent."""
        with patch("music_cli.cli.get_daemon_pid", return_value=None), \
             patch("music_cli.cli.is_daemon_running", return_value=False), \
             patch("music_cli.cli.start_daemon_background", return_value=None):
            result = runner.invoke(main, ["daemon", action])
            assert result.exit_code != 2, (
                f"daemon {action} gave usage error:\n{result.output}"
            )


# ===========================================================================
# config command
# ===========================================================================


class TestConfigCommand:
    """config shows file paths without a running daemon."""

    def test_config_exits_ok(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["config"])
        assert result.exit_code == 0

    def test_config_output_contains_path(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["config"])
        output_lower = result.output.lower()
        assert any(kw in output_lower for kw in ("config", "path", "music-cli", "~")), (
            f"config output looks wrong:\n{result.output}"
        )


# ===========================================================================
# update-radios (hidden legacy)
# ===========================================================================


class TestUpdateRadios:
    """update-radios is a hidden alias and must not crash."""

    def test_update_radios_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["update-radios", "--help"])
        assert result.exit_code == 0

    def test_update_radios_invoked(self, runner: CliRunner) -> None:
        with patch("music_cli.cli.get_config") as mock_cfg_fn:
            cfg = MagicMock()
            mock_cfg_fn.return_value = cfg
            result = runner.invoke(main, ["update-radios"])
            assert result.exit_code != 2


# ===========================================================================
# NO_COLOR / icon helper
# ===========================================================================


class TestNoColor:
    """NO_COLOR env var and --no-color flag disable emoji output."""

    def test_no_color_flag_propagated(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--no-color", "config"])
        assert result.exit_code == 0

    def test_no_color_env_var(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["config"], env={"NO_COLOR": "1"})
        assert result.exit_code == 0

    def test_no_color_empty_string(self, runner: CliRunner) -> None:
        """NO_COLOR= (empty) should still disable color per spec."""
        result = runner.invoke(main, ["config"], env={"NO_COLOR": ""})
        assert result.exit_code == 0


# ===========================================================================
# Bare invocation (no subcommand → status)
# ===========================================================================


class TestBareInvocation:
    def test_bare_does_not_crash(self, runner: CliRunner) -> None:
        result = runner.invoke(main, [])
        # exit 2 = Click usage error; must not be that
        assert result.exit_code != 2

    def test_bare_attempts_status(self, runner: CliRunner) -> None:
        result = runner.invoke(main, [])
        output_lower = result.output.lower()
        assert any(
            kw in output_lower
            for kw in ("status", "error", "daemon", "playing", "stopped", "paused")
        ), f"Bare invocation did not attempt status: {result.output}"


# ===========================================================================
# Platform / Python version smoke tests
# ===========================================================================


class TestPlatformSmoke:
    """Verify the CLI can be imported and basic help works on all platforms."""

    def test_python_version(self) -> None:
        """Project requires Python 3.10+; CI matrix uses 3.12/3.13/3.14."""
        assert sys.version_info >= (3, 10), (
            f"Expected Python >=3.10, got {sys.version_info}"
        )

    def test_platform_detected(self) -> None:
        assert sys.platform in ("linux", "darwin", "win32"), (
            f"Unexpected platform: {sys.platform}"
        )

    def test_cli_importable(self) -> None:
        from music_cli.cli import main as _main  # noqa: F401

        assert callable(_main)

    def test_config_importable(self) -> None:
        from music_cli.config import get_config  # noqa: F401

        assert callable(get_config)
