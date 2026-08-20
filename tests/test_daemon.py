"""Tests for the daemon module, especially cross-platform PID checking."""

import asyncio
import json
import os
import stat
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from music_cli.daemon import _pid_alive, get_daemon_pid


class TestPidAlive:
    """Tests for the _pid_alive helper function."""

    def test_pid_alive_unix_running(self, tmp_path: Path) -> None:
        """On Unix, os.kill(pid, 0) succeeds for a running process."""
        with patch("music_cli.platform.is_unix", return_value=True):
            with patch("os.kill") as mock_kill:
                result = _pid_alive(1234)
                assert result is True
                mock_kill.assert_called_once_with(1234, 0)

    def test_pid_alive_unix_not_running(self, tmp_path: Path) -> None:
        """On Unix, os.kill raises ProcessLookupError for a dead process."""
        with patch("music_cli.platform.is_unix", return_value=True):
            with patch("os.kill", side_effect=ProcessLookupError):
                result = _pid_alive(1234)
                assert result is False

    def test_pid_alive_unix_permission_error(self, tmp_path: Path) -> None:
        """On Unix, PermissionError means process exists but we can't signal it."""
        with patch("music_cli.platform.is_unix", return_value=True):
            with patch("os.kill", side_effect=PermissionError):
                result = _pid_alive(1234)
                assert result is True

    def test_pid_alive_windows_running(self, tmp_path: Path) -> None:
        """On Windows, OpenProcess succeeds for a running process."""
        mock_handle = MagicMock()
        with patch("music_cli.platform.is_unix", return_value=False):
            with patch.dict("sys.modules", {"ctypes": self._make_fake_ctypes(mock_handle)}):
                result = _pid_alive(1234)
                assert result is True

    def test_pid_alive_windows_not_running(self, tmp_path: Path) -> None:
        """On Windows, OpenProcess returns None for a dead process."""
        with patch("music_cli.platform.is_unix", return_value=False):
            with patch.dict("sys.modules", {"ctypes": self._make_fake_ctypes(None)}):
                result = _pid_alive(1234)
                assert result is False

    @staticmethod
    def _make_fake_ctypes(open_process_result):
        """Create a fake ctypes module with mocked Windows API calls."""
        fake_ctypes = MagicMock()
        fake_windll = MagicMock()
        fake_kernel32 = MagicMock()
        fake_kernel32.OpenProcess.return_value = open_process_result
        fake_kernel32.CloseHandle = MagicMock()
        fake_windll.kernel32 = fake_kernel32
        fake_ctypes.windll = fake_windll
        return fake_ctypes


