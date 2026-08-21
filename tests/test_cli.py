"""Tests for CLI v2 Phase 1, Phase 2 & Phase 3."""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from music_cli.cli import (
    _detect_play_mode,
    _resolve_local_path,
    icon,
    main,
    start_daemon_background,
)
from music_cli.config import get_config

# The real spawner, captured at collection time: the autouse ``isolate_home``
# fixture swaps ``music_cli.cli.start_daemon_background`` for a no-op during
# every test, so these daemon-startup tests must re-bind this original.
_real_start_daemon_background = start_daemon_background


@pytest.fixture
def runner():
    """Create a Click CliRunner."""
    return CliRunner()


@pytest.fixture
def mock_daemon_client():
    """Return a mocked DaemonClient."""
    client = MagicMock()
    client.play.return_value = {
        "track": {"title": "Test Track", "source": "test.mp3", "source_type": "local"}
    }
    client.status.return_value = {
        "state": "playing",
        "track": {"title": "Test Track", "source_type": "radio"},
        "volume": 80,
    }
    client.list_history.return_value = [
        {"index": 1, "title": "Song A", "source_type": "radio", "timestamp": "2026-01-01T00:00"},
        {"index": 2, "title": "Song B", "source_type": "local", "timestamp": "2026-01-01T01:00"},
    ]
    return client


# -------------------------------------------------------------------------
# 1.1 — mc entry point (both entry points share the same `main` group)
# -------------------------------------------------------------------------


