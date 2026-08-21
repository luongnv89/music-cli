"""Radio station management commands."""

import shutil
import sys

import click

from .. import __version__
from ..config import get_config
from . import runtime
from .app import main
from .common import AliasedGroup, icon


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
    client = runtime.ensure_daemon()

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