class TestGetDaemonPid:
    """Tests for the get_daemon_pid function."""

    def test_no_pid_file(self, tmp_path: Path) -> None:
        """When no PID file exists, return None."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        pid_file = config_dir / "music-cli.pid"

        with patch("music_cli.daemon.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.pid_file = pid_file
            mock_cfg.socket_path = config_dir / "music-cli.sock"
            mock_config.return_value = mock_cfg
            result = get_daemon_pid()
            assert result is None

    def test_stale_pid_file_cleaned_up(self, tmp_path: Path) -> None:
        """When PID file points to a dead process, clean up and return None."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        pid_file = config_dir / "music-cli.pid"
        socket_path = config_dir / "music-cli.sock"
        pid_file.write_text("99999")
        socket_path.touch()

        with patch("music_cli.daemon.get_config") as mock_config:
            with patch("music_cli.daemon._pid_alive", return_value=False):
                with patch("music_cli.platform.is_unix", return_value=True):
                    mock_cfg = MagicMock()
                    mock_cfg.pid_file = pid_file
                    mock_cfg.socket_path = socket_path
                    mock_config.return_value = mock_cfg
                    result = get_daemon_pid()
                    assert result is None
                    assert not pid_file.exists()
                    assert not socket_path.exists()

    def test_live_pid_returns_pid(self, tmp_path: Path) -> None:
        """When PID file points to a live process, return the PID."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        pid_file = config_dir / "music-cli.pid"
        pid_file.write_text("12345")

        with patch("music_cli.daemon.get_config") as mock_config:
            with patch("music_cli.daemon._pid_alive", return_value=True):
                mock_cfg = MagicMock()
                mock_cfg.pid_file = pid_file
                mock_cfg.socket_path = config_dir / "music-cli.sock"
                mock_config.return_value = mock_cfg
                result = get_daemon_pid()
                assert result == 12345
                assert pid_file.exists()

    def test_invalid_pid_file_content(self, tmp_path: Path) -> None:
        """When PID file has non-numeric content, clean up and return None."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        pid_file = config_dir / "music-cli.pid"
        pid_file.write_text("not-a-pid")

        with patch("music_cli.daemon.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.pid_file = pid_file
            mock_cfg.socket_path = config_dir / "music-cli.sock"
            mock_config.return_value = mock_cfg
            result = get_daemon_pid()
            assert result is None
            assert not pid_file.exists()

    def test_socket_not_cleaned_on_windows(self, tmp_path: Path) -> None:
        """On Windows, socket file should NOT be cleaned up (Windows uses TCP)."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        pid_file = config_dir / "music-cli.pid"
        socket_path = config_dir / "music-cli.sock"
        pid_file.write_text("99999")
        socket_path.touch()

        with patch("music_cli.daemon.get_config") as mock_config:
            with patch("music_cli.daemon._pid_alive", return_value=False):
                with patch("music_cli.platform.is_unix", return_value=False):
                    mock_cfg = MagicMock()
                    mock_cfg.pid_file = pid_file
                    mock_cfg.socket_path = socket_path
                    mock_config.return_value = mock_cfg
                    result = get_daemon_pid()
                    assert result is None
                    assert not pid_file.exists()
                    # Socket should still exist on Windows
                    assert socket_path.exists()


class _DaemonTestHarness:
    """Build a MusicDaemon without heavy player/source dependencies."""

    @staticmethod
    def make_daemon(tmp_path: Path, token: str = "test-token") -> Any:  # noqa: S107
        from music_cli.daemon import MusicDaemon

        daemon = MusicDaemon.__new__(MusicDaemon)
        daemon._auth_token = token
        return daemon


async def _roundtrip(port: int, payload: dict) -> dict:
    """Send one JSON request over TCP and return the JSON response."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(json.dumps(payload).encode())
    await writer.drain()
    data = await asyncio.wait_for(reader.read(), timeout=5.0)
    writer.close()
    try:
        await writer.wait_closed()
    except (ConnectionError, OSError):
        pass
    return json.loads(data)


class TestAuthTokenEnforcement:
    """Every daemon request must carry a valid per-run token (#47)."""

    async def _serve(self, daemon) -> tuple[asyncio.AbstractServer, int]:
        server = await asyncio.start_server(daemon._handle_client, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        return server, port

    @pytest_asyncio.fixture
    async def running_server(self, tmp_path: Path):
        daemon = _DaemonTestHarness.make_daemon(tmp_path)
        server, port = await self._serve(daemon)
        yield daemon, port
        server.close()
        await server.wait_closed()

    async def test_missing_token_rejected(self, running_server) -> None:
        daemon, port = running_server
        response = await _roundtrip(port, {"command": "ping", "args": {}})
        assert response == {"error": "Unauthorized"}

    async def test_wrong_token_rejected(self, running_server) -> None:
        daemon, port = running_server
        response = await _roundtrip(port, {"command": "ping", "args": {}, "token": "wrong-token"})
        assert response == {"error": "Unauthorized"}

    async def test_valid_token_reaches_handler(self, running_server) -> None:
        daemon, port = running_server
        response = await _roundtrip(
            port, {"command": "ping", "args": {}, "token": daemon._auth_token}
        )
        assert response.get("status") == "ok"

    async def test_non_string_token_rejected(self, running_server) -> None:
        daemon, port = running_server
        response = await _roundtrip(port, {"command": "ping", "args": {}, "token": 123})
        assert response == {"error": "Unauthorized"}

    def test_issue_auth_token_persists_owner_only(self, tmp_path: Path) -> None:
        import stat as stat_module

        from music_cli.config import Config

        config = Config(config_dir=tmp_path / "cfg")
        daemon = _DaemonTestHarness.make_daemon(tmp_path)
        daemon.config = config

        token = daemon._issue_auth_token()

        assert token == daemon._auth_token
        assert len(token) >= 32
        assert config.read_auth_token() == token
        assert stat_module.S_IMODE(config.auth_token_file.stat().st_mode) == 0o600

    def test_issue_auth_token_rotates(self, tmp_path: Path) -> None:
        from music_cli.config import Config

        config = Config(config_dir=tmp_path / "cfg")
        daemon = _DaemonTestHarness.make_daemon(tmp_path)
        daemon.config = config

        first = daemon._issue_auth_token()
        second = daemon._issue_auth_token()
        assert first != second
        assert config.read_auth_token() == second


class TestUnixSocketPermissions:
    """The Unix socket must never be world-accessible (#48)."""

    @pytest.mark.skipif(os.name != "posix", reason="Unix sockets only")
    async def test_socket_owner_only_immediately_after_start(self, tmp_path: Path) -> None:
        from music_cli.platform.ipc import UnixIPCServer

        async def noop_handler(reader, writer):
            writer.close()

        socket_path = tmp_path / "music-cli.sock"
        server = UnixIPCServer()
        await server.start(noop_handler, socket_path)
        try:
            mode = stat.S_IMODE(socket_path.stat().st_mode)
            assert mode & 0o077 == 0, f"socket is group/world accessible: {oct(mode)}"
            assert mode & 0o700 == 0o600
        finally:
            await server.stop()


class TestGenericErrorResponses:
    """Client-visible errors must not leak exception text or paths (#48)."""

    async def test_no_filesystem_path_in_error(self, tmp_path: Path) -> None:
        daemon = _DaemonTestHarness.make_daemon(tmp_path)

        async def boom(args):
            raise RuntimeError(f"cannot read {tmp_path / 'secret.wav'}")

        daemon._cmd_status = boom

        server = await asyncio.start_server(daemon._handle_client, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            response = await _roundtrip(
                port,
                {"command": "status", "args": {}, "token": daemon._auth_token},
            )
        finally:
            server.close()
            await server.wait_closed()

        assert response["error"] == "Internal error while processing command"
        assert str(tmp_path) not in json.dumps(response)