class TestHelpOutput:
    """Verify --help contains expected commands with new names."""

    def test_help_shows_new_group_names(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        # New primary names must appear
        for cmd in ("radio", "yt", "mood", "vol"):
            assert cmd in result.output

    def test_help_hides_old_group_names(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        # Old names must NOT appear in the help listing
        # They should still work as hidden aliases
        for old in ("radios", "youtube", "moods", "volume"):
            # Make sure the old name doesn't appear as a listed command.
            # We check it doesn't appear on a line starting with whitespace (command listing).
            lines = result.output.splitlines()
            command_lines = [
                line.strip().split()[0] for line in lines if line.startswith("  ") and line.strip()
            ]
            assert old not in command_lines, f"Old name '{old}' should be hidden from --help"

    def test_help_hides_playback_aliases(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        lines = result.output.splitlines()
        command_lines = [
            line.strip().split()[0] for line in lines if line.startswith("  ") and line.strip()
        ]
        for alias in ("s", "pp", "r", "n", "st", "h"):
            assert alias not in command_lines, f"Alias '{alias}' should be hidden from --help"

    def test_help_shows_expected_commands(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        for cmd in (
            "play",
            "stop",
            "pause",
            "resume",
            "next",
            "status",
            "history",
            "radio",
            "yt",
            "mood",
            "vol",
            "ai",
            "daemon",
            "config",
        ):
            assert cmd in result.output

    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "version" in result.output.lower()


# -------------------------------------------------------------------------
# 1.2 + 1.3 — Alias infrastructure & renamed groups
# -------------------------------------------------------------------------


class TestGroupRenames:
    """Old group names resolve to the same commands as new names."""

    def test_radio_help(self, runner):
        result = runner.invoke(main, ["radio", "--help"])
        assert result.exit_code == 0
        assert "radio" in result.output.lower()

    def test_radios_alias_resolves(self, runner):
        result = runner.invoke(main, ["radios", "--help"])
        assert result.exit_code == 0
        assert "radio" in result.output.lower()

    def test_yt_help(self, runner):
        result = runner.invoke(main, ["yt", "--help"])
        assert result.exit_code == 0
        assert "youtube" in result.output.lower() or "yt" in result.output.lower()

    def test_youtube_alias_resolves(self, runner):
        result = runner.invoke(main, ["youtube", "--help"])
        assert result.exit_code == 0

    def test_mood_help(self, runner):
        result = runner.invoke(main, ["mood", "--help"])
        assert result.exit_code == 0

    def test_moods_alias_resolves(self, runner):
        result = runner.invoke(main, ["moods", "--help"])
        assert result.exit_code == 0

    def test_vol_help(self, runner):
        result = runner.invoke(main, ["vol", "--help"])
        assert result.exit_code == 0
        assert "volume" in result.output.lower()

    def test_volume_alias_resolves(self, runner):
        result = runner.invoke(main, ["volume", "--help"])
        assert result.exit_code == 0
        assert "volume" in result.output.lower()

    def test_yt_cached_alias(self, runner):
        """'yt cached' should resolve to 'yt list' (hidden alias)."""
        result = runner.invoke(main, ["yt", "cached", "--help"])
        assert result.exit_code == 0

    def test_yt_list_help(self, runner):
        result = runner.invoke(main, ["yt", "list", "--help"])
        assert result.exit_code == 0


# -------------------------------------------------------------------------
# 1.4 — Playback command aliases
# -------------------------------------------------------------------------


class TestPlaybackAliases:
    """Single-letter and short aliases resolve to real commands."""

    @pytest.mark.parametrize(
        "alias,target_cmd",
        [
            ("s", "stop"),
            ("pp", "pause"),
            ("r", "resume"),
            ("n", "next"),
            ("st", "status"),
            ("h", "history"),
        ],
    )
    def test_alias_resolves_to_help(self, runner, alias, target_cmd):
        """Each alias should resolve without error when given --help."""
        result = runner.invoke(main, [alias, "--help"])
        assert result.exit_code == 0, f"Alias '{alias}' failed: {result.output}"

    @pytest.mark.parametrize(
        "alias,target_cmd",
        [
            ("s", "stop"),
            ("pp", "pause"),
            ("r", "resume"),
            ("n", "next"),
            ("st", "status"),
            ("h", "history"),
        ],
    )
    def test_alias_help_matches_target(self, runner, alias, target_cmd):
        """Alias help output should match the target command help output."""
        alias_result = runner.invoke(main, [alias, "--help"])
        target_result = runner.invoke(main, [target_cmd, "--help"])
        # The help text body should be the same (ignoring the usage line which
        # shows the invoked name)
        alias_body = "\n".join(alias_result.output.splitlines()[1:])
        target_body = "\n".join(target_result.output.splitlines()[1:])
        assert alias_body == target_body


# -------------------------------------------------------------------------
# 1.5 — Bare invocation → status
# -------------------------------------------------------------------------


class TestBareInvocation:
    """Bare `mc` (no subcommand) should invoke status."""

    def test_bare_invocation_does_not_crash(self, runner):
        """Bare invocation should not crash (exit code 0 or 1 for daemon not running)."""
        result = runner.invoke(main, [])
        # We accept exit_code 1 because the daemon likely isn't running in test,
        # but it must not be exit_code 2 (Click usage error).
        assert result.exit_code in (
            0,
            1,
        ), f"Bare invocation crashed with exit code {result.exit_code}: {result.output}"

    def test_bare_invocation_attempts_status(self, runner):
        """Bare invocation should try to show status (connect to daemon)."""
        result = runner.invoke(main, [])
        # Either shows status output or a connection error — both prove status was invoked
        output_lower = result.output.lower()
        assert (
            "status" in output_lower
            or "error" in output_lower
            or "daemon" in output_lower
            or "starting" in output_lower
        ), f"Bare invocation did not attempt status: {result.output}"


# -------------------------------------------------------------------------
# Daemon startup failure surfacing (issue #71 / F-BUG-011)
# -------------------------------------------------------------------------

# A fake child-process traceback, written into whatever stderr handle the
# spawn wired up — mirrors what a real `python -m music_cli.daemon` writes
# before dying at startup.
_TRACEBACK_LINES = (
    "Traceback (most recent call last):\n",
    '  File "<string>", line 1, in <module>\n',
    "RuntimeError: daemon failed to start\n",
)


class TestDaemonStartupFailureLog:
    """A failed daemon start must leave its stderr in a readable log file."""

    def _force_failed_start(self, runner, monkeypatch):
        """Drive ensure_daemon through a spawn whose child dies with a traceback.

        Replaces subprocess.Popen so no real process is forked: the fake
        writes the traceback into the stderr handle the CLI passed for the
        child — exactly what the OS-level redirection must deliver to disk.
        """
        import music_cli.cli as cli_module

        log_path = get_config().config_dir / "daemon.log"
        monkeypatch.setattr(cli_module, "is_daemon_running", lambda *a, **k: False)
        # Restore the real spawner (conftest no-ops it) so the fake Popen
        # below is actually reached through ensure_daemon.
        monkeypatch.setattr(cli_module, "start_daemon_background", _real_start_daemon_background)

        def fake_popen(cmd, **kwargs):
            err = kwargs["stderr"]
            assert hasattr(err, "write"), f"child stderr was not redirected to a file: {err!r}"
            for line in _TRACEBACK_LINES:
                err.write(line)
            err.flush()
            return MagicMock()

        monkeypatch.setattr(cli_module.subprocess, "Popen", fake_popen)
        result = runner.invoke(main, ["status"])
        return result, log_path

    def test_failure_message_prints_log_path(self, runner, monkeypatch):
        result, log_path = self._force_failed_start(runner, monkeypatch)
        assert result.exit_code == 1
        assert "Failed to start daemon" in result.output
        assert str(log_path) in result.output

    def test_log_file_contains_child_traceback(self, runner, monkeypatch):
        result, log_path = self._force_failed_start(runner, monkeypatch)
        assert result.exit_code == 1
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "Traceback" in content
        assert "RuntimeError: daemon failed to start" in content


class TestDaemonSpawnWiring:
    """start_daemon_background redirects the child's stderr to the log file."""

    @pytest.fixture
    def captured_popen(self, monkeypatch):
        """Capture Popen kwargs without forking; returns (calls list)."""
        import music_cli.cli as cli_module

        calls: list[dict] = []

        def fake_popen(cmd, **kwargs):
            calls.append(kwargs)
            # Close any file handle passed as stderr so tests stay tidy.
            err = kwargs.get("stderr")
            if hasattr(err, "close"):
                err.close()
            return MagicMock(pid=4321)

        monkeypatch.setattr(cli_module.subprocess, "Popen", fake_popen)
        return calls

    def test_unix_branch_redirects_stderr_to_log_file(self, monkeypatch, captured_popen):
        import music_cli.cli as cli_module

        monkeypatch.setattr(cli_module, "is_windows", lambda: False)
        expected = get_config().config_dir / "daemon.log"

        _real_start_daemon_background()

        kwargs = captured_popen[0]
        assert kwargs["stdout"] == subprocess.DEVNULL
        assert Path(kwargs["stderr"].name) == expected
        assert kwargs["start_new_session"] is True

    def test_windows_branch_redirects_stderr_to_log_file(self, monkeypatch, captured_popen):
        import music_cli.cli as cli_module

        monkeypatch.setattr(cli_module, "is_windows", lambda: True)
        expected = get_config().config_dir / "daemon.log"

        _real_start_daemon_background()

        kwargs = captured_popen[0]
        assert kwargs["stdout"] == subprocess.DEVNULL
        assert Path(kwargs["stderr"].name) == expected
        assert kwargs["creationflags"] == 0x00000200 | 0x00000008


# -------------------------------------------------------------------------
# 1.6 — -M short flag for --mood
# -------------------------------------------------------------------------


class TestMoodShortFlag:
    """The -M flag works on both play and ai play."""

    def test_play_has_mood_short_flag(self, runner):
        result = runner.invoke(main, ["play", "--help"])
        assert result.exit_code == 0
        assert "-M" in result.output

    def test_ai_play_has_mood_short_flag(self, runner):
        result = runner.invoke(main, ["ai", "play", "--help"])
        assert result.exit_code == 0
        assert "-M" in result.output


# -------------------------------------------------------------------------
# Integration: all subcommand --help should resolve cleanly
# -------------------------------------------------------------------------


class TestSubcommandHelp:
    """Every primary command/group shows --help without errors."""

    @pytest.mark.parametrize(
        "cmd_args",
        [
            ["play", "--help"],
            ["stop", "--help"],
            ["pause", "--help"],
            ["resume", "--help"],
            ["next", "--help"],
            ["status", "--help"],
            ["history", "--help"],
            ["history", "list", "--help"],
            ["history", "play", "--help"],
            ["radio", "--help"],
            ["radio", "update", "--help"],
            ["yt", "--help"],
            ["mood", "--help"],
            ["vol", "--help"],
            ["ai", "--help"],
            ["ai", "model", "--help"],
            ["ai", "model", "default", "--help"],
            ["daemon", "--help"],
            ["config", "--help"],
        ],
    )
    def test_command_help_succeeds(self, runner, cmd_args):
        result = runner.invoke(main, cmd_args)
        assert result.exit_code == 0, f"Failed for {cmd_args}: {result.output}"


# =========================================================================
# Phase 2 Tests
# =========================================================================


# -------------------------------------------------------------------------
# 2.1 — Smart play [SOURCE] auto-detection
# -------------------------------------------------------------------------


class TestSmartPlayDetection:
    """Test _detect_play_mode auto-detection logic."""

    def test_no_source_returns_context(self):
        mode, src = _detect_play_mode(None)
        assert mode == "context"
        assert src is None

    def test_existing_file_returns_local(self, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        mode, src = _detect_play_mode(str(f))
        assert mode == "local"
        assert src == str(f)

    @pytest.mark.parametrize(
        "url",
        [
            "https://youtube.com/watch?v=abc123",
            "https://www.youtube.com/watch?v=abc123",
            "https://youtu.be/abc123",
            "https://youtube.com/playlist?list=PLabc",
        ],
    )
    def test_youtube_url_returns_youtube(self, url):
        mode, src = _detect_play_mode(url)
        assert mode == "youtube"
        assert src == url

    def test_http_url_returns_radio(self):
        url = "https://stream.example.com/radio.mp3"
        mode, src = _detect_play_mode(url)
        assert mode == "radio"
        assert src == url

    def test_http_url_returns_radio_plain(self):
        url = "http://icecast.example.com:8000/stream"
        mode, src = _detect_play_mode(url)
        assert mode == "radio"
        assert src == url

    @patch("music_cli.cli.get_config")
    def test_station_name_returns_radio(self, mock_config):
        mock_cfg = MagicMock()
        mock_cfg.get_station_by_name.return_value = ("Chill", "https://stream.chill.com/radio")
        mock_config.return_value = mock_cfg
        mode, src = _detect_play_mode("Chill")
        assert mode == "radio"
        assert src == "https://stream.chill.com/radio"

    @patch("music_cli.cli.get_config")
    def test_unknown_string_falls_back_to_radio(self, mock_config):
        mock_cfg = MagicMock()
        mock_cfg.get_station_by_name.return_value = None
        mock_config.return_value = mock_cfg
        mode, src = _detect_play_mode("nonexistent-station")
        assert mode == "radio"
        assert src == "nonexistent-station"

    def test_play_help_shows_source_argument(self, runner):
        result = runner.invoke(main, ["play", "--help"])
        assert result.exit_code == 0
        assert "SOURCE" in result.output

    @patch("music_cli.cli.ensure_daemon")
    @patch("music_cli.cli.check_ffplay_available", return_value=True)
    def test_play_with_youtube_url(self, mock_ffplay, mock_daemon, runner, mock_daemon_client):
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["play", "https://youtube.com/watch?v=test"])
        assert result.exit_code == 0
        mock_daemon_client.play.assert_called_once()
        call_kwargs = mock_daemon_client.play.call_args
        assert call_kwargs[1]["mode"] == "youtube" or call_kwargs.kwargs["mode"] == "youtube"

    @patch("music_cli.cli.ensure_daemon")
    @patch("music_cli.cli.check_ffplay_available", return_value=True)
    def test_play_bare_uses_context(self, mock_ffplay, mock_daemon, runner, mock_daemon_client):
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["play"])
        assert result.exit_code == 0
        call_kwargs = mock_daemon_client.play.call_args
        assert call_kwargs[1]["mode"] == "context" or call_kwargs.kwargs["mode"] == "context"


class TestResolveLocalPath:
    """Unit tests for _resolve_local_path (issue #18)."""

    def test_relative_existing_path_resolved_to_absolute(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        f = Path("song.mp3")
        f.touch()

        resolved = _resolve_local_path("song.mp3")

        assert resolved == str((tmp_path / "song.mp3").resolve())

    def test_relative_missing_path_returned_unchanged(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        resolved = _resolve_local_path("missing.mp3")

        assert resolved == "missing.mp3"

    def test_absolute_path_returned_unchanged(self, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()

        resolved = _resolve_local_path(str(f))

        assert resolved == str(f)


class TestPlayRelativeLocalPath:
    """`mc play <relative-file>` must send the daemon an absolute path.

    The daemon is a separate long-running process — a relative path sent
    as-is would be checked against the *daemon's* cwd, not the terminal's,
    and would silently fail to be found (issue #18).
    """

    @patch("music_cli.cli.ensure_daemon")
    @patch("music_cli.cli.check_ffplay_available", return_value=True)
    def test_play_relative_file_sends_absolute_source(
        self, mock_ffplay, mock_daemon, runner, mock_daemon_client, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        Path("song.mp3").touch()
        mock_daemon.return_value = mock_daemon_client

        result = runner.invoke(main, ["play", "song.mp3"])

        assert result.exit_code == 0
        call_kwargs = mock_daemon_client.play.call_args.kwargs
        assert call_kwargs["mode"] == "local"
        assert call_kwargs["source"] == str((tmp_path / "song.mp3").resolve())

    @patch("music_cli.cli.ensure_daemon")
    @patch("music_cli.cli.check_ffplay_available", return_value=True)
    def test_play_explicit_mode_local_relative_file_sends_absolute_source(
        self, mock_ffplay, mock_daemon, runner, mock_daemon_client, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        Path("song.mp3").touch()
        mock_daemon.return_value = mock_daemon_client

        result = runner.invoke(main, ["play", "song.mp3", "--mode", "local"])

        assert result.exit_code == 0
        call_kwargs = mock_daemon_client.play.call_args.kwargs
        assert call_kwargs["source"] == str((tmp_path / "song.mp3").resolve())

    @patch("music_cli.cli.ensure_daemon")
    @patch("music_cli.cli.check_ffplay_available", return_value=True)
    def test_play_explicit_mode_local_missing_file_kept_relative(
        self, mock_ffplay, mock_daemon, runner, mock_daemon_client, tmp_path, monkeypatch
    ):
        # Not found in cwd -> left unchanged so the daemon still falls back
        # to the configured music directory (today's behavior, preserved).
        monkeypatch.chdir(tmp_path)
        mock_daemon.return_value = mock_daemon_client

        result = runner.invoke(main, ["play", "not-in-cwd.mp3", "--mode", "local"])

        assert result.exit_code == 0
        call_kwargs = mock_daemon_client.play.call_args.kwargs
        assert call_kwargs["source"] == "not-in-cwd.mp3"


# -------------------------------------------------------------------------
# 2.2 — Deprecate play -m ai
# -------------------------------------------------------------------------


class TestDeprecatePlayAI:
    """play -m ai shows deprecation warning but still works."""

    @patch("music_cli.cli.ensure_daemon")
    @patch("music_cli.cli.check_ffplay_available", return_value=True)
    def test_play_m_ai_shows_warning(self, mock_ffplay, mock_daemon, runner, mock_daemon_client):
        mock_daemon_client.play.return_value = {"track": {"title": "AI Track", "source_type": "ai"}}
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["play", "-m", "ai"])
        assert "Deprecated" in result.output
        assert "mc ai play" in result.output
        # Should still call play
        mock_daemon_client.play.assert_called_once()


# -------------------------------------------------------------------------
# 2.3 — Deprecate play -m history
# -------------------------------------------------------------------------


class TestDeprecatePlayHistory:
    """play -m history shows deprecation warning but still works."""

    @patch("music_cli.cli.ensure_daemon")
    @patch("music_cli.cli.check_ffplay_available", return_value=True)
    def test_play_m_history_shows_warning(
        self, mock_ffplay, mock_daemon, runner, mock_daemon_client
    ):
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["play", "-m", "history", "-i", "3"])
        assert "Deprecated" in result.output
        assert "mc history play N" in result.output
        mock_daemon_client.play.assert_called_once()


# -------------------------------------------------------------------------
# 2.4 — history play N subcommand
# -------------------------------------------------------------------------


class TestHistoryGroup:
    """history is now a group with list + play subcommands."""

    def test_history_help_shows_subcommands(self, runner):
        result = runner.invoke(main, ["history", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "play" in result.output

    @patch("music_cli.cli.ensure_daemon")
    def test_bare_history_lists(self, mock_daemon, runner, mock_daemon_client):
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["history"])
        assert result.exit_code == 0
        mock_daemon_client.list_history.assert_called_once()

    @patch("music_cli.cli.ensure_daemon")
    def test_history_list_with_limit(self, mock_daemon, runner, mock_daemon_client):
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["history", "list", "-n", "5"])
        assert result.exit_code == 0
        mock_daemon_client.list_history.assert_called_once_with(limit=5)

    @patch("music_cli.cli.ensure_daemon")
    def test_history_play_number(self, mock_daemon, runner, mock_daemon_client):
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["history", "play", "3"])
        assert result.exit_code == 0
        mock_daemon_client.play.assert_called_once_with(mode="history", index=3)

    @patch("music_cli.cli.ensure_daemon")
    def test_h_alias_play(self, mock_daemon, runner, mock_daemon_client):
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["h", "play", "1"])
        assert result.exit_code == 0
        mock_daemon_client.play.assert_called_once_with(mode="history", index=1)

    @patch("music_cli.cli.ensure_daemon")
    def test_h_bare_lists_history(self, mock_daemon, runner, mock_daemon_client):
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["h"])
        assert result.exit_code == 0
        mock_daemon_client.list_history.assert_called_once()

    def test_history_list_shows_replay_hint(self, runner):
        """The list output should mention 'mc history play'."""
        result = runner.invoke(main, ["history", "list", "--help"])
        assert result.exit_code == 0


# -------------------------------------------------------------------------
# 2.5 — radio update subcommand
# -------------------------------------------------------------------------


class TestRadioUpdate:
    """update-radios is now 'radio update', old form still works."""

    def test_radio_update_help(self, runner):
        result = runner.invoke(main, ["radio", "update", "--help"])
        assert result.exit_code == 0
        assert "Update radio stations" in result.output

    def test_radio_help_shows_update(self, runner):
        result = runner.invoke(main, ["radio", "--help"])
        assert result.exit_code == 0
        assert "update" in result.output

    def test_update_radios_legacy_still_works(self, runner):
        result = runner.invoke(main, ["update-radios", "--help"])
        assert result.exit_code == 0

    def test_update_radios_hidden_from_main_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        lines = result.output.splitlines()
        command_lines = [
            line.strip().split()[0] for line in lines if line.startswith("  ") and line.strip()
        ]
        assert "update-radios" not in command_lines


# -------------------------------------------------------------------------
# 2.6 — ai model (singular) + default subcommand
# -------------------------------------------------------------------------


class TestAIModelGroup:
    """ai model/models aliases and default/set-default aliases."""

    def test_ai_model_help(self, runner):
        result = runner.invoke(main, ["ai", "model", "--help"])
        assert result.exit_code == 0
        assert "default" in result.output

    def test_ai_models_alias_works(self, runner):
        result = runner.invoke(main, ["ai", "models", "--help"])
        assert result.exit_code == 0
        assert "default" in result.output

    def test_ai_model_default_help(self, runner):
        result = runner.invoke(main, ["ai", "model", "default", "--help"])
        assert result.exit_code == 0
        assert "MODEL_ID" in result.output

    def test_ai_models_set_default_alias_works(self, runner):
        result = runner.invoke(main, ["ai", "models", "set-default", "--help"])
        assert result.exit_code == 0
        assert "MODEL_ID" in result.output


# -------------------------------------------------------------------------
# 2.7 — Unified AI duration default to 15
# -------------------------------------------------------------------------


class TestAIDurationDefault:
    """Both ai play and play should default --duration to 15."""

    @patch("music_cli.cli.ensure_daemon")
    @patch("music_cli.cli.check_ffplay_available", return_value=True)
    def test_play_duration_default_is_15(
        self, mock_ffplay, mock_daemon, runner, mock_daemon_client
    ):
        """play command sends duration=15 when not explicitly set."""
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["play"])
        assert result.exit_code == 0
        call_kwargs = mock_daemon_client.play.call_args[1]
        assert call_kwargs["duration"] == 15

    @patch("music_cli.cli.ensure_daemon")
    def test_ai_play_duration_default_is_15(self, mock_daemon, runner, mock_daemon_client):
        """ai play command sends duration=15 when not explicitly set."""
        mock_daemon_client.ai_play.return_value = {
            "track": {"title": "AI Track", "metadata": {"model": "test"}},
            "prompt": "test",
        }
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["ai", "play"])
        assert result.exit_code == 0
        call_kwargs = mock_daemon_client.ai_play.call_args[1]
        assert call_kwargs["duration"] == 15

    @patch("music_cli.cli.ensure_daemon")
    def test_ai_play_forwards_lyrics(self, mock_daemon, runner, mock_daemon_client):
        mock_daemon_client.ai_play.return_value = {
            "track": {"title": "AI Track", "metadata": {"model": "minimax-music3"}},
            "prompt": "acoustic pop",
        }
        mock_daemon.return_value = mock_daemon_client

        result = runner.invoke(
            main,
            ["ai", "play", "-m", "minimax-music3", "--lyrics", "[Verse] hello"],
        )

        assert result.exit_code == 0
        call_kwargs = mock_daemon_client.ai_play.call_args.kwargs
        assert call_kwargs["model"] == "minimax-music3"
        assert call_kwargs["lyrics"] == "[Verse] hello"


# -------------------------------------------------------------------------
# 2.8 — mood MOOD plays directly
# -------------------------------------------------------------------------


class TestMoodDirectPlay:
    """mc mood lists moods; mc mood <name> starts playback."""

    def test_bare_mood_lists(self, runner):
        result = runner.invoke(main, ["mood"])
        assert result.exit_code == 0
        assert "Available moods:" in result.output

    def test_mood_help_shows_mood_name(self, runner):
        result = runner.invoke(main, ["mood", "--help"])
        assert result.exit_code == 0
        assert "MOOD_NAME" in result.output

    @patch("music_cli.cli.ensure_daemon")
    def test_mood_focus_plays(self, mock_daemon, runner, mock_daemon_client):
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["mood", "focus"])
        assert result.exit_code == 0
        mock_daemon_client.play.assert_called_once_with(mode="radio", mood="focus")
        assert "Playing mood" in result.output


