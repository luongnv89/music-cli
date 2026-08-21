"""Playback transport commands: play, stop, pause, resume, status, next, vol."""

import sys
from dataclasses import dataclass
from pathlib import Path

import click

from .. import __github_url__, __version__
from ..client import PlayRequest
from ..config import get_config
from ..platform import is_windows
from ..player.ffplay import check_ffplay_available
from . import runtime
from .app import main
from .common import get_random_quote, icon


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


def _resolve_local_path(source: str) -> str:
    """Resolve a local playback source against the CLI's cwd.

    The daemon is a long-running background process started once with its
    own cwd (see start_daemon_background) — it is generally not the cwd of
    the terminal a later `play` command runs in. A still-relative path
    handed to the daemon therefore gets checked against the *daemon's* cwd,
    not the user's, and silently misses even when the file is right there.
    Resolve it to an absolute path here, while we still have the correct
    cwd, so it survives the trip over IPC unchanged. Leave anything that
    doesn't exist relative to cwd as-is so the daemon's fallback to the
    configured music directory keeps working.
    """
    path = Path(source)
    if not path.is_absolute() and path.exists():
        return str(path.resolve())
    return source


@dataclass(frozen=True)
class PlayOptions:
    """Options accepted by `mc play`, grouped so the command stays thin."""

    source: str | None = None
    mode: str | None = None
    mood: str | None = None
    auto: bool = False
    duration: int = 15
    index: int | None = None

    # Click's flat callback kwarg names accepted by from_click.
    _CLICK_KEYS = frozenset({"source", "source_flag", "mode", "mood", "auto", "duration", "index"})

    @classmethod
    def from_click(cls, click_args: dict) -> "PlayOptions":
        """Build options from Click's flat callback kwargs, passed as one mapping."""
        unknown = set(click_args) - cls._CLICK_KEYS
        if unknown:
            raise TypeError(f"Unexpected play options: {sorted(unknown)}")
        # Positional SOURCE takes priority over -s flag
        effective_source = click_args.get("source")
        if effective_source is None:
            effective_source = click_args.get("source_flag")
        return cls(
            source=effective_source,
            mode=click_args.get("mode"),
            mood=click_args.get("mood"),
            auto=click_args.get("auto", False),
            duration=click_args.get("duration", 15),
            index=click_args.get("index"),
        )


def _require_ffplay() -> None:
    """Exit with install guidance when ffplay is unavailable."""
    if check_ffplay_available():
        return
    click.echo("Error: ffplay not found. Please install FFmpeg.", err=True)
    if is_windows():
        click.echo("  Windows: choco install ffmpeg", err=True)
        click.echo("       or: winget install ffmpeg", err=True)
        click.echo("       or: scoop install ffmpeg", err=True)
    else:
        click.echo("  macOS: brew install ffmpeg", err=True)
        click.echo("  Linux: apt install ffmpeg", err=True)
    sys.exit(1)


def _warn_deprecated_modes(mode: str | None) -> None:
    """Emit deprecation notices for modes superseded by dedicated commands."""
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


def _detect_mode_and_source(options: PlayOptions) -> tuple[str, str | None]:
    """Resolve the effective (mode, source), honouring smart auto-detection."""
    # Task 2.1: Smart auto-detection when --mode is NOT given
    if options.mode is None:
        mode, detected_source = _detect_play_mode(options.source)
        return mode, detected_source
    # If mode was explicitly given, keep the old behaviour
    # (effective_source from flag/positional is used as-is)
    return options.mode, options.source


def _render_play_response(response: dict, auto: bool) -> None:
    """Print the daemon's play response, exiting on an error payload."""
    if "error" in response:
        click.echo(f"Error: {response['error']}", err=True)
        sys.exit(1)

    track = response.get("track", {})
    title = track.get("title", track.get("source", "Unknown"))
    source_type = track.get("source_type", "unknown")

    click.echo(f"{icon(chr(0x25B6))} Playing: {title} [{source_type}]")
    if auto:
        click.echo("  Auto-play enabled (shuffle mode)")


def _run_play(options: PlayOptions) -> None:
    """Send the play request to the daemon and render the outcome."""
    _require_ffplay()

    _warn_deprecated_modes(options.mode)

    mode, source = _detect_mode_and_source(options)

    # Issue #18: a relative local path must be resolved before it crosses
    # the IPC boundary to the daemon (see _resolve_local_path).
    if mode == "local" and source:
        source = _resolve_local_path(source)

    client = runtime.ensure_daemon()

    # Show animation for AI generation
    animation = None
    if mode == "ai":
        animation = runtime.ComposingAnimation()
        animation.start()

    try:
        response = client.play(
            PlayRequest(
                mode=mode,
                source=source,
                mood=options.mood,
                auto=options.auto,
                duration=options.duration,
                index=options.index,
            )
        )

        if animation:
            animation.stop()

        _render_play_response(response, options.auto)

    except ConnectionError as e:
        if animation:
            animation.stop()
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


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
def play(source, **options):
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
    _run_play(PlayOptions.from_click({"source": source, **options}))


@main.command()
def stop():
    """Stop playback."""
    client = runtime.ensure_daemon()

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
    client = runtime.ensure_daemon()

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
    client = runtime.ensure_daemon()

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
    client = runtime.ensure_daemon()

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
    client = runtime.ensure_daemon()

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
    client = runtime.ensure_daemon()

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
