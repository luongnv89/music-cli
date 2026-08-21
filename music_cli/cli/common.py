"""Shared presentation helpers and the aliased Click group class."""

import os

import click

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


def _register_alias(group: click.Group, alias: str, target: str) -> None:
    """Register a hidden alias on an AliasedGroup."""
    cast_group: AliasedGroup = group  # type: ignore[assignment]
    cast_group.add_alias(alias, target)