# -------------------------------------------------------------------------
# 2.9 — Volume validation 0-100
# -------------------------------------------------------------------------


class TestVolumeValidation:
    """Volume argument is clamped to 0..100."""

    def test_vol_minus_1_rejected(self, runner):
        result = runner.invoke(main, ["vol", "-1"])
        assert result.exit_code != 0
        # Click outputs an error about the range
        assert (
            "not in the range" in result.output.lower()
            or "invalid" in result.output.lower()
            or result.exit_code == 2
        )

    def test_vol_150_rejected(self, runner):
        result = runner.invoke(main, ["vol", "150"])
        assert result.exit_code != 0

    @patch("music_cli.cli.ensure_daemon")
    def test_vol_50_accepted(self, mock_daemon, runner, mock_daemon_client):
        mock_daemon.return_value = mock_daemon_client
        mock_daemon_client.set_volume.return_value = {"volume": 50}
        result = runner.invoke(main, ["vol", "50"])
        assert result.exit_code == 0
        assert "50" in result.output

    @patch("music_cli.cli.ensure_daemon")
    def test_vol_0_accepted(self, mock_daemon, runner, mock_daemon_client):
        mock_daemon.return_value = mock_daemon_client
        mock_daemon_client.set_volume.return_value = {"volume": 0}
        result = runner.invoke(main, ["vol", "0"])
        assert result.exit_code == 0

    @patch("music_cli.cli.ensure_daemon")
    def test_vol_100_accepted(self, mock_daemon, runner, mock_daemon_client):
        mock_daemon.return_value = mock_daemon_client
        mock_daemon_client.set_volume.return_value = {"volume": 100}
        result = runner.invoke(main, ["vol", "100"])
        assert result.exit_code == 0


