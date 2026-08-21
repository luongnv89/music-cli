"""Tests for the daemon module, especially cross-platform PID checking."""

import asyncio
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from music_cli.daemon import (
    _pid_alive,
    _probe_daemon_identity,
    get_daemon_pid,
    is_daemon_running,
)


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
        """A legacy plain-int PID file can never prove identity — stale."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        pid_file = config_dir / "music-cli.pid"
        socket_path = config_dir / "music-cli.sock"
        pid_file.write_text("12345")
        socket_path.touch()

        with patch("music_cli.daemon.get_config") as mock_config:
            with patch("music_cli.daemon._pid_alive", return_value=True):
                mock_cfg = MagicMock()
                mock_cfg.pid_file = pid_file
                mock_cfg.socket_path = socket_path
                mock_config.return_value = mock_cfg
                result = get_daemon_pid()
                assert result is None
                assert not pid_file.exists()

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


class TestIdentityLiveness:
    """Liveness requires identity, not just PID existence (#68)."""

    @staticmethod
    def _write_pid_file(pid_file: Path, pid: int, identity: str | None) -> None:
        if identity is None:
            pid_file.write_text(str(pid))
        else:
            pid_file.write_text(json.dumps({"pid": pid, "identity": identity}))

    @staticmethod
    def _patched_config(config_dir: Path, pid_file: Path):
        mock_cfg = MagicMock()
        mock_cfg.pid_file = pid_file
        mock_cfg.socket_path = config_dir / "music-cli.sock"
        mock_cfg.read_auth_token.return_value = None
        return patch("music_cli.daemon.get_config", return_value=mock_cfg)

    async def test_ping_echoes_run_identity(self, tmp_path: Path) -> None:
        daemon = _DaemonTestHarness.make_daemon(tmp_path)
        server = await asyncio.start_server(daemon._handle_client, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            response = await _roundtrip(
                port, {"command": "ping", "args": {}, "token": daemon._auth_token}
            )
        finally:
            server.close()
            await server.wait_closed()
        assert response["status"] == "ok"
        assert response["identity"] == daemon._identity

    def test_live_unrelated_process_is_not_running(self, tmp_path: Path) -> None:
        """A PID file naming a live non-daemon process is stale (#68)."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        pid_file = config_dir / "music-cli.pid"

        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            assert _pid_alive(proc.pid), "test setup: sleeper must be alive"
            self._write_pid_file(pid_file, proc.pid, "stale-nonce")
            with self._patched_config(config_dir, pid_file):
                assert get_daemon_pid() is None
                assert not is_daemon_running()
                assert not pid_file.exists()
        finally:
            proc.terminate()
            proc.wait(timeout=10)

    def test_identity_match_returns_pid(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        pid_file = config_dir / "music-cli.pid"
        self._write_pid_file(pid_file, 12345, "run-nonce")

        with self._patched_config(config_dir, pid_file):
            with patch("music_cli.daemon._pid_alive", return_value=True):
                with patch(
                    "music_cli.daemon._probe_daemon_identity",
                    return_value="run-nonce",
                ):
                    assert get_daemon_pid() == 12345
                    assert pid_file.exists()

    def test_identity_mismatch_cleans_up(self, tmp_path: Path) -> None:
        """A live process that answers with a foreign identity is not ours."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        pid_file = config_dir / "music-cli.pid"
        socket_path = config_dir / "music-cli.sock"
        self._write_pid_file(pid_file, 12345, "recorded-nonce")
        socket_path.touch()

        with self._patched_config(config_dir, pid_file):
            with patch("music_cli.daemon._pid_alive", return_value=True):
                with patch(
                    "music_cli.daemon._probe_daemon_identity",
                    return_value="someone-else",
                ):
                    with patch("music_cli.platform.is_unix", return_value=True):
                        assert get_daemon_pid() is None
                        assert not pid_file.exists()
                        assert not socket_path.exists()

    def test_probe_fails_when_nothing_listens(self, tmp_path: Path) -> None:
        """The real probe returns None against a socket path with no listener."""
        assert _probe_daemon_identity(tmp_path / "no-such.sock", None) is None

    @pytest.mark.skipif(
        os.name == "nt",
        reason="socket-file leftovers are Unix-only; the recycled-PID core is "
        "covered cross-platform by test_live_unrelated_process_is_not_running",
    )
    def test_recycled_pid_scenario_end_to_end(self, tmp_path: Path) -> None:
        """Unclean exit + PID recycling: stale file cleaned, daemon restartable.

        Simulates the failure the issue describes: the PID file survives an
        unclean exit and names a live unrelated process. Before #68 the
        daemon was considered running forever; now the file is cleaned up so
        ``ensure_daemon`` can start a fresh daemon.
        """
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        pid_file = config_dir / "music-cli.pid"
        socket_path = config_dir / "music-cli.sock"
        socket_path.touch()  # leftover socket from the unclean exit

        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 5
            while not _pid_alive(proc.pid):
                assert time.monotonic() < deadline, "sleeper never came up"
                time.sleep(0.05)
            self._write_pid_file(pid_file, proc.pid, "dead-daemon-nonce")
            with self._patched_config(config_dir, pid_file):
                with patch("music_cli.platform.is_unix", return_value=True):
                    assert get_daemon_pid() is None
                    assert not pid_file.exists(), "stale PID file must be removed"
                    assert not socket_path.exists(), "leftover socket must be removed"
        finally:
            proc.terminate()
            proc.wait(timeout=10)


class _DaemonTestHarness:
    """Build a MusicDaemon without heavy player/source dependencies."""

    @staticmethod
    def make_daemon(tmp_path: Path, token: str = "test-token") -> Any:  # noqa: S107
        from music_cli.daemon import MusicDaemon

        daemon = MusicDaemon.__new__(MusicDaemon)
        daemon._auth_token = token
        # Attributes __init__ normally provides and _process_command touches.
        daemon._command_lock = asyncio.Lock()
        daemon._background_tasks = set()
        daemon._identity = "test-identity"
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

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
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
    async def test_socket_owner_only_immediately_after_start(self) -> None:
        import shutil
        import tempfile

        from music_cli.platform.ipc import UnixIPCServer

        async def noop_handler(reader, writer):
            writer.close()

        # macOS limits sun_path to 104 bytes and pytest's tmp_path can
        # exceed that, so bind in a short-lived directory near the temp root.
        short_dir = Path(tempfile.mkdtemp(prefix="music-cli-test-"))
        socket_path = short_dir / "t.sock"
        server = UnixIPCServer()
        await server.start(noop_handler, socket_path)
        try:
            mode = stat.S_IMODE(socket_path.stat().st_mode)
            assert mode & 0o077 == 0, f"socket is group/world accessible: {oct(mode)}"
            assert mode & 0o700 == 0o600
        finally:
            await server.stop()
            shutil.rmtree(short_dir, ignore_errors=True)


class _StubPlayer:
    """Minimal player double mimicking FFplayPlayer's play/stop lifecycle.

    ``play`` yields before assigning ``_process`` so that, without the
    command lock, two concurrent plays reliably interleave and both
    subprocesses survive.
    """

    def __init__(self) -> None:
        self._process = None
        self.processes: list[Any] = []
        self.events: list[str] = []
        self.stopped_count = 0

    async def stop(self) -> None:
        self.events.append("stop")
        self.stopped_count += 1
        if self._process is not None:
            self._process["killed"] = True
            self._process = None

    async def play(self, track: Any) -> bool:
        # Mirror FFplayPlayer.play: every play stops current playback first.
        await self.stop()
        self.events.append(f"play:{track.source}")
        await asyncio.sleep(0.01)
        proc = {"id": track.source, "killed": False}
        self.processes.append(proc)
        self._process = proc
        self.events.append("play-done")
        return True

    def set_on_track_end(self, callback: Any) -> None:
        pass

    def get_status(self) -> dict:
        return {"state": "stopped"}


def _make_play_daemon(tmp_path: Path, player: _StubPlayer) -> Any:
    """Harness daemon wired for play commands through a stub player."""
    from music_cli.player.base import TrackInfo

    daemon = _DaemonTestHarness.make_daemon(tmp_path)
    daemon.player = player
    daemon._auto_play = False
    daemon._current_mood = None
    daemon.local_source = MagicMock()
    daemon.local_source.get_track.side_effect = lambda source: TrackInfo(
        source=source, source_type="local", title=source
    )
    daemon.radio_source = MagicMock()
    daemon.youtube_source = MagicMock()
    daemon.history = MagicMock()
    daemon.youtube_history = MagicMock()
    daemon.temporal = MagicMock()
    return daemon


class TestCommandSerialization:
    """State-mutating command handlers run under one lock (#67)."""

    @pytest_asyncio.fixture
    async def play_server(self, tmp_path: Path):
        player = _StubPlayer()
        daemon = _make_play_daemon(tmp_path, player)
        server = await asyncio.start_server(daemon._handle_client, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        yield daemon, player, port
        server.close()
        await server.wait_closed()

    async def test_concurrent_plays_leave_single_process(self, play_server) -> None:
        daemon, player, port = play_server

        def payload(n: int) -> dict:
            return {
                "command": "play",
                "args": {"mode": "local", "source": f"track-{n}.wav"},
                "token": daemon._auth_token,
            }

        first, second = await asyncio.gather(
            _roundtrip(port, payload(1)),
            _roundtrip(port, payload(2)),
        )

        assert first.get("status") == "playing"
        assert second.get("status") == "playing"

        survivors = [p for p in player.processes if not p["killed"]]
        assert len(survivors) == 1, (
            f"expected exactly one live ffplay process, got {len(survivors)}"
        )
        assert daemon.player._process is survivors[0]

    async def test_ping_answers_outside_in_flight_play(self, play_server) -> None:
        daemon, player, port = play_server

        release_play = asyncio.Event()

        async def holding_play(track: Any) -> bool:
            await player.stop()
            player.events.append(f"play:{track.source}")
            # Hold the handler mid-play until the ping below has been
            # answered, so the ordering assertion cannot lose a timing race
            # on slow runners.
            await asyncio.wait_for(release_play.wait(), timeout=5)
            proc = {"id": track.source, "killed": False}
            player.processes.append(proc)
            player._process = proc
            player.events.append("play-done")
            return True

        async def recording_ping(args):
            player.events.append("pong")
            return {"status": "ok", "message": "pong", "identity": daemon._identity}

        player.play = holding_play
        daemon._cmd_ping = recording_ping

        play_task = asyncio.create_task(
            _roundtrip(
                port,
                {
                    "command": "play",
                    "args": {"mode": "local", "source": "slow.wav"},
                    "token": daemon._auth_token,
                },
            )
        )
        try:
            # Wait until the play handler is mid-flight and parked.
            for _ in range(200):
                if any(e.startswith("play:") for e in player.events):
                    break
                await asyncio.sleep(0.005)
            assert any(e.startswith("play:") for e in player.events)

            pong = await asyncio.wait_for(
                _roundtrip(port, {"command": "ping", "args": {}, "token": daemon._auth_token}),
                timeout=5,
            )
        finally:
            release_play.set()
        await asyncio.wait_for(play_task, timeout=5)

        assert pong["status"] == "ok"
        # Health checks answer outside the command lock (#68): a liveness
        # probe must not queue behind a long state-mutating handler, or the
        # identity check would hang for the duration of every play.
        assert player.events.index("pong") < player.events.index("play-done")


class TestBackgroundTaskReferences:
    """Fire-and-forget tasks keep strong references until done (#69)."""

    async def test_spawn_task_tracked_until_completion(self, tmp_path) -> None:
        daemon = _DaemonTestHarness.make_daemon(tmp_path)
        finished = asyncio.Event()

        async def work():
            await asyncio.sleep(0)
            finished.set()

        task = daemon._spawn_task(work())
        assert task in daemon._background_tasks
        await asyncio.wait_for(task, timeout=5)
        assert finished.is_set()
        assert task not in daemon._background_tasks

    async def test_auto_play_chain_spawns_tracked_locked_task(self, tmp_path) -> None:
        from music_cli.player.base import TrackInfo

        player = _StubPlayer()
        daemon = _make_play_daemon(tmp_path, player)
        daemon._auto_play = True
        daemon.local_source.get_random_track.return_value = TrackInfo(
            source="next.wav", source_type="local", title="next"
        )

        daemon._on_track_end()

        tasks = list(daemon._background_tasks)
        assert len(tasks) == 1, "auto-play chain must keep a strong reference"
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)

        # The detached advance ran under the command lock and took over
        # playback: previous process killed, exactly one survivor.
        survivors = [p for p in player.processes if not p["killed"]]
        assert len(survivors) == 1
        assert daemon.player._process is survivors[0]
        daemon.history.log.assert_called_once()

    async def test_authenticated_shutdown_stops_serve_loop(self, tmp_path, monkeypatch):
        from music_cli.platform.ipc import TCPIPCServer

        monkeypatch.setattr("music_cli.daemon.supports_unix_signals", lambda: False)

        daemon = _DaemonTestHarness.make_daemon(tmp_path)
        daemon.player = _StubPlayer()
        ipc = TCPIPCServer(port=0)
        daemon._ipc_server = ipc

        pid_file = tmp_path / "daemon.pid"
        config = MagicMock()
        config.socket_path = tmp_path / "daemon.sock"
        config.pid_file = pid_file
        daemon.config = config

        start_task = asyncio.create_task(daemon.start())
        for _ in range(100):
            if ipc.server is not None:
                break
            await asyncio.sleep(0.01)
        port = ipc.server.sockets[0].getsockname()[1]

        response = await _roundtrip(
            port,
            # start() rotates the per-run token; use the fresh one.
            {"command": "shutdown", "args": {}, "token": daemon._auth_token},
        )
        assert response == {"status": "shutting_down"}

        # The daemon must actually terminate, not merely acknowledge.
        # Server.close() cancels the serve_forever future, so start()
        # surfaces that cancellation — either way the loop has exited.
        try:
            await asyncio.wait_for(start_task, timeout=5)
        except asyncio.CancelledError:
            pass
        assert start_task.done() and not daemon._running
        assert not pid_file.exists()


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
