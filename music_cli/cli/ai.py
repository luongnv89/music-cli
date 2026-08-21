"""AI-generated music commands."""

import sys

import click

from ..config import get_config
from . import runtime
from .app import main
from .common import AliasedGroup


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
    client = runtime.ensure_daemon()

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
@click.option(
    "--duration",
    "-d",
    default=15,
    type=click.IntRange(min=2, max=300),
    help="Duration in seconds (model-specific; MiniMax supports 5-300)",
)
@click.option(
    "--model",
    "-m",
    help="Model to use (e.g., musicgen-small, minimax-music3). See 'mc ai model'",
)
@click.option(
    "--lyrics",
    help="Lyrics for lyrics-conditioned models such as minimax-music3",
)
def ai_play(prompt, mood, duration, model, lyrics):
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
      mc ai play -m minimax-music3 --lyrics "[Verse]..."  # Lyrics-conditioned song
    """
    client = runtime.ensure_daemon()

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
    animation = runtime.ComposingAnimation()
    animation.start()

    try:
        response = client.ai_play(
            prompt=prompt,
            duration=duration,
            mood=mood,
            model=model,
            lyrics=lyrics,
        )

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
    client = runtime.ensure_daemon()

    try:
        response = client.ai_replay(index)

        if response.get("status") == "file_missing":
            # File is missing, offer regeneration
            prompt = response.get("prompt", "Unknown")
            click.echo(f"Audio file not found for track #{index}")
            click.echo(f"Original prompt: {prompt[:60]}...")

            if click.confirm("Regenerate with the same prompt?", default=True):
                # Show animation during regeneration
                animation = runtime.ComposingAnimation()
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
        from .ai_models import ai_models_list

        ctx.invoke(ai_models_list)


@ai_group.command("remove")
@click.argument("index", type=int)
def ai_remove(index):
    """Remove an AI track and its audio file."""
    client = runtime.ensure_daemon()

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