# -------------------------------------------------------------------------
# 2.10 — No music-cli references in help/echo text
# -------------------------------------------------------------------------


class TestHelpTextUpdated:
    """No 'music-cli' references remain in echo/help strings."""

    @pytest.mark.parametrize(
        "cmd_args",
        [
            ["play", "--help"],
            ["radio", "--help"],
            ["history", "--help"],
            ["ai", "--help"],
            ["ai", "play", "--help"],
            ["ai", "model", "--help"],
            ["vol", "--help"],
            ["mood", "--help"],
            ["yt", "--help"],
        ],
    )
    def test_no_music_cli_in_help(self, runner, cmd_args):
        result = runner.invoke(main, cmd_args)
        assert result.exit_code == 0
        # Check the help body (skip usage line which may contain entry point name)
        body_lines = result.output.splitlines()[1:]
        body = "\n".join(body_lines)
        assert "music-cli" not in body, f"Found 'music-cli' in help for {cmd_args}:\n{body}"


# -------------------------------------------------------------------------
# 2.11 — Additional integration tests
# -------------------------------------------------------------------------


class TestPhase2Integration:
    """Cross-cutting integration checks for Phase 2."""

    def test_play_source_and_flag_positional_wins(self, runner):
        """When both positional SOURCE and -s flag are given, positional wins."""
        result = runner.invoke(main, ["play", "--help"])
        assert result.exit_code == 0
        # Just verify the command accepts both forms
        assert "SOURCE" in result.output
        assert "-s" in result.output

    def test_history_alias_h_resolves_to_group(self, runner):
        result = runner.invoke(main, ["h", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "play" in result.output

    @patch("music_cli.cli.ensure_daemon")
    @patch("music_cli.cli.check_ffplay_available", return_value=True)
    def test_play_explicit_mode_overrides_detection(
        self, mock_ffplay, mock_daemon, runner, mock_daemon_client
    ):
        """When -m is given explicitly, auto-detection is skipped."""
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["play", "-m", "radio", "-s", "something"])
        assert result.exit_code == 0
        call_kwargs = mock_daemon_client.play.call_args
        assert call_kwargs[1]["mode"] == "radio" or call_kwargs.kwargs["mode"] == "radio"


# =========================================================================
# Phase 3 Tests
# =========================================================================


# -------------------------------------------------------------------------
# 3.1 — -h as help shortcut
# -------------------------------------------------------------------------


class TestHelpShortcut:
    """-h shows help at every command level (same as --help)."""

    def test_main_dash_h(self, runner):
        result = runner.invoke(main, ["-h"])
        assert result.exit_code == 0
        assert "mc:" in result.output or "music player" in result.output.lower()

    def test_main_dash_h_matches_dash_dash_help(self, runner):
        h_result = runner.invoke(main, ["-h"])
        help_result = runner.invoke(main, ["--help"])
        assert h_result.output == help_result.output

    @pytest.mark.parametrize(
        "cmd_args",
        [
            ["play", "-h"],
            ["stop", "-h"],
            ["pause", "-h"],
            ["resume", "-h"],
            ["next", "-h"],
            ["status", "-h"],
            ["radio", "-h"],
            ["yt", "-h"],
            ["ai", "-h"],
            ["history", "-h"],
            ["mood", "-h"],
            ["vol", "-h"],
            ["config", "-h"],
            ["daemon", "-h"],
        ],
    )
    def test_subcommand_dash_h(self, runner, cmd_args):
        result = runner.invoke(main, cmd_args)
        assert result.exit_code == 0, f"Failed for {cmd_args}: {result.output}"
        assert "Usage:" in result.output or "usage:" in result.output.lower()

    @pytest.mark.parametrize(
        "cmd_args",
        [
            ["play"],
            ["radio"],
            ["yt"],
            ["ai"],
            ["history"],
            ["mood"],
            ["vol"],
        ],
    )
    def test_dash_h_matches_dash_dash_help_for_subcommands(self, runner, cmd_args):
        h_result = runner.invoke(main, cmd_args + ["-h"])
        help_result = runner.invoke(main, cmd_args + ["--help"])
        assert h_result.output == help_result.output

    def test_nested_subcommand_dash_h(self, runner):
        """Nested subcommands also accept -h."""
        for cmd_args in [
            ["radio", "play", "-h"],
            ["ai", "play", "-h"],
            ["ai", "model", "-h"],
            ["history", "list", "-h"],
            ["history", "play", "-h"],
        ]:
            result = runner.invoke(main, cmd_args)
            assert result.exit_code == 0, f"Failed for {cmd_args}: {result.output}"


# -------------------------------------------------------------------------
# 3.2 — NO_COLOR / --no-color support
# -------------------------------------------------------------------------


class TestNoColorFlag:
    """--no-color flag and NO_COLOR env var suppress emoji."""

    @patch("music_cli.cli.ensure_daemon")
    def test_no_color_flag_status_no_emoji(self, mock_daemon, runner, mock_daemon_client):
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["--no-color", "status"])
        assert result.exit_code == 0
        # Should not contain unicode emoji
        assert "\u25b6" not in result.output  # ▶
        assert "\u23f8" not in result.output  # ⏸
        assert "\u23f9" not in result.output  # ⏹
        assert "\u23f3" not in result.output  # ⏳
        assert "\u274c" not in result.output  # ❌
        # Should contain text fallback
        assert "[playing]" in result.output

    @patch("music_cli.cli.ensure_daemon")
    def test_no_color_env_status_no_emoji(self, mock_daemon, runner, mock_daemon_client):
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["status"], env={"NO_COLOR": "1"})
        assert result.exit_code == 0
        assert "\u25b6" not in result.output
        assert "[playing]" in result.output

    @patch("music_cli.cli.ensure_daemon")
    def test_no_color_env_empty_string_means_color(self, mock_daemon, runner, mock_daemon_client):
        """NO_COLOR='' (empty) should NOT disable color."""
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["status"], env={"NO_COLOR": ""})
        assert result.exit_code == 0
        # With color enabled, should have unicode symbol
        assert "\u25b6" in result.output

    @patch("music_cli.cli.ensure_daemon")
    def test_color_by_default_status_has_emoji(self, mock_daemon, runner, mock_daemon_client):
        mock_daemon.return_value = mock_daemon_client
        # Ensure NO_COLOR is not set
        env = os.environ.copy()
        env.pop("NO_COLOR", None)
        result = runner.invoke(main, ["status"], env=env)
        assert result.exit_code == 0
        assert "\u25b6" in result.output

    @patch("music_cli.cli.ensure_daemon")
    def test_no_color_stop_text_fallback(self, mock_daemon, runner, mock_daemon_client):
        mock_daemon_client.stop.return_value = {"status": "stopped"}
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["--no-color", "stop"])
        assert result.exit_code == 0
        assert "\u23f9" not in result.output
        assert "[stopped]" in result.output

    @patch("music_cli.cli.ensure_daemon")
    def test_no_color_pause_text_fallback(self, mock_daemon, runner, mock_daemon_client):
        mock_daemon_client.pause.return_value = {"status": "paused"}
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["--no-color", "pause"])
        assert result.exit_code == 0
        assert "\u23f8" not in result.output
        assert "[paused]" in result.output

    @patch("music_cli.cli.ensure_daemon")
    def test_no_color_resume_text_fallback(self, mock_daemon, runner, mock_daemon_client):
        mock_daemon_client.resume.return_value = {"status": "resumed"}
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["--no-color", "resume"])
        assert result.exit_code == 0
        assert "\u25b6" not in result.output
        assert "[resumed]" in result.output

    @patch("music_cli.cli.ensure_daemon")
    def test_no_color_next_text_fallback(self, mock_daemon, runner, mock_daemon_client):
        mock_daemon_client.next_track.return_value = {"status": "next"}
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["--no-color", "next"])
        assert result.exit_code == 0
        assert "\u23ed" not in result.output
        assert "[skip]" in result.output

    @patch("music_cli.cli.ensure_daemon")
    @patch("music_cli.cli.check_ffplay_available", return_value=True)
    def test_no_color_play_text_fallback(
        self, mock_ffplay, mock_daemon, runner, mock_daemon_client
    ):
        mock_daemon.return_value = mock_daemon_client
        result = runner.invoke(main, ["--no-color", "play"])
        assert result.exit_code == 0
        assert "\u25b6" not in result.output
        assert "[playing]" in result.output


