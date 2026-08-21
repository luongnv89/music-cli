"""YouTube cache/history commands."""

import sys

import click

from . import runtime
from .app import main
from .common import AliasedGroup, icon


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
    client = runtime.ensure_daemon()

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
    client = runtime.ensure_daemon()

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
    client = runtime.ensure_daemon()

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
    client = runtime.ensure_daemon()

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
