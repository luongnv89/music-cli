"""Tests for the F-CLEAN-007 CLI package split and client transport/protocol split.

Guards the structural contracts the refactor promised:

- ``music_cli.cli`` stays a drop-in facade: every historical name still imports,
  and patching ``music_cli.cli.runtime.*`` reaches command implementations.
- No module under ``music_cli/cli/`` exceeds 400 lines.
- ``play`` keeps a thin Click callback (≤4 params) backed by ``PlayOptions``.
- ``DaemonClient.send_command`` delegates to separate protocol/transport helpers
  whose behaviour is pinned here.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

import music_cli.cli as cli_facade
import music_cli.cli.playback as playback_module
import music_cli.client as client_module
from music_cli.cli import main
from music_cli.cli.playback import PlayOptions
from music_cli.client import AI_TIMEOUT, DEFAULT_TIMEOUT, DaemonClient

CLI_PACKAGE_DIR = Path(cli_facade.__file__).parent
MAX_MODULE_LINES = 400


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click CliRunner."""
    return CliRunner()


# -------------------------------------------------------------------------
# Facade re-exports (backward compatibility surface)
# -------------------------------------------------------------------------


class TestFacadeReExports:
    @pytest.mark.parametrize(
        "name",
        [
            "main",
            "ensure_daemon",
            "start_daemon_background",
            "ComposingAnimation",
            "AliasedGroup",
            "icon",
            "_detect_play_mode",
            "_resolve_local_path",
            "_register_alias",
            "get_random_quote",
            "INSPIRATIONAL_QUOTES",
        ],
    )
    def test_historical_names_still_importable(self, name: str) -> None:
        assert hasattr(cli_facade, name), f"music_cli.cli lost {name!r} in the split"

    def test_main_is_aliased_group(self) -> None:
        assert isinstance(main, cli_facade.AliasedGroup)

    def test_runtime_patch_reaches_commands(self, runner: CliRunner) -> None:
        """The conftest contract: patching runtime.ensure_daemon drives commands."""
        client = MagicMock()
        client.status.return_value = {
            "state": "stopped",
            "volume": 50,
        }
        with (
            patch("music_cli.cli.runtime.ensure_daemon", return_value=client),
            patch("music_cli.cli.runtime.is_daemon_running", return_value=True),
        ):
            result = runner.invoke(main, ["st"])
        assert result.exit_code == 0
        assert "Status:" in result.output


# -------------------------------------------------------------------------
# Package layout (issue #77 acceptance criterion)
# -------------------------------------------------------------------------


class TestPackageLayout:
    @pytest.mark.parametrize(
        "module_path",
        sorted(p for p in CLI_PACKAGE_DIR.glob("*.py")),
        ids=lambda p: p.name,
    )
    def test_no_module_exceeds_400_lines(self, module_path: Path) -> None:
        line_count = len(module_path.read_text(encoding="utf-8").splitlines())
        assert line_count <= MAX_MODULE_LINES, (
            f"{module_path.name} grew to {line_count} lines (max {MAX_MODULE_LINES})"
        )

    def test_command_group_modules_exist(self) -> None:
        expected = {"ai.py", "radio.py", "history.py", "youtube.py", "runtime.py"}
        actual = {p.name for p in CLI_PACKAGE_DIR.glob("*.py")}
        missing = expected - actual
        assert not missing, f"expected command-group modules missing: {sorted(missing)}"


# -------------------------------------------------------------------------
# Thin play() callback backed by PlayOptions
# -------------------------------------------------------------------------