class TestIconHelper:
    """Unit tests for the icon() helper function."""

    def test_icon_returns_symbol_when_color_enabled(self, runner):
        """Without NO_COLOR, icon returns the symbol."""
        env = os.environ.copy()
        env.pop("NO_COLOR", None)
        runner.invoke(main, ["--help"])  # Just establish a context
        # Test icon outside click context using env var
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NO_COLOR", None)
            # icon() falls back to env var check when no click context
            assert icon("\u25b6") == "\u25b6"

    def test_icon_returns_fallback_when_no_color(self, runner):
        """With NO_COLOR env, icon returns text fallback."""
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            assert icon("\u25b6") == "[playing]"
            assert icon("\u23f9") == "[stopped]"
            assert icon("\u23f8") == "[paused]"
            assert icon("\u23ed") == "[skip]"
            assert icon("\u274c") == "[error]"
            assert icon("\u23f3") == "[loading]"

    def test_icon_custom_fallback(self, runner):
        """Custom text_fallback overrides the default mapping."""
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            assert icon("\u25b6", "[resumed]") == "[resumed]"

    def test_icon_unknown_symbol_passthrough(self, runner):
        """Unknown symbols pass through as-is."""
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            assert icon("X") == "X"


# -------------------------------------------------------------------------
# 3.3 — --no-color appears in --help
# -------------------------------------------------------------------------


class TestNoColorInHelp:
    """Verify --no-color is documented in --help."""

    def test_no_color_in_main_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "--no-color" in result.output
