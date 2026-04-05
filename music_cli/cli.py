"""Command-line interface for music-cli."""

import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import click

from . import __github_url__, __version__
from .client import DaemonClient
from .config import get_config
from .daemon import get_daemon_pid, is_daemon_running
from .platform import is_windows
from .player.ffplay import check_ffplay_available

logger = logging.getLogger(__name__)

# Inspirational quotes about music and life
INSPIRATIONAL_QUOTES = [
    '"Music is the soundtrack of your life." - Dick Clark',
    '"Where words fail, music speaks." - Hans Christian Andersen',
    '"One good thing about music, when it hits you, you feel no pain." - Bob Marley',
    '"Music gives a soul to the universe, wings to the mind, flight to the imagination." - Plato',
    '"Without music, life would be a mistake." - Friedrich Nietzsche',
    '"Music is the strongest form of magic." - Marilyn Manson',
    '"Life is like a beautiful melody, only the lyrics are messed up." - Hans Christian Andersen',
    '"Music expresses that which cannot be said and on which it is impossible to be silent." - Victor Hugo',
    '"The only truth is music." - Jack Kerouac',
    '"Music is the divine way to tell beautiful, poetic things to the heart." - Pablo Casals',
]


def get_random_quote() -> str:
    """Get a random inspirational quote."""
    import random

    return random.choice(INSPIRATIONAL_QUOTES)  # noqa: S311


# ---------------------------------------------------------------------------
# Task 3.2: NO_COLOR / --no-color support
# ---------------------------------------------------------------------------

# Mapping from unicode symbol to plain-text fallback
_ICON_FALLBACKS: dict[str, str] = {
    "\u25b6": "[playing]",  # ▶
    "\u23f8": "[paused]",  # ⏸
    "\u23f9": "[stopped]",  # ⏹
    "\u23ed": "[skip]",  # ⏭
    "\u274c": "[error]",  # ❌
    "\u23f3": "[loading]",  # ⏳
    "\u26a0": "[warning]",  # ⚠
}


def _is_no_color() -> bool:
    """Return True when colour/emoji output should be suppressed."""
    try:
        ctx = click.get_current_context()
        if isinstance(ctx.obj, dict):
            return ctx.obj.get("no_color", False)
    except RuntimeError:
        pass
    # No active Click context or ctx.obj not initialised — fall back to env var
    return os.environ.get("NO_COLOR", "") != ""


def icon(symbol: str, text_fallback: str | None = None) -> str:
    """Return *symbol* normally, or a plain-text fallback when NO_COLOR is active.

    If *text_fallback* is not provided, _ICON_FALLBACKS is consulted.
    """
    if not _is_no_color():
        return symbol
    if text_fallback is not None:
        return text_fallback
    return _ICON_FALLBACKS.get(symbol, symbol)


# Track if we've already checked for updates this session
_update_checked = False


def _check_for_updates_once() -> None:
    """Check for updates only once per CLI session."""
    global _update_checked
    if _update_checked:
        return
    _update_checked = True

    try:
        config = get_config()
        if not config.needs_update():
            return

        new_stations = config.get_new_default_stations()
        if new_stations:
            click.echo(
                f"\nNew version detected! {len(new_stations)} new radio station(s) available.",
                err=True,
            )
            click.echo("Run 'mc radio update' to update your stations.\n", err=True)
    except Exception as e:
        # Don't let update check break normal operation
        logger.debug(f"Update check failed: {e}")


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
            click.echo("Failed to start daemon", err=True)
            sys.exit(1)

    return DaemonClient()


def start_daemon_background() -> None:
    """Start the daemon in background.

    Uses platform-appropriate process creation:
    - Linux/macOS: start_new_session=True
    - Windows: CREATE_NEW_PROCESS_GROUP flag
    """
    python = sys.executable
    cmd = [python, "-m", "music_cli.daemon"]

    if is_windows():
        # Windows: Use CREATE_NEW_PROCESS_GROUP to detach from console
        # These are Windows API constants
        create_new_process_group = 0x00000200
        detached_process = 0x00000008
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=create_new_process_group | detached_process,
        )
    else:
        # Unix: Use start_new_session to create a new session
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


