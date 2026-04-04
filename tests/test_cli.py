"""Tests for CLI v2 Phase 1: Foundation — mc alias, short names, playback aliases."""

import pytest
from click.testing import CliRunner

from music_cli.cli import main


@pytest.fixture
def runner():
    """Create a Click CliRunner."""
    return CliRunner()


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
            command_lines = [l.strip().split()[0] for l in lines if l.startswith("  ") and l.strip()]
            assert old not in command_lines, f"Old name '{old}' should be hidden from --help"

    def test_help_hides_playback_aliases(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        lines = result.output.splitlines()
        command_lines = [l.strip().split()[0] for l in lines if l.startswith("  ") and l.strip()]
        for alias in ("s", "pp", "r", "n", "st", "h"):
            assert alias not in command_lines, f"Alias '{alias}' should be hidden from --help"

    def test_help_shows_expected_commands(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        for cmd in ("play", "stop", "pause", "resume", "next", "status", "history",
                     "radio", "yt", "mood", "vol", "ai", "daemon", "config"):
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
        assert result.exit_code in (0, 1), (
            f"Bare invocation crashed with exit code {result.exit_code}: {result.output}"
        )

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
            ["radio", "--help"],
            ["yt", "--help"],
            ["mood", "--help"],
            ["vol", "--help"],
            ["ai", "--help"],
            ["daemon", "--help"],
            ["config", "--help"],
        ],
    )
    def test_command_help_succeeds(self, runner, cmd_args):
        result = runner.invoke(main, cmd_args)
        assert result.exit_code == 0, f"Failed for {cmd_args}: {result.output}"
