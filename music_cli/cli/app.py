"""The root `mc` command group and the once-per-session update check."""

import logging
import os

import click

from .. import __version__
from ..config import get_config
from .common import AliasedGroup

logger = logging.getLogger(__name__)

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
        from .playback import status

        ctx.invoke(status)