class TestPlayOptionsGrouping:
    def test_positional_source_wins_over_legacy_flag(self) -> None:
        opts = PlayOptions.from_click(source="song.mp3", source_flag="ignored.mp3")
        assert opts.source == "song.mp3"

    def test_flag_used_when_no_positional_source(self) -> None:
        opts = PlayOptions.from_click(source=None, source_flag="flag.mp3")
        assert opts.source == "flag.mp3"

    def test_defaults(self) -> None:
        opts = PlayOptions.from_click()
        assert opts == PlayOptions(
            source=None, mode=None, mood=None, auto=False, duration=15, index=None
        )

    def test_callback_parameter_count(self) -> None:
        """play's Click callback takes ≤4 params (issue #76 acceptance criterion)."""
        import inspect

        params = list(inspect.signature(playback_module.play.callback).parameters)
        assert len(params) <= 4


# -------------------------------------------------------------------------
# DaemonClient protocol/transport split
# -------------------------------------------------------------------------


@pytest.fixture()
def ipc(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake_ipc = MagicMock()
    monkeypatch.setattr(client_module, "get_ipc_client", lambda: fake_ipc)
    return fake_ipc


class TestSendCommandSplit:
    def test_default_timeout_selection(self, ipc: MagicMock) -> None:
        client = DaemonClient()
        assert client._default_timeout("ai_play", {}) == AI_TIMEOUT
        assert client._default_timeout("status", {}) == DEFAULT_TIMEOUT

    def test_explicit_timeout_beats_derived(self, ipc: MagicMock) -> None:
        client = DaemonClient()
        sock = MagicMock()
        sock.recv.side_effect = lambda *a: b""
        ipc.connect.return_value = sock

        client.send_command("ai_play", {}, timeout=1.5)

        assert ipc.connect.call_args[0][1] == 1.5

    def test_build_request_carries_token_and_args(self, ipc: MagicMock) -> None:
        client = DaemonClient()
        request = client._build_request("play", {"mode": "radio"})
        assert set(request) == {"command", "args", "token"}
        assert request["command"] == "play"
        assert request["args"] == {"mode": "radio"}

    def test_round_trip_streams_until_eof_and_closes(self, ipc: MagicMock) -> None:
        client = DaemonClient()
        payload = [b'{"sta', b'tus": 1}', b"", b"never-read"]
        sock = MagicMock()
        stream = iter(payload)
        sock.recv.side_effect = lambda *a: next(stream)
        ipc.connect.return_value = sock

        data = client._round_trip({"command": "status"}, DEFAULT_TIMEOUT)

        assert data == b'{"status": 1}'
        sock.close.assert_called_once()

    def test_decode_response_error_mapping(self, ipc: MagicMock) -> None:
        client = DaemonClient()

        too_large = b"x" * client_module.MAX_RESPONSE_SIZE
        empty = b""
        invalid = b"{not-json"

        assert client._decode_response(too_large) == {"error": "Response too large from daemon"}
        assert client._decode_response(empty) == {"error": "Empty response from daemon"}
        assert client._decode_response(invalid) == {"error": "Invalid response from daemon"}
        assert client._decode_response(b'{"ok": true}') == {"ok": True}

    def test_send_command_end_to_end_through_split(self, ipc: MagicMock) -> None:
        client = DaemonClient()
        response = {"status": "ok"}
        sock = MagicMock()
        stream = iter([json.dumps(response).encode(), b""])
        sock.recv.side_effect = lambda *a: next(stream)
        ipc.connect.return_value = sock

        result = client.send_command("ping")

        sent = json.loads(sock.sendall.call_args[0][0])
        assert sent["command"] == "ping"
        assert result == response


# -------------------------------------------------------------------------
# Hidden aliases survive the split (issue #77 acceptance criterion)
# -------------------------------------------------------------------------


class TestAliasesResolvePostSplit:
    @pytest.mark.parametrize(
        ("argv", "needle"),
        [
            (["radios", "--help"], "Manage radio stations"),
            (["youtube", "--help"], "Manage cached YouTube audio"),
            (["moods"], "Available moods"),
            (["h", "--help"], "Show and replay playback history"),
        ],
    )
    def test_hidden_aliases_resolve(self, runner: CliRunner, argv: list[str], needle: str) -> None:
        result = runner.invoke(main, argv)
        assert result.exit_code == 0
        assert needle in result.output
