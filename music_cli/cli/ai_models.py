"""AI model management commands (`mc ai model ...`)."""

import sys

import click

from ..config import get_config
from .ai import ai_models_group


@ai_models_group.command("list")
def ai_models_list():
    """List available AI models with download status and sizes."""
    from ..model_manager import ModelManager

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
        "minimax_music3": "MiniMax Music 3 - Lyrics-conditioned music",
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
    from ..model_manager import ModelManager

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
    from ..model_manager import ModelManager

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
    from ..model_manager import ModelManager

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
