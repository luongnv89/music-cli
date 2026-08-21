"""Configuration and mood commands."""

import sys

import click

from ..client import PlayRequest
from ..config import get_config
from . import runtime
from .app import main
from .common import icon


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
        client = runtime.ensure_daemon()
        try:
            response = client.play(PlayRequest(mode="radio", mood=mood_name))
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

    from ..context.mood import MoodContext

    click.echo("Available moods:")
    for mood in MoodContext.get_all_moods():
        click.echo(f"  - {mood}")
    click.echo("\nPlay directly: mc mood <mood>")
    click.echo("Or use with: mc play --mood <mood>")
