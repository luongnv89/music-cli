"""Tests for the daemon module, especially cross-platform PID checking."""

from pathlib import Path
from unittest.mock import MagicMock, patch

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
