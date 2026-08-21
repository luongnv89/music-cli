"""Daemon lifecycle control command."""

import os
import signal
import time

import click

from ..daemon import get_daemon_pid, is_daemon_running
from ..platform import is_windows
from . import runtime
from .app import main


@main.command("daemon")
@click.argument("action", type=click.Choice(["start", "stop", "restart", "status"]))
def daemon_control(action):
    """Control the background daemon.

    \b
    Actions:
      start   - Start the daemon
      stop    - Stop the daemon
      restart - Restart the daemon
      status  - Check daemon status
    """
    if action == "status":
        pid = get_daemon_pid()
        if pid:
            click.echo(f"Daemon is running (PID: {pid})")
        else:
            click.echo("Daemon is not running")

    elif action == "start":
        if is_daemon_running():
            click.echo("Daemon is already running")
        else:
            runtime.start_daemon_background()
            click.echo("Daemon started")

    elif action == "stop":
        pid = get_daemon_pid()
        if pid:
            _terminate_daemon(pid)
            click.echo("Daemon stopped")
        else:
            click.echo("Daemon is not running")

    elif action == "restart":
        pid = get_daemon_pid()
        if pid:
            _terminate_daemon(pid)
            time.sleep(0.5)
        runtime.start_daemon_background()
        click.echo("Daemon restarted")


def _terminate_daemon(pid: int) -> None:
    """Terminate the daemon process.

    Uses platform-appropriate method:
    - Unix: SIGTERM signal (allows graceful shutdown)
    - Windows: Send stop command via IPC, then terminate
    """
    if is_windows():
        # On Windows, try to send stop command via IPC for graceful shutdown
        # TerminateProcess doesn't give the daemon a chance to cleanup
        try:
            from ..client import DaemonClient

            client = DaemonClient()
            # Try to send stop command - this triggers graceful shutdown
            client.send_command("shutdown", timeout=2.0)
            # Wait a moment for cleanup
            time.sleep(0.3)
        except Exception:  # noqa: S110  # nosec B110
            pass  # If IPC fails, fall through to forceful termination

        # Force terminate if still running
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass  # Process already stopped
    else:
        # Unix: SIGTERM triggers graceful shutdown via signal handler
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass  # Process already stopped
