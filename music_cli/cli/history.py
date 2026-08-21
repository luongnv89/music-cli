"""Playback history commands."""

import sys

import click

from ..client import PlayRequest
from . import runtime
from .app import main
from .common import AliasedGroup, icon


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
    client = runtime.ensure_daemon()

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
    client = runtime.ensure_daemon()

    try:
        response = client.play(PlayRequest(mode="history", index=number))

        if "error" in response:
            click.echo(f"Error: {response['error']}", err=True)
            sys.exit(1)

        track = response.get("track", {})
        title = track.get("title", track.get("source", "Unknown"))
        click.echo(f"{icon(chr(0x25B6))} Replaying: {title}")

    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
