"""Runtime services shared by commands: daemon lifecycle and animation."""

import logging
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import IO, Any

import click

from ..client import DaemonClient
from ..config import get_config
from ..daemon import is_daemon_running
from ..platform import get_path_provider, is_windows

logger = logging.getLogger(__name__)


class ComposingAnimation:
    """Animated text display for AI music generation."""

    def __init__(self):
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the composing animation."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the animation."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        # Clear the animation line
        click.echo("\r" + " " * 40 + "\r", nl=False)

    def _animate(self) -> None:
        """Animation loop."""
        frames = ["composing", "composing.", "composing..", "composing..."]
        idx = 0
        while not self._stop_event.is_set():
            click.echo(f"\r{frames[idx]}", nl=False)
            idx = (idx + 1) % len(frames)
            time.sleep(0.5)


def ensure_daemon() -> DaemonClient:
    """Ensure daemon is running and return client."""
    if not is_daemon_running():
        click.echo("Starting daemon...", err=True)
        start_daemon_background()
        # Wait a bit for daemon to start
        for _ in range(10):
            time.sleep(0.2)
            if is_daemon_running():
                break
        else:
            log_path = _daemon_log_path()
            click.echo("Failed to start daemon", err=True)
            click.echo(f"Daemon startup log: {log_path}", err=True)
            sys.exit(1)

    return DaemonClient()


def _daemon_log_path() -> Path:
    """Path where the spawned daemon's stderr (startup tracebacks) lands."""
    return get_path_provider().get_daemon_log_file(get_config().config_dir)


def start_daemon_background() -> None:
    """Start the daemon in background.

    Uses platform-appropriate process creation:
    - Linux/macOS: start_new_session=True
    - Windows: CREATE_NEW_PROCESS_GROUP flag

    The child's stderr is redirected to a log file under the config
    directory (daemon.log) so a startup failure leaves a readable traceback.
    """
    python = sys.executable
    cmd = [python, "-m", "music_cli.daemon"]

    # Redirect the child's stderr to the log file; fall back to DEVNULL if
    # the log file cannot be created (config dir missing, permissions, ...).
    # Line-buffered so a crash traceback reaches disk even if the child dies
    # without flushing.
    err_target: int | IO[Any] = subprocess.DEVNULL
    log_file = None
    try:
        log_path = _daemon_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("a", buffering=1)
        err_target = log_file
    except OSError as exc:
        logger.warning("Could not open daemon startup log: %s", exc)

    try:
        if is_windows():
            # Windows: Use CREATE_NEW_PROCESS_GROUP to detach from console
            # These are Windows API constants
            create_new_process_group = 0x00000200
            detached_process = 0x00000008
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=err_target,
                stdin=subprocess.DEVNULL,
                creationflags=create_new_process_group | detached_process,
            )
        else:
            # Unix: Use start_new_session to create a new session
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=err_target,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
    finally:
        if log_file is not None:
            # Safe to close: Popen dup'ed the fd into the child.
            log_file.close()
