"""Background daemon for music-cli."""

import asyncio
import hmac
import json
import logging
import os
import secrets
import signal
from collections.abc import Coroutine
from typing import Any

from .ai_tracks import get_ai_tracks
from .config import get_config
from .context.mood import Mood
from .context.temporal import TemporalContext
from .daemon_handlers import (
    COMMAND_HANDLERS,
    AIHandlers,
    PlaybackHandlers,
    SystemHandlers,
    YouTubeHistoryHandlers,
)
from .history import get_history
from .ipc_framing import MAX_REQUEST_SIZE, REQUEST_CHUNK_SIZE, RequestError, read_request
from .platform import get_ipc_server, supports_unix_signals
from .platform.ipc import IPCServer
from .player.ffplay import FFplayPlayer
from .sources.local import LocalSource
from .sources.radio import RadioSource
from .sources.youtube import YouTubeSource
from .sources.youtube import is_youtube_available as is_youtube_available
from .youtube_history import get_youtube_history

logger = logging.getLogger(__name__)

# Liveness-probe budget (#68): long enough for a busy loop to answer a ping,
# short enough that a hung impostor does not stall every CLI command.
IDENTITY_PROBE_TIMEOUT = 2.0
REQUEST_READ_TIMEOUT = 5.0


class MusicDaemon(
    PlaybackHandlers,
    AIHandlers,
    YouTubeHistoryHandlers,
    SystemHandlers,
):
    """Background daemon that handles music playback.

    Transport and lifecycle live here; the per-command behaviour behind
    ``COMMAND_HANDLERS`` lives in :mod:`music_cli.daemon_handlers`. The
    registry maps each command to its handler method name and is built once
    at class creation — never per request.
    """

    COMMAND_HANDLERS = COMMAND_HANDLERS

    def __init__(self):
        self.config = get_config()
        self.player = FFplayPlayer()
        self.local_source = LocalSource()
        self.radio_source = RadioSource()
        self.youtube_source = YouTubeSource()
        self.history = get_history()
        self.youtube_history = get_youtube_history()
        self.temporal = TemporalContext()
        self.ai_tracks = get_ai_tracks()

        # Platform-specific IPC server (Unix sockets or TCP)
        self._ipc_server: IPCServer = get_ipc_server()
        self._running = False
        self._current_mood: Mood | None = None
        self._auto_play = False  # For infinite/context-aware mode
        self._auth_token: str | None = None  # Issued in start(); None rejects every request
        # Serializes state-mutating command handlers (#67): per-connection
        # tasks interleave at every await, so concurrent plays would race on
        # player state and orphan ffplay processes.
        self._command_lock = asyncio.Lock()
        # Strong references to fire-and-forget tasks (#69): the event loop
        # keeps only a weak reference, so unreferenced tasks can be collected
        # mid-execution.
        self._background_tasks: set[asyncio.Task] = set()
        # Per-run identity (#68): recorded in the PID file and echoed by
        # ``ping`` so liveness checks can tell this daemon apart from an
        # unrelated process that merely recycled its PID.
        self._identity = secrets.token_hex(16)

    def _spawn_task(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
        """Schedule a background task and hold a reference until it finishes."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    def _issue_auth_token(self) -> str:
        """Generate a fresh auth token and persist it owner-only.

        The token is stored in the config directory (0o700) with file mode
        0o600 so only the owning user's clients can authenticate.
        """
        self._auth_token = secrets.token_hex(32)
        self.config.write_auth_token(self._auth_token)
        return self._auth_token

    async def start(self) -> None:
        """Start the daemon server.

        Uses platform-appropriate IPC:
        - Linux/macOS: Unix domain sockets
        - Windows: TCP localhost
        """
        socket_path = self.config.socket_path

        self._running = True

        # Generate a fresh per-run auth token before accepting connections
        self._issue_auth_token()

        # Set up signal handlers (Unix only - not supported on Windows asyncio)
        if supports_unix_signals():
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, lambda: self._spawn_task(self.stop()))

        # Start IPC server (platform-specific)
        await self._ipc_server.start(self._handle_client, socket_path)

        # Write PID file with the run's identity so liveness checks can
        # verify the process behind the PID is this daemon (#68).
        self.config.pid_file.write_text(
            json.dumps({"pid": os.getpid(), "identity": self._identity})
        )

        address_display = self._ipc_server.get_address_display(socket_path)
        logger.info(f"Daemon started, listening on {address_display}")

        await self._ipc_server.serve_forever()

    async def stop(self) -> None:
        """Stop the daemon."""
        logger.info("Stopping daemon...")
        self._running = False

        await self.player.stop()

        # Stop IPC server (handles socket cleanup on Unix)
        await self._ipc_server.stop()

        # Clean up PID file
        if self.config.pid_file.exists():
            try:
                self.config.pid_file.unlink()
            except OSError:
                pass  # Best effort cleanup

        logger.info("Daemon stopped")

    async def _read_request(self, reader: asyncio.StreamReader) -> dict | None:
        """Read one complete JSON request without relying on socket boundaries.

        The timeout is read from module scope at call time so tests can patch
        ``music_cli.daemon.REQUEST_READ_TIMEOUT``.
        """
        return await read_request(reader, read_timeout=REQUEST_READ_TIMEOUT)

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a client connection."""
        try:
            try:
                request = await self._read_request(reader)
            except RequestError as exc:
                response = {"error": str(exc)}
                writer.write(json.dumps(response).encode())
                await writer.drain()
                return

            if request is None:
                return

            # Authenticate before dispatching any command handler
            token = request.get("token")
            auth_token = self._auth_token
            if (
                not auth_token
                or not isinstance(token, str)
                or not hmac.compare_digest(token, auth_token)
            ):
                logger.warning("Rejected request with missing or invalid token")
                response = {"error": "Unauthorized"}
                writer.write(json.dumps(response).encode())
                await writer.drain()
                return

            command = request.get("command", "")
            args = request.get("args", {})

            response = await self._process_command(command, args)

            writer.write(json.dumps(response).encode())
            await writer.drain()

        except Exception as e:
            logger.error(f"Error handling client: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def _process_command(self, command: str, args: dict) -> dict:
        """Process a command and return response."""
        handler_name = self.COMMAND_HANDLERS.get(command)
        if handler_name is None:
            return {"error": f"Unknown command: {command}"}

        handler = getattr(self, handler_name)

        # Health checks answer outside the command lock (#68): a ping
        # must not queue behind a long state-mutating handler, or every
        # liveness probe would block for the duration of a play.
        if command == "ping":
            return await handler(args)

        try:
            # Hold the command lock for the whole handler so concurrent
            # connections cannot interleave state mutations (#67).
            async with self._command_lock:
                return await handler(args)
        except Exception as e:
            # Log the detail server-side; never leak exception text
            # (which can contain filesystem paths) to the client.
            logger.error(f"Error processing {command}: {e}", exc_info=True)
            return {"error": "Internal error while processing command"}

    def _on_track_end(self) -> None:
        """Called when a track ends in auto-play mode."""
        if self._auto_play:
            self._spawn_task(self._auto_advance())

    async def _auto_advance(self) -> None:
        """Advance to the next track under the command lock.

        The lock is not reentrant, so ``_cmd_next`` (which already holds it)
        calls ``_play_next`` directly; only the detached auto-play chain
        re-acquires the lock here.
        """
        async with self._command_lock:
            await self._play_next()

    async def _play_next(self) -> None:
        """Play the next track in auto-play mode."""
        track = self.local_source.get_random_track()
        if track:
            await self.player.play(track)
            self.history.log(
                source=track.source,
                source_type=track.source_type,
                title=track.title,
                artist=track.artist,
                mood=self._current_mood.value if self._current_mood else None,
                context=self.temporal.get_time_period().value,
            )


def run_daemon() -> None:
    """Run the daemon (entry point)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    daemon = MusicDaemon()
    asyncio.run(daemon.start())


def _pid_alive(pid: int) -> bool:
    """Check if a PID is alive, cross-platform safe (does not kill on Windows).

    On Unix, uses ``os.kill(pid, 0)`` which is a no-op liveness probe.
    On Windows, uses ``OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)``
    to query process existence without requiring ``TerminateProcess``
    access — this avoids the Windows ``os.kill()`` bug where signal ``0``
    calls ``TerminateProcess(handle, 0)`` and can kill the process.

    Args:
        pid: The process ID to check.

    Returns:
        ``True`` if a process with the given PID exists, ``False`` otherwise.
    """
    from .platform import is_unix

    if is_unix():
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but we lack permission to signal it.
            return True
    else:
        # Windows: use ctypes to call OpenProcess with limited rights.
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000  # noqa: N806
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)  # type: ignore[attr-defined]
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
            return True
        return False


def _probe_daemon_identity(socket_path: Any, token: str | None) -> str | None:
    """Ask the process listening on ``socket_path`` to identify itself (#68).

    Sends an authenticated ``ping`` and returns the daemon's run identity,
    or ``None`` when nothing answers, the answer is unauthenticated, or the
    response carries no identity. Never raises.
    """
    from .platform import get_ipc_client

    try:
        client = get_ipc_client()
        sock = client.connect(socket_path, IDENTITY_PROBE_TIMEOUT)
    except Exception:
        return None
    try:
        request = json.dumps({"command": "ping", "args": {}, "token": token})
        sock.sendall(request.encode())
        response_data = b""
        while len(response_data) < MAX_REQUEST_SIZE:
            chunk = sock.recv(REQUEST_CHUNK_SIZE)
            if not chunk:
                break
            response_data += chunk
        response = json.loads(response_data.decode())
    except Exception:
        return None
    finally:
        try:
            sock.close()
        except OSError:
            pass
    if not isinstance(response, dict):
        return None
    identity = response.get("identity")
    return identity if isinstance(identity, str) else None


def _parse_pid_record(raw: str) -> tuple[int | None, str | None]:
    """Parse PID-file content into ``(pid, identity)``.

    Current format: JSON ``{"pid": ..., "identity": ...}``. A legacy
    plain-int file parses as a PID but carries no identity, so it can never
    be verified and is treated as stale. A JSON PID of ``true`` must not
    read as ``1`` (bool is an int subclass).
    """
    try:
        parsed = json.loads(raw)
    except ValueError:
        parsed = None

    if isinstance(parsed, dict):
        file_pid = parsed.get("pid")
        file_identity = parsed.get("identity")
        if (
            isinstance(file_pid, int)
            and not isinstance(file_pid, bool)
            and isinstance(file_identity, str)
        ):
            return file_pid, file_identity

    try:
        return int(raw), None
    except ValueError:
        return None, None


def _cleanup_stale_files(config: Any) -> None:
    """Best-effort removal of stale PID and (Unix-only) socket files."""
    from .platform import is_unix

    try:
        if config.pid_file.exists():
            config.pid_file.unlink()
        # Only clean up socket file on Unix (Windows uses TCP)
        if is_unix() and config.socket_path.exists():
            config.socket_path.unlink()
    except OSError:
        pass  # Best effort cleanup


def get_daemon_pid() -> int | None:
    """Get the PID of the running daemon.

    Returns the PID only when the PID file is current *and* the process it
    names proves its identity (#68): the daemon records a per-run nonce in
    the PID file and echoes it over ``ping``, so a recycled PID belonging to
    an unrelated process no longer reads as a live daemon.

    Also cleans up stale PID/socket files when the daemon is not running.
    """
    config = get_config()

    if not config.pid_file.exists():
        return None

    try:
        raw = config.pid_file.read_text().strip()
    except OSError:
        raw = ""

    pid, identity = _parse_pid_record(raw)

    if pid is None:
        try:
            if config.pid_file.exists():
                config.pid_file.unlink()
        except OSError:
            pass
        return None

    if not _pid_alive(pid):
        # PID file is stale, clean up
        _cleanup_stale_files(config)
        return None

    # The PID is alive — now make sure it is *our* daemon and not whatever
    # process recycled the PID after an unclean exit (#68).
    answered = _probe_daemon_identity(config.socket_path, config.read_auth_token())
    if identity is None or answered != identity:
        logger.info(
            "PID file identity check failed (recorded=%s, answered=%s) — "
            "treating PID file as stale",
            "present" if identity else "missing",
            "matching" if answered == identity else "mismatched",
        )
        _cleanup_stale_files(config)
        return None

    return pid


def is_daemon_running() -> bool:
    """Check if daemon is already running."""
    return get_daemon_pid() is not None


if __name__ == "__main__":
    run_daemon()
