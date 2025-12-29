"""Command-line interface for music-cli."""

import os
import signal
import subprocess
import sys
import time

import click

from . import __version__
from .client import DaemonClient
from .config import get_config
from .daemon import get_daemon_pid, is_daemon_running
from .player.ffplay import check_ffplay_available


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
            click.echo("Failed to start daemon", err=True)
            sys.exit(1)

    return DaemonClient()


def start_daemon_background() -> None:
    """Start the daemon in background."""
    # Start daemon as subprocess
    python = sys.executable
    subprocess.Popen(
        [python, "-m", "music_cli.daemon"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


@click.group()
@click.version_option(__version__)
def main():
    """music-cli: A command-line music player for coders.

    Play local MP3s, stream radio, or generate AI music based on your mood
    and the time of day.
    """
    pass


@main.command()
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["local", "radio", "ai", "context", "history"]),
    default="radio",
    help="Playback mode",
)
@click.option("--source", "-s", help="Source file/URL/station name")
@click.option(
    "--mood",
    type=click.Choice(["happy", "sad", "excited", "focus", "relaxed", "energetic"]),
    help="Mood for context-aware playback",
)
@click.option("--auto", "-a", is_flag=True, help="Enable auto-play (shuffle local files)")
@click.option("--duration", "-d", default=30, help="Duration for AI generation (seconds)")
@click.option("--index", "-i", type=int, help="History entry index to replay")
def play(mode, source, mood, auto, duration, index):
    """Start playing music.

    \b
    Examples:
      music-cli play                    # Play context-aware radio
      music-cli play -m local -s song.mp3  # Play local file
      music-cli play -m radio -s "chill"   # Play radio station by name
      music-cli play --mood focus       # Play focus music
      music-cli play -m ai --mood happy # Generate happy AI music
      music-cli play -m history -i 3    # Replay 3rd item from history
      music-cli play -m local --auto    # Shuffle local library
    """
    if not check_ffplay_available():
        click.echo("Error: ffplay not found. Please install FFmpeg.", err=True)
        click.echo("  macOS: brew install ffmpeg", err=True)
        click.echo("  Linux: apt install ffmpeg", err=True)
        sys.exit(1)

    client = ensure_daemon()

    try:
        response = client.play(
            mode=mode,
            source=source,
            mood=mood,
            auto=auto,
            duration=duration,
            index=index,
        )

        if "error" in response:
            click.echo(f"Error: {response['error']}", err=True)
            sys.exit(1)

        track = response.get("track", {})
        title = track.get("title", track.get("source", "Unknown"))
        source_type = track.get("source_type", "unknown")

        click.echo(f"▶ Playing: {title} [{source_type}]")
        if auto:
            click.echo("  Auto-play enabled (shuffle mode)")

    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
def stop():
    """Stop playback."""
    client = ensure_daemon()

    try:
        response = client.stop()
        if "error" in response:
            click.echo(f"Error: {response['error']}", err=True)
        else:
            click.echo("⏹ Stopped")
    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
def pause():
    """Pause playback."""
    client = ensure_daemon()

    try:
        response = client.pause()
        if "error" in response:
            click.echo(f"Error: {response['error']}", err=True)
        else:
            click.echo("⏸ Paused")
    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
def resume():
    """Resume playback."""
    client = ensure_daemon()

    try:
        response = client.resume()
        if "error" in response:
            click.echo(f"Error: {response['error']}", err=True)
        else:
            click.echo("▶ Resumed")
    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
def status():
    """Show current playback status."""
    client = ensure_daemon()

    try:
        response = client.status()

        if "error" in response:
            click.echo(f"Error: {response['error']}", err=True)
            sys.exit(1)

        state = response.get("state", "unknown")
        state_icons = {
            "playing": "▶",
            "paused": "⏸",
            "stopped": "⏹",
            "loading": "⏳",
            "error": "❌",
        }

        click.echo(f"Status: {state_icons.get(state, '?')} {state}")

        track = response.get("track")
        if track:
            title = track.get("title", track.get("source", "Unknown"))
            source_type = track.get("source_type", "unknown")
            click.echo(f"Track: {title} [{source_type}]")

        volume = response.get("volume", 80)
        click.echo(f"Volume: {volume}%")

        if response.get("auto_play"):
            click.echo("Auto-play: enabled")

        mood = response.get("mood")
        if mood:
            click.echo(f"Mood: {mood}")

        context = response.get("context", {})
        time_period = context.get("time_period", "")
        if time_period:
            click.echo(f"Context: {time_period} / {context.get('day_type', '')}")

    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command("next")
def next_track():
    """Skip to next track (auto-play mode only)."""
    client = ensure_daemon()

    try:
        response = client.next_track()
        if "error" in response:
            click.echo(f"Error: {response['error']}", err=True)
        else:
            click.echo("⏭ Skipped to next track")
    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("level", type=int, required=False)
def volume(level):
    """Get or set volume (0-100).

    \b
    Examples:
      music-cli volume      # Show current volume
      music-cli volume 50   # Set volume to 50%
    """
    client = ensure_daemon()

    try:
        if level is not None:
            response = client.set_volume(level)
            click.echo(f"Volume: {response.get('volume', level)}%")
        else:
            vol = client.get_volume()
            click.echo(f"Volume: {vol}%")
    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command("radios")
def list_radios():
    """List available radio stations."""
    client = ensure_daemon()

    try:
        stations = client.list_radios()

        if not stations:
            config = get_config()
            click.echo(f"No stations configured. Add stations to: {config.radios_file}")
            return

        click.echo("Available radio stations:")
        for station in stations:
            click.echo(f"  {station['index']}. {station['name']}")

    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command("history")
@click.option("--limit", "-n", default=20, help="Number of entries to show")
def list_history(limit):
    """Show playback history."""
    client = ensure_daemon()

    try:
        history = client.list_history(limit=limit)

        if not history:
            click.echo("No playback history yet.")
            return

        click.echo("Recent playback history:")
        for entry in history:
            idx = entry.get("index", "?")
            title = entry.get("title") or entry.get("source", "Unknown")[:40]
            source_type = entry.get("source_type", "?")
            timestamp = entry.get("timestamp", "")[:16]  # Truncate to date/time
            click.echo(f"  {idx}. [{timestamp}] {title} ({source_type})")

        click.echo("\nReplay with: music-cli play -m history -i <number>")

    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


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
            start_daemon_background()
            click.echo("Daemon started")

    elif action == "stop":
        pid = get_daemon_pid()
        if pid:
            os.kill(pid, signal.SIGTERM)
            click.echo("Daemon stopped")
        else:
            click.echo("Daemon is not running")

    elif action == "restart":
        pid = get_daemon_pid()
        if pid:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
        start_daemon_background()
        click.echo("Daemon restarted")


@main.command("config")
def show_config():
    """Show configuration file locations."""
    config = get_config()

    click.echo("Configuration files:")
    click.echo(f"  Config:  {config.config_file}")
    click.echo(f"  Radios:  {config.radios_file}")
    click.echo(f"  History: {config.history_file}")
    click.echo(f"  Socket:  {config.socket_path}")
    click.echo(f"  PID:     {config.pid_file}")


@main.command("moods")
def list_moods():
    """List available mood tags."""
    from .context.mood import MoodContext

    click.echo("Available moods:")
    for mood in MoodContext.get_all_moods():
        click.echo(f"  - {mood}")
    click.echo("\nUse with: music-cli play --mood <mood>")


if __name__ == "__main__":
    main()
