"""Structural guarantees for the daemon split (#74, #75).

Pins the two contracts the F-CLEAN-008 refactor promised:

1. The command registry is built once and reused across requests (#74,
   F-PERF-006) — never rebuilt per IPC request.
2. Handlers live in their own module while the transport surface of
   ``music_cli.daemon`` stays import- and patch-compatible (#75,
   F-CLEAN-008).
"""

from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

import pytest

import music_cli.daemon as daemon_module
from music_cli.daemon import MusicDaemon, _parse_pid_record
from music_cli.daemon_handlers import COMMAND_HANDLERS
from tests.test_daemon import _DaemonTestHarness

EXPECTED_COMMANDS = {
    "play",
    "stop",
    "pause",
    "resume",
    "status",
    "next",
    "volume",
    "list_radios",
    "list_history",
    "ping",
    "ai_list",
    "ai_play",
    "ai_replay",
    "ai_remove",
    "youtube_history_list",
    "youtube_history_play",
    "youtube_history_remove",
    "youtube_history_clear",
    "shutdown",
}


def _make_daemon(tmp_path: Path):
    return _DaemonTestHarness.make_daemon(tmp_path)


class TestCommandRegistry:
    """The dispatch table is constructed once and reused (#74)."""

    def test_registry_is_read_only(self) -> None:
        assert isinstance(COMMAND_HANDLERS, MappingProxyType)
        with pytest.raises(TypeError):
            COMMAND_HANDLERS["teleport"] = "_cmd_teleport"  # type: ignore[index]

    def test_registry_covers_all_nineteen_commands(self) -> None:
        assert set(COMMAND_HANDLERS) == EXPECTED_COMMANDS

    async def test_same_mapping_object_reused_across_two_requests(self, tmp_path) -> None:
        """Two sequential IPC requests must not rebuild the dispatch table."""
        daemon = _make_daemon(tmp_path)
        mapping_before = daemon.COMMAND_HANDLERS

        first = await daemon._process_command("ping", {})
        second = await daemon._process_command("ping", {})

        assert first["status"] == "ok"
        assert second["message"] == "pong"
        assert daemon.COMMAND_HANDLERS is mapping_before
        assert MusicDaemon.COMMAND_HANDLERS is mapping_before
        # No per-instance copy materialised during dispatch.
        instance_state = vars(daemon)
        assert "COMMAND_HANDLERS" not in instance_state
        assert "handlers" not in instance_state

    def test_every_registered_handler_resolves_on_instances(self, tmp_path) -> None:
        daemon = _make_daemon(tmp_path)
        for command, handler_name in COMMAND_HANDLERS.items():
            handler = getattr(daemon, handler_name, None)
            assert callable(handler), f"{command} -> {handler_name} did not resolve"

    def test_handlers_live_in_their_own_module(self) -> None:
        for command, handler_name in COMMAND_HANDLERS.items():
            method = getattr(MusicDaemon, handler_name)
            assert method.__module__ == "music_cli.daemon_handlers", (
                f"handler for {command} escaped daemon_handlers: {method.__module__}"
            )

    async def test_dispatch_honours_instance_handler_overrides(self, tmp_path) -> None:
        """Instance-level handler replacement still wins over the registry."""

        async def recording_ping(args):
            return {"status": "ok", "overridden": True}

        daemon = _make_daemon(tmp_path)
        daemon._cmd_ping = recording_ping

        response = await daemon._process_command("ping", {})

        assert response == {"status": "ok", "overridden": True}


class TestTransportSurfaceCompat:
    """daemon.py keeps its public/patchable surface after the split (#75)."""

    def test_request_error_importable_from_daemon(self) -> None:
        from music_cli.ipc_framing import RequestError as CanonicalRequestError

        assert daemon_module.RequestError is CanonicalRequestError

    async def test_youtube_availability_flag_patchable_on_daemon(self, tmp_path) -> None:
        """Handlers resolve availability through music_cli.daemon at call time."""
        daemon = _make_daemon(tmp_path)

        with patch("music_cli.daemon.is_youtube_available", return_value=False):
            response = await daemon._process_command(
                "play", {"mode": "youtube", "source": "https://youtu.be/x"}
            )

        assert response == {
            "error": "YouTube playback not available. Install with: "
            "pip install 'coder-music-cli[youtube]'"
        }

    def test_daemon_module_stays_under_500_lines(self) -> None:
        source = Path(daemon_module.__file__).read_text(encoding="utf-8")
        line_count = len(source.splitlines())
        assert line_count < 500, f"music_cli/daemon.py grew to {line_count} lines"


class TestPidRecordParsing:
    """PID-file parsing extracted from get_daemon_pid keeps its contract (#68)."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ('{"pid": 42, "identity": "nonce"}', (42, "nonce")),
            ("12345", (12345, None)),  # legacy plain-int: pid without identity
            ("not-a-pid", (None, None)),
            ('{"pid": true, "identity": "n"}', (None, None)),  # bool is not a PID
            ('{"pid": 42}', (None, None)),  # missing identity can never verify
        ],
    )
    def test_parse_pid_record(self, raw: str, expected: tuple) -> None:
        assert _parse_pid_record(raw) == expected


class TestSharedAIHandlerPaths:
    """The AI handlers share generation setup and error mapping (#75)."""

    def test_unavailable_error_is_shared(self) -> None:
        from music_cli.daemon_handlers import AIHandlers

        error = AIHandlers._ai_unavailable_error()
        assert error == {
            "error": "AI generation not available. Install with: pip install 'coder-music-cli[ai]'"
        }