class AliasedGroup(click.Group):
    """Click group that supports hidden command aliases.

    Aliases are registered as a mapping from alias name to real command name.
    They are hidden from --help output but fully functional.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._aliases: dict[str, str] = {}

    def add_alias(self, alias: str, target: str) -> None:
        """Register *alias* as a hidden forwarding name for *target*."""
        self._aliases[alias] = target

    def get_command(self, ctx, cmd_name):
        """Resolve aliases before normal lookup."""
        # Check if the cmd_name is an alias
        real_name = self._aliases.get(cmd_name, cmd_name)
        return super().get_command(ctx, real_name)

    def format_usage(self, ctx, formatter):
        """Standard usage — aliases stay hidden."""
        super().format_usage(ctx, formatter)


def _register_alias(group: AliasedGroup, alias: str, target: str) -> None:
    """Register a hidden alias on an AliasedGroup."""
    group.add_alias(alias, target)


@click.group(
    cls=AliasedGroup,
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__)
@click.option(
    "--no-color", is_flag=True, default=False, help="Disable emoji/unicode symbols in output"
)
@click.pass_context
def main(ctx, no_color):
    """mc: A command-line music player for coders.

    Play local MP3s, stream radio, or generate AI music based on your mood
    and the time of day.
    """
    # Task 3.2: NO_COLOR support (https://no-color.org/)
    ctx.ensure_object(dict)
    ctx.obj["no_color"] = no_color or os.environ.get("NO_COLOR", "") != ""

    # Check for updates on any command
    if ctx.invoked_subcommand is not None:
        _check_for_updates_once()
    elif ctx.invoked_subcommand is None:
        # Bare invocation: show status
        ctx.invoke(status)


def _detect_play_mode(source_arg):
    """Auto-detect playback mode from the SOURCE argument.

    Detection order:
    1. File path that exists on disk -> local
    2. YouTube URL pattern -> youtube
    3. http:// or https:// URL -> radio (stream URL)
    4. Station name match (case-insensitive) -> radio
    5. No source -> context
    """
    import re

    if source_arg is None:
        return "context", None

    # 1. Existing file path
    if Path(source_arg).exists():
        return "local", source_arg

    # 2. YouTube URL
    yt_pattern = re.compile(r"(youtube\.com/watch|youtu\.be/|youtube\.com/playlist)", re.IGNORECASE)
    if yt_pattern.search(source_arg):
        return "youtube", source_arg

    # 3. Generic HTTP(S) URL -> radio stream
    if source_arg.startswith("http://") or source_arg.startswith("https://"):
        return "radio", source_arg

    # 4. Station name lookup
    config = get_config()
    station = config.get_station_by_name(source_arg)
    if station:
        return "radio", station[1]  # return the URL

    # Fall back: treat as source for the default radio mode
    return "radio", source_arg


@main.command()
@click.argument("source", required=False, default=None)
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["local", "radio", "ai", "context", "history", "youtube", "yt"]),
    default=None,
    help="Playback mode (usually auto-detected from SOURCE)",
)
@click.option(
    "--source", "-s", "source_flag", default=None, help="Source file/URL/station name (legacy flag)"
)
@click.option(
    "--mood",
    "-M",
    type=click.Choice(
        ["happy", "sad", "excited", "focus", "relaxed", "energetic", "melancholic", "peaceful"]
    ),
    help="Mood for context-aware playback",
)
@click.option("--auto", "-a", is_flag=True, help="Enable auto-play (shuffle local files)")
@click.option("--duration", "-d", default=15, help="Duration for AI generation (seconds)")
@click.option("--index", "-i", type=int, help="History entry index to replay")
def play(source, mode, source_flag, mood, auto, duration, index):
    """Start playing music.

    \b
    SOURCE is auto-detected:
      file path        -> local mode
      YouTube URL      -> youtube mode
      http(s):// URL   -> radio stream
      station name     -> radio station
      (nothing)        -> context-aware radio

    \b
    Examples:
      mc play ~/song.mp3                          # Auto-detect local
      mc play "https://youtube.com/watch?v=xxx"   # Auto-detect YouTube
      mc play chill                                # Auto-detect station name
      mc play                                      # Context-aware radio
      mc play -M focus                             # Mood-based radio
    """
    if not check_ffplay_available():
        click.echo("Error: ffplay not found. Please install FFmpeg.", err=True)
        if is_windows():
            click.echo("  Windows: choco install ffmpeg", err=True)
            click.echo("       or: winget install ffmpeg", err=True)
            click.echo("       or: scoop install ffmpeg", err=True)
        else:
            click.echo("  macOS: brew install ffmpeg", err=True)
            click.echo("  Linux: apt install ffmpeg", err=True)
        sys.exit(1)

    # Positional SOURCE takes priority over -s flag
    effective_source = source if source is not None else source_flag

    # Task 2.2: Deprecate play -m ai
    if mode == "ai":
        click.echo(
            f"{icon(chr(0x26A0))} Deprecated: use 'mc ai play' instead. This will be removed in v1.0.",
            err=True,
        )

    # Task 2.3: Deprecate play -m history
    if mode == "history":
        click.echo(
            f"{icon(chr(0x26A0))} Deprecated: use 'mc history play N' instead. This will be removed in v1.0.",
            err=True,
        )

    # Task 2.1: Smart auto-detection when --mode is NOT given
    if mode is None:
        mode, detected_source = _detect_play_mode(effective_source)
        effective_source = detected_source
    # If mode was explicitly given, keep the old behaviour
    # (effective_source from flag/positional is used as-is)

    client = ensure_daemon()

    # Show animation for AI generation
    animation = None
    if mode == "ai":
        animation = ComposingAnimation()
        animation.start()

    try:
        response = client.play(
            mode=mode,
            source=effective_source,
            mood=mood,
            auto=auto,
            duration=duration,
            index=index,
        )

        if animation:
            animation.stop()

        if "error" in response:
            click.echo(f"Error: {response['error']}", err=True)
            sys.exit(1)

        track = response.get("track", {})
        title = track.get("title", track.get("source", "Unknown"))
        source_type = track.get("source_type", "unknown")

        click.echo(f"{icon(chr(0x25B6))} Playing: {title} [{source_type}]")
        if auto:
            click.echo("  Auto-play enabled (shuffle mode)")

    except ConnectionError as e:
        if animation:
            animation.stop()
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
            click.echo(f"{icon(chr(0x23F9))} Stopped")
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
            click.echo(f"{icon(chr(0x23F8))} Paused")
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
            click.echo(f"{icon(chr(0x25B6), '[resumed]')} Resumed")
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
            "playing": icon("\u25b6"),
            "paused": icon("\u23f8"),
            "stopped": icon("\u23f9"),
            "loading": icon("\u23f3"),
            "error": icon("\u274c"),
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

        click.echo(f"\n{get_random_quote()}")
        click.echo(f"\nVersion: {__version__}")
        click.echo(f"GitHub: {__github_url__}")

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
            click.echo(f"{icon(chr(0x23ED))} Skipped to next track")
    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command("vol")
@click.argument("level", type=click.IntRange(0, 100), required=False)
def volume(level):
    """Get or set volume (0-100).

    \b
    Examples:
      mc vol            # Show current volume
      mc vol 50         # Set volume to 50%
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


