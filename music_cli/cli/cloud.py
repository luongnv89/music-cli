"""Cloud provider credential management (`mc cloud`)."""

from __future__ import annotations

import logging
import sys

import click

from .app import main
from .common import AliasedGroup

logger = logging.getLogger(__name__)

# Keyring namespace so credentials never touch config files, env vars, or git.
KEYRING_SERVICE = "coder-music-cli"

# Providers with credential support. Extend as adapters land (issue #131).
SUPPORTED_PROVIDERS = ("gmi",)


def _load_keyring():
    try:
        import keyring
    except ImportError as exc:
        raise click.ClickException(
            "The 'keyring' package is not installed.\n"
            "Install it with: pip install 'coder-music-cli[gmi]'"
        ) from exc
    return keyring


def _validate_provider(provider: str) -> str:
    if provider not in SUPPORTED_PROVIDERS:
        supported = ", ".join(SUPPORTED_PROVIDERS)
        raise click.BadParameter(f"unsupported provider '{provider}' (supported: {supported})")
    return provider


def _stored_providers() -> list[str]:
    keyring = _load_keyring()
    present = []
    for provider in SUPPORTED_PROVIDERS:
        try:
            if keyring.get_password(KEYRING_SERVICE, provider) is not None:
                present.append(provider)
        except Exception as exc:  # keyring backends vary widely
            logger.debug("keyring lookup failed for '%s': %s", provider, exc)
    return present


@main.group("cloud", cls=AliasedGroup)
@click.pass_context
def cloud_group(ctx):
    """Manage cloud provider credentials and services."""


@cloud_group.group("key")
def key_group():
    """Store API keys in the system keyring (never in files or env vars)."""


@key_group.command("set")
@click.argument("provider")
def key_set(provider):
    """Securely store the API key for PROVIDER in the system keyring."""
    _validate_provider(provider)
    api_key = click.prompt(f"{provider.upper()} API key", hide_input=True)
    keyring = _load_keyring()
    keyring.set_password(KEYRING_SERVICE, provider, api_key)
    click.echo(f"API key for '{provider}' stored in the system keyring.")


@key_group.command("get")
@click.argument("provider")
def key_get(provider):
    """Print the stored API key for PROVIDER (use sparingly — it is a secret)."""
    _validate_provider(provider)
    keyring = _load_keyring()
    value = keyring.get_password(KEYRING_SERVICE, provider)
    if value is None:
        click.echo(
            f"No API key stored for '{provider}'. Set one with: mc cloud key set {provider}",
            err=True,
        )
        sys.exit(1)
    click.echo(value)


@key_group.command("delete")
@click.confirmation_option(prompt="Delete the stored API key?")
@click.argument("provider")
def key_delete(provider):
    """Remove the stored API key for PROVIDER from the system keyring."""
    _validate_provider(provider)
    keyring = _load_keyring()
    try:
        keyring.delete_password(KEYRING_SERVICE, provider)
    except Exception as exc:
        click.echo(f"No stored API key found for '{provider}': {exc}", err=True)
        sys.exit(1)
    click.echo(f"API key for '{provider}' deleted.")


@key_group.command("list")
def key_list():
    """List providers with a stored API key (values are never shown)."""
    stored = _stored_providers()
    if not stored:
        click.echo("No cloud API keys stored.")
        return
    click.echo("Stored cloud API keys:")
    for provider in stored:
        click.echo(f"  - {provider}")


# Registered at the bottom so cloud_smoke's own `from .cloud import` sees the
# fully-initialized names above (issue #152).
from .cloud_smoke import register_cloud_smoke  # noqa: E402

register_cloud_smoke(cloud_group)