@main.group("radio", cls=AliasedGroup, invoke_without_command=True)
@click.pass_context
def radios_group(ctx):
    """Manage radio stations.

    \b
    Commands:
      list          - Show all radio stations (default)
      play <number> - Play a station by number
      add           - Add a new radio station
      remove <num>  - Remove a station by number
      update        - Update stations after version upgrade

    \b
    Examples:
      mc radio              # List all stations
      mc radio list         # List all stations
      mc radio play 5       # Play station #5
      mc radio add          # Add new station interactively
      mc radio remove 3     # Remove station #3
      mc radio update       # Update station list
    """
    if ctx.invoked_subcommand is None:
        # Default action: list radios
        ctx.invoke(radios_list)


@radios_group.command("list")
def radios_list():
    """List all available radio stations."""
    config = get_config()
    radios = config.get_radios_categorized()

    if not radios:
        click.echo(f"No stations configured. Add stations to: {config.radios_file}")
        click.echo("Or run: mc radio add")
        return

    click.echo("Available radio stations:\n")

    # Group stations by category
    categories: dict[str, list[dict]] = {}
    for station in radios:
        cat = station["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(station)

    # Get terminal width and calculate columns
    terminal_width = shutil.get_terminal_size().columns
    col_width = 24  # Width for each column
    indent = 4  # Left margin for station rows
    # Calculate number of columns that fit (minimum 1, maximum 6)
    num_cols = max(1, min(6, (terminal_width - indent) // col_width))

    # Display each category
    for category, stations in categories.items():
        click.echo(f"  [{category}]")

        for i in range(0, len(stations), num_cols):
            row_parts = []
            for j in range(num_cols):
                if i + j < len(stations):
                    station = stations[i + j]
                    name = station["name"][: col_width - 5]
                    col_str = f"{station['index']:2}. {name}"
                    row_parts.append(f"{col_str:<{col_width}}")
            click.echo(f"  {''.join(row_parts)}")

        click.echo()  # Empty line after each category

    click.echo(f"Total: {len(radios)} station(s)")
    click.echo("Play with: mc radio play <number>")


@radios_group.command("play")
@click.argument("number", type=int)
def radios_play(number):
    """Play a radio station by its number."""
    config = get_config()
    station = config.get_radio_by_index(number)

    if not station:
        radios = config.get_radios()
        if not radios:
            click.echo("No radio stations configured.", err=True)
        else:
            click.echo(f"Invalid station number. Choose between 1 and {len(radios)}.", err=True)
        sys.exit(1)

    name, url = station
    client = ensure_daemon()

    try:
        response = client.play(mode="radio", source=url)

        if "error" in response:
            click.echo(f"Error: {response['error']}", err=True)
            sys.exit(1)

        click.echo(f"{icon(chr(0x25B6))} Playing: {name}")

    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@radios_group.command("add")
def radios_add():
    """Add a new radio station interactively."""
    click.echo("Add a new radio station\n")

    name = click.prompt("Station name")
    if not name.strip():
        click.echo("Error: Station name cannot be empty.", err=True)
        sys.exit(1)

    url = click.prompt("Stream URL")
    if not url.strip():
        click.echo("Error: Stream URL cannot be empty.", err=True)
        sys.exit(1)

    # Basic URL validation
    if not (url.startswith("http://") or url.startswith("https://")):
        click.echo("Warning: URL doesn't start with http:// or https://", err=True)
        if not click.confirm("Add anyway?", default=False):
            click.echo("Cancelled.")
            return

    config = get_config()
    config.add_radio(name.strip(), url.strip())

    radios = config.get_radios()
    click.echo(f"\nAdded: {name}")
    click.echo(f"Station #{len(radios)} in your list")
    click.echo(f"Play with: mc radio play {len(radios)}")


@radios_group.command("remove")
@click.argument("number", type=int)
def radios_remove(number):
    """Remove a radio station by its number."""
    config = get_config()
    radios = config.get_radios()

    if not radios:
        click.echo("No radio stations to remove.", err=True)
        sys.exit(1)

    if not (1 <= number <= len(radios)):
        click.echo(f"Invalid station number. Choose between 1 and {len(radios)}.", err=True)
        sys.exit(1)

    name, url = radios[number - 1]

    click.echo(f"Station #{number}: {name}")
    click.echo(f"URL: {url}")

    if not click.confirm("Remove this station?", default=False):
        click.echo("Cancelled.")
        return

    removed = config.remove_radio(number)
    if removed:
        click.echo(f"\nRemoved: {removed[0]}")
    else:
        click.echo("Error: Failed to remove station.", err=True)
        sys.exit(1)


@main.group("history", cls=AliasedGroup, invoke_without_command=True)
@click.pass_context
def history_group(ctx):
    """Show and replay playback history.

    \b
    Commands:
      list          - Show recent history (default)
      play <number> - Replay an item by its history number

    \b
    Examples:
      mc history              # List recent history
      mc history list -n 5    # Show last 5 entries
      mc history play 3       # Replay history item #3
      mc h play 1             # Short alias
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(history_list)


@history_group.command("list")
@click.option("--limit", "-n", default=20, help="Number of entries to show")
def history_list(limit):
    """List recent playback history."""
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

        click.echo("\nReplay with: mc history play <number>")

    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@history_group.command("play")
@click.argument("number", type=int)
def history_play(number):
    """Replay an item from playback history by its number."""
    client = ensure_daemon()

    try:
        response = client.play(mode="history", index=number)

        if "error" in response:
            click.echo(f"Error: {response['error']}", err=True)
            sys.exit(1)

        track = response.get("track", {})
        title = track.get("title", track.get("source", "Unknown"))
        click.echo(f"{icon(chr(0x25B6))} Replaying: {title}")

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
            _terminate_daemon(pid)
            click.echo("Daemon stopped")
        else:
            click.echo("Daemon is not running")

    elif action == "restart":
        pid = get_daemon_pid()
        if pid:
            _terminate_daemon(pid)
            time.sleep(0.5)
        start_daemon_background()
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
            from .client import DaemonClient

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


@main.command("config")
def show_config():
    """Show configuration file locations."""
    config = get_config()

    click.echo("Configuration files:")
    click.echo(f"  Config:        {config.config_file}")
    click.echo(f"  Radios:        {config.radios_file}")
    click.echo(f"  History:       {config.history_file}")
    click.echo(f"  AI Tracks:     {config.ai_tracks_file}")
    click.echo(f"  AI Music:      {config.ai_music_dir}")
    click.echo(f"  YouTube Cache: {config.youtube_cache_dir}")
    click.echo(f"  Socket:        {config.socket_path}")
    click.echo(f"  PID:           {config.pid_file}")


@main.command("mood")
@click.argument("mood_name", required=False, default=None)
def list_moods(mood_name):
    """List available moods, or play a mood directly.

    \b
    Examples:
      mc mood              # List all moods
      mc mood focus        # Start focus-mood radio
    """
    if mood_name is not None:
        # Play mood-based radio directly
        client = ensure_daemon()
        try:
            response = client.play(mode="radio", mood=mood_name)
            if "error" in response:
                click.echo(f"Error: {response['error']}", err=True)
                sys.exit(1)
            track = response.get("track", {})
            title = track.get("title", track.get("source", "Unknown"))
            click.echo(f"{icon(chr(0x25B6))} Playing mood '{mood_name}': {title}")
        except ConnectionError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        return

    from .context.mood import MoodContext

    click.echo("Available moods:")
    for mood in MoodContext.get_all_moods():
        click.echo(f"  - {mood}")
    click.echo("\nPlay directly: mc mood <mood>")
    click.echo("Or use with: mc play --mood <mood>")


@main.group("ai", cls=AliasedGroup, invoke_without_command=True)
@click.pass_context
def ai_group(ctx):
    """Manage AI-generated music tracks.

    \b
    Commands:
      list          - Show all AI-generated tracks (default)
      play          - Generate and play AI music
      replay <num>  - Replay a track by number
      remove <num>  - Remove a track by number
      model         - Manage AI models

    \b
    Examples:
      mc ai                    # List all AI tracks
      mc ai list               # List all AI tracks
      mc ai play               # Generate music from current context
      mc ai play -p "jazz"     # Generate with custom prompt
      mc ai replay 3           # Replay track #3
      mc ai remove 2           # Remove track #2
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(ai_list)


@ai_group.command("list")
def ai_list():
    """List all AI-generated tracks."""
    client = ensure_daemon()

    try:
        tracks = client.ai_list()

        if not tracks:
            click.echo("No AI-generated tracks yet.")
            click.echo("Generate one with: mc ai play")
            return

        click.echo("AI-generated tracks:\n")
        for track in tracks:
            idx = track.get("index", "?")
            prompt = track.get("prompt", "Unknown")[:40]
            if len(track.get("prompt", "")) > 40:
                prompt += "..."
            duration = track.get("duration", "?")
            timestamp = track.get("timestamp", "")[:16]
            exists = track.get("file_exists", True)
            model = track.get("model", "musicgen-small")
            status = "" if exists else " [missing]"

            click.echo(f"  {idx:2}. [{timestamp}] {prompt} ({duration}s) [{model}]{status}")

        click.echo(f"\nTotal: {len(tracks)} track(s)")
        click.echo("Replay with: mc ai replay <number>")

    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@ai_group.command("play")
@click.option("-p", "--prompt", help="Custom prompt for AI music generation")
@click.option(
    "--mood",
    "-M",
    type=click.Choice(
        ["happy", "sad", "excited", "focus", "relaxed", "energetic", "melancholic", "peaceful"]
    ),
    help="Mood for context-aware generation",
)
@click.option("--duration", "-d", default=15, help="Duration in seconds (5-60)")
@click.option(
    "--model",
    "-m",
    help="Model to use (e.g., musicgen-small, musicgen-medium). See 'mc ai model'",
)
def ai_play(prompt, mood, duration, model):
    """Generate and play AI music.

    \b
    Without options, generates music based on current context:
    - Time of day (morning, afternoon, evening, night)
    - Day of week (weekday vs weekend)
    - Current session mood (if set)

    \b
    Examples:
      mc ai play                           # Context-aware generation
      mc ai play -p "jazz piano"           # Custom prompt
      mc ai play --mood focus              # With mood
      mc ai play -d 60                     # 60 second track
      mc ai play -m musicgen-medium        # Use specific model
    """
    client = ensure_daemon()

    # Validate model if specified
    if model:
        config = get_config()
        if not config.validate_ai_model(model):
            available = ", ".join(config.list_ai_models(enabled_only=True))
            click.echo(f"Error: Unknown or disabled model '{model}'", err=True)
            click.echo(f"Available models: {available}", err=True)
            click.echo("See all models with: mc ai model", err=True)
            sys.exit(1)

    # Show animation during generation
    animation = ComposingAnimation()
    animation.start()

    try:
        response = client.ai_play(prompt=prompt, duration=duration, mood=mood, model=model)

        animation.stop()

        if "error" in response:
            click.echo(f"Error: {response['error']}", err=True)
            sys.exit(1)

        track = response.get("track", {})
        title = track.get("title", "Unknown")
        used_prompt = response.get("prompt", prompt or "context-aware")
        model_used = track.get("metadata", {}).get("model", "unknown")

        click.echo(f"Playing: {title}")
        click.echo(f"Model: {model_used}")
        click.echo(f"Prompt: {used_prompt[:60]}{'...' if len(used_prompt) > 60 else ''}")

        # Suggest longer duration if using default
        if duration == 15:
            click.echo("\nTip: For longer tracks, use -d option (e.g., mc ai play -d 30)")

    except ConnectionError as e:
        animation.stop()
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@ai_group.command("replay")
@click.argument("index", type=int)
def ai_replay(index):
    """Replay an AI track by its number.

    If the audio file is missing, you'll be offered to regenerate it
    using the original prompt.
    """
    client = ensure_daemon()

    try:
        response = client.ai_replay(index)

        if response.get("status") == "file_missing":
            # File is missing, offer regeneration
            prompt = response.get("prompt", "Unknown")
            click.echo(f"Audio file not found for track #{index}")
            click.echo(f"Original prompt: {prompt[:60]}...")

            if click.confirm("Regenerate with the same prompt?", default=True):
                # Show animation during regeneration
                animation = ComposingAnimation()
                animation.start()

                response = client.ai_replay(index, regenerate=True)

                animation.stop()

                if "error" in response:
                    click.echo(f"Error: {response['error']}", err=True)
                    sys.exit(1)

                click.echo("Regenerated and playing!")
            else:
                click.echo("Cancelled.")
                return

        elif "error" in response:
            click.echo(f"Error: {response['error']}", err=True)
            sys.exit(1)

        else:
            track = response.get("track", {})
            title = track.get("title", "Unknown")
            regenerated = response.get("regenerated", False)

            if regenerated:
                click.echo(f"Regenerated: {title}")
            else:
                click.echo(f"Playing: {title}")

    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@ai_group.group("model", cls=AliasedGroup, invoke_without_command=True)
@click.pass_context
def ai_models_group(ctx):
    """Manage AI models.

    \b
    Commands:
      list          - Show all models with download status (default)
      download      - Download a model to cache
      delete        - Delete a cached model
      default       - Set the default model

    \b
    Examples:
      mc ai model                    # List all models
      mc ai model list               # List all models
      mc ai model download musicgen-medium
      mc ai model delete musicgen-large
      mc ai model default musicgen-small
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(ai_models_list)


@ai_models_group.command("list")
def ai_models_list():
    """List available AI models with download status and sizes."""
    from .model_manager import ModelManager

    config = get_config()
    manager = ModelManager(config)

    models = manager.list_models()
    if not models:
        click.echo("No AI models configured.")
        click.echo("Add models to config.toml under [ai.models]")
        return

    click.echo("Available AI models:\n")

    # Group models by type
    type_descriptions = {
        "musicgen": "MusicGen (Meta) - Music generation",
        "audioldm": "AudioLDM (CVSSP) - Sound effects & ambient audio",
        "bark": "Bark (Suno) - Speech synthesis & audio",
    }

    current_type = None
    for model in models:
        # Print type header if type changed
        if model.model_type != current_type:
            if current_type is not None:
                click.echo()
            current_type = model.model_type
            click.echo(f"  {type_descriptions.get(model.model_type, model.model_type)}:")

        # Build status string
        default_flag = " (default)" if model.is_default else ""
        disabled_flag = " [disabled]" if not model.enabled else ""

        # Build size string
        if model.is_downloaded and model.cached_size_gb:
            size_str = f"[downloaded: {model.cached_size_gb:.1f} GB]"
        elif model.expected_size_gb > 0:
            size_str = f"[not downloaded, ~{model.expected_size_gb:.1f} GB]"
        else:
            size_str = "[not downloaded]"

        # Build description
        desc = f" - {model.description}" if model.description else ""

        click.echo(f"    - {model.id}{default_flag} {size_str}{disabled_flag}{desc}")

    click.echo()

    # Print summary
    summary = manager.get_summary()
    click.echo(f"Default: {summary['default_model']}")
    if summary["downloaded"] > 0:
        click.echo(
            f"Downloaded: {summary['downloaded']}/{summary['total']} models "
            f"({summary['total_size_gb']:.1f} GB total)"
        )

    click.echo("\nCommands:")
    click.echo("  mc ai model download <model_id>    - Download a model")
    click.echo("  mc ai model delete <model_id>      - Delete cached model")
    click.echo("  mc ai model default <model_id>     - Set default model")


@ai_models_group.command("download")
@click.argument("model_id")
def ai_models_download(model_id):
    """Download an AI model to the HuggingFace cache.

    The model will be downloaded with a progress bar showing the download status.
    This may take a while depending on model size and connection speed.

    \b
    Examples:
      mc ai model download musicgen-medium
      mc ai model download audioldm-s-full-v2
    """
    from .model_manager import ModelManager

    config = get_config()
    manager = ModelManager(config)

    # Validate model
    is_valid, error = manager.validate_model(model_id)
    if not is_valid:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)

    model = manager.get_model(model_id)
    if model is None:
        click.echo(f"Error: Model '{model_id}' not found", err=True)
        sys.exit(1)

    if model.is_downloaded:
        size = f"{model.cached_size_gb:.1f} GB" if model.cached_size_gb else "unknown size"
        click.echo(f"Model '{model_id}' is already downloaded ({size})")
        return

    click.echo(f"Downloading {model_id} ({model.hf_model_id})...")
    if model.expected_size_gb > 0:
        click.echo(f"Expected size: ~{model.expected_size_gb:.1f} GB")
    click.echo("This may take a while depending on your connection speed.\n")

    success, message = manager.download_model(model_id)

    if success:
        click.echo(f"\n{message}")
        click.echo(f"You can now use it with: mc ai play -m {model_id}")
    else:
        click.echo(f"\nError: {message}", err=True)
        sys.exit(1)


@ai_models_group.command("delete")
@click.argument("model_id")
def ai_models_delete(model_id):
    """Delete a model from the HuggingFace cache.

    This will free up disk space but you'll need to re-download
    the model to use it again.

    \b
    Examples:
      mc ai model delete musicgen-large
      mc ai model delete bark
    """
    from .model_manager import ModelManager

    config = get_config()
    manager = ModelManager(config)

    model = manager.get_model(model_id)
    if model is None:
        available = ", ".join(m.id for m in manager.list_models())
        click.echo(f"Error: Unknown model '{model_id}'", err=True)
        click.echo(f"Available models: {available}", err=True)
        sys.exit(1)

    if not model.is_downloaded:
        click.echo(f"Model '{model_id}' is not downloaded.", err=True)
        sys.exit(1)

    # Show model info
    size = f"{model.cached_size_gb:.1f} GB" if model.cached_size_gb else "unknown size"
    click.echo(f"Model: {model_id} ({size})")
    if model.description:
        click.echo(f"Description: {model.description}")

    # Warn if deleting default
    if model.is_default:
        click.echo("\nWarning: This is currently the default model!", err=True)

    # Confirm deletion
    if not click.confirm("\nDelete this model from cache?", default=False):
        click.echo("Cancelled.")
        return

    success, message, _ = manager.delete_model(model_id)

    if success:
        click.echo(f"\n{message}")
    else:
        click.echo(f"\nError: {message}", err=True)
        sys.exit(1)


@ai_models_group.command("default")
@click.argument("model_id")
def ai_models_set_default(model_id):
    """Set the default AI model used for generation.

    The default model is used when you don't specify -m option in 'ai play'.

    \b
    Examples:
      mc ai model default musicgen-medium
      mc ai model default audioldm-s-full-v2
    """
    from .model_manager import ModelManager

    config = get_config()
    manager = ModelManager(config)

    # Validate and set
    success, message = manager.set_default_model(model_id)

    if success:
        click.echo(message)
        click.echo("Use with: mc ai play")
    else:
        click.echo(f"Error: {message}", err=True)
        sys.exit(1)


@ai_group.command("remove")
@click.argument("index", type=int)
def ai_remove(index):
    """Remove an AI track and its audio file."""
    client = ensure_daemon()

    try:
        # First get the track info to show confirmation
        tracks = client.ai_list()
        track = next((t for t in tracks if t.get("index") == index), None)

        if not track:
            if not tracks:
                click.echo("No AI tracks to remove.", err=True)
            else:
                click.echo(
                    f"Invalid track number. Choose between 1 and {len(tracks)}.",
                    err=True,
                )
            sys.exit(1)

        prompt = track.get("prompt", "Unknown")
        click.echo(f"Track #{index}: {prompt[:60]}...")

        if not click.confirm("Remove this track and its audio file?", default=False):
            click.echo("Cancelled.")
            return

        response = client.ai_remove(index)

        if "error" in response:
            click.echo(f"Error: {response['error']}", err=True)
            sys.exit(1)

        click.echo(f"Removed: {response.get('prompt', 'Unknown')[:50]}...")

    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.group("yt", cls=AliasedGroup, invoke_without_command=True)
@click.pass_context
def youtube_group(ctx):
    """Manage cached YouTube audio for offline playback.

    \b
    Commands:
      list          - Show all cached YouTube tracks (default)
      play <number> - Play a cached track by number (offline)
      remove <num>  - Remove a cached track
      clear         - Clear all cached tracks

    \b
    Examples:
      mc yt              # List cached tracks
      mc yt list         # List cached tracks
      mc yt play 3       # Play cached track #3
      mc yt remove 1     # Remove track #1
      mc yt clear        # Clear entire cache
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(youtube_cached)


@youtube_group.command("list")
def youtube_cached():
    client = ensure_daemon()

    try:
        response = client.youtube_cached()

        if "error" in response:
            click.echo(f"Error: {response['error']}", err=True)
            sys.exit(1)

        tracks = response.get("tracks", [])
        stats = response.get("stats", {})

        if not tracks:
            click.echo("No YouTube history yet.")
            click.echo("Play a YouTube URL to add it to history:")
            click.echo("  mc play 'https://youtube.com/watch?v=...'")
            return

        click.echo("YouTube replay history:\n")
        for track in tracks:
            idx = track.get("index", "?")
            title = track.get("title", "Unknown")[:45]
            if len(track.get("title", "")) > 45:
                title += "..."
            duration = track.get("duration")
            dur_str = f"{int(duration // 60)}:{int(duration % 60):02d}" if duration else "?"
            cached = " [cached]" if track.get("file_exists") else ""

            click.echo(f"  {idx:2}. {title} ({dur_str}){cached}")

        click.echo(f"\nTotal: {stats.get('count', 0)} track(s)")
        click.echo("Replay with: mc yt play <number>")

    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@youtube_group.command("play")
@click.argument("number", type=int)
def youtube_play(number):
    client = ensure_daemon()

    try:
        response = client.youtube_play(number)

        if "error" in response:
            click.echo(f"Error: {response['error']}", err=True)
            sys.exit(1)

        track = response.get("track", {})
        title = track.get("title", "Unknown")
        click.echo(f"{icon(chr(0x25B6))} Playing: {title}")

    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@youtube_group.command("remove")
@click.argument("number", type=int)
def youtube_remove(number):
    client = ensure_daemon()

    try:
        cached_response = client.youtube_cached()
        tracks = cached_response.get("tracks", [])
        track = next((t for t in tracks if t.get("index") == number), None)

        if not track:
            if not tracks:
                click.echo("No YouTube history to remove.", err=True)
            else:
                click.echo(f"Invalid number. Choose between 1 and {len(tracks)}.", err=True)
            sys.exit(1)

        title = track.get("title", "Unknown")
        click.echo(f"Track #{number}: {title}")

        if not click.confirm("Remove this entry?", default=False):
            click.echo("Cancelled.")
            return

        response = client.youtube_remove(number)

        if "error" in response:
            click.echo(f"Error: {response['error']}", err=True)
            sys.exit(1)

        click.echo(f"Removed: {response.get('title', 'Unknown')}")

    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@youtube_group.command("clear")
def youtube_clear():
    client = ensure_daemon()

    try:
        cached_response = client.youtube_cached()
        stats = cached_response.get("stats", {})
        count = stats.get("count", 0)

        if count == 0:
            click.echo("History is already empty.")
            return

        click.echo(f"This will remove {count} YouTube history entry(s).")

        if not click.confirm("Clear entire YouTube history?", default=False):
            click.echo("Cancelled.")
            return

        response = client.youtube_clear()

        if "error" in response:
            click.echo(f"Error: {response['error']}", err=True)
            sys.exit(1)

        removed = response.get("removed_count", 0)
        click.echo(f"Cleared {removed} entry(s).")

    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@radios_group.command("update")
def radio_update():
    """Update radio stations list after version upgrade."""
    config = get_config()

    new_stations = config.get_new_default_stations()

    if not new_stations:
        click.echo("Your radio stations are up to date!")
        installed_version = config.get_installed_version()
        if installed_version != __version__:
            config.update_version()
            click.echo(f"Config version updated to {__version__}")
        return

    click.echo(f"Found {len(new_stations)} new radio station(s) available:\n")
    for name, _url in new_stations[:10]:  # Show first 10
        click.echo(f"  + {name}")
    if len(new_stations) > 10:
        click.echo(f"  ... and {len(new_stations) - 10} more\n")
    else:
        click.echo()

    click.echo("How would you like to update your radio stations?\n")
    click.echo("  [M] Merge   - Add new stations to your existing list (recommended)")
    click.echo("  [O] Overwrite - Replace with new defaults (backs up old file)")
    click.echo("  [K] Keep    - Keep your current stations unchanged\n")

    choice = click.prompt(
        "Your choice",
        type=click.Choice(["M", "O", "K", "m", "o", "k"], case_sensitive=False),
        default="M",
    )

    choice = choice.upper()

    if choice == "M":
        added = config.merge_radios()
        click.echo(f"\nAdded {added} new station(s) to your radios.txt")
        click.echo("Run 'mc radio' to see the full list")

    elif choice == "O":
        backup_path = config.backup_radios_path()
        config.overwrite_radios()
        click.echo("\nRadio stations replaced with new defaults")
        click.echo(f"Your old stations backed up to: {backup_path}")

    else:  # K
        click.echo("\nKept your existing radio stations unchanged")

    config.update_version()
    click.echo(f"Config version updated to {__version__}")


@main.command("update-radios", hidden=True)
@click.pass_context
def update_radios_legacy(ctx):
    """Update radio stations (deprecated, use 'mc radio update')."""
    ctx.invoke(radio_update)


# ---------------------------------------------------------------------------
# Register aliases (hidden — don't appear in --help but work on the CLI)
# ---------------------------------------------------------------------------

# Task 1.3: Old group/command names -> hidden aliases on main
_register_alias(main, "radios", "radio")
_register_alias(main, "youtube", "yt")
_register_alias(main, "moods", "mood")
_register_alias(main, "volume", "vol")

# Task 1.4: Playback single-letter/short aliases
_register_alias(main, "s", "stop")
_register_alias(main, "pp", "pause")
_register_alias(main, "r", "resume")
_register_alias(main, "n", "next")
_register_alias(main, "st", "status")
_register_alias(main, "h", "history")

# Task 1.3: Inside yt group, "cached" -> "list"
_register_alias(youtube_group, "cached", "list")  # type: ignore[arg-type]

# Task 2.6: "models" -> "model" (old name), "set-default" -> "default" (old name)
_register_alias(ai_group, "models", "model")  # type: ignore[arg-type]
_register_alias(ai_models_group, "set-default", "default")  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
