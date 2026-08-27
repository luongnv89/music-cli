"""Cloud provider credential management and reachability probes (`mc cloud`).

Public surface (issue #134, task P1.3):

- ``mc cloud key set|get|delete|list <provider>`` — keyring-backed secret
  storage (thin facades over :mod:`music_cli.cloud.secrets`)
- ``mc cloud ping [provider]`` — one trivial request per adapter, reporting
  reachable/unreachable with latency; key values are never printed
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time

import click

from ..cloud import secrets as _secrets
from .app import main
from .common import AliasedGroup

logger = logging.getLogger(__name__)

# Keyring namespace so credentials never touch config files, env vars, or git.
# Kept as an alias of music_cli.cloud.secrets.SERVICE (PR #155 name preserved).
KEYRING_SERVICE = _secrets.SERVICE

# Providers with credential support. Extend as adapters land (issue #131).
SUPPORTED_PROVIDERS = _secrets.PROVIDERS

# Cheapest text model per provider for the trivial ping request (audio models
# are async queue jobs — much too heavy for a reachability probe).
_PING_MODEL = {
    "gmi": "MiniMax-H3",
    "openrouter": "minimax/minimax-m3",
}


def _load_keyring():
    """Return the ``keyring`` module (tests patch this seam)."""
    try:
        return _secrets.load_keyring()
    except _secrets.KeyringUnavailableError as exc:
        raise click.ClickException(str(exc)) from exc


def _validate_provider(provider: str) -> str:
    if provider not in SUPPORTED_PROVIDERS:
        supported = ", ".join(SUPPORTED_PROVIDERS)
        raise click.BadParameter(f"unsupported provider '{provider}' (supported: {supported})")
    return provider


def _stored_providers() -> list[str]:
    return _secrets.stored_providers(keyring_module=_load_keyring())


def _build_adapter(provider: str, api_key: str):
    """Build the adapter for ``provider`` (tests patch this factory)."""
    from ..cloud.gmi import GMIAdapter
    from ..cloud.openrouter import OpenRouterAdapter

    if provider == "gmi":
        return GMIAdapter(api_key)
    return OpenRouterAdapter(api_key)


async def _ping_provider(provider: str, api_key: str, timeout: float) -> dict:
    """One trivial chat request against ``provider``; never raises.

    The result dict carries reachability, latency, and a short error string.
    The API key itself never appears in the payload we hand back (adapter
    errors quote response bodies, not request headers).
    """
    model = _PING_MODEL[provider]
    adapter = _build_adapter(provider, api_key)
    start = time.monotonic()
    try:
        await asyncio.wait_for(
            adapter.chat(model=model, prompt="ping", params={"max_tokens": 1}),
            timeout,
        )
        return {
            "provider": provider,
            "model": model,
            "ok": True,
            "latency": time.monotonic() - start,
            "error": None,
        }
    except Exception as exc:
        return {
            "provider": provider,
            "model": model,
            "ok": False,
            "latency": time.monotonic() - start,
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        await adapter.aclose()


@main.group("cloud", cls=AliasedGroup)
@click.pass_context
def cloud_group(ctx):
    """Manage cloud provider credentials and services.

    Examples:

    \b
        mc cloud key set gmi          # store an API key in the OS keyring
        mc cloud key get gmi          # read a stored key back
        mc cloud key list             # providers with stored keys
        mc cloud ping                 # probe every configured provider
        mc cloud ping gmi             # probe one provider
    """


@cloud_group.group("key")
def key_group():
    """Store API keys in the system keyring (never in files or env vars)."""


@key_group.command("set")
@click.argument("provider")
def key_set(provider):
    """Securely store the API key for PROVIDER in the system keyring."""
    _validate_provider(provider)
    api_key = click.prompt(f"{provider.upper()} API key", hide_input=True)
    _secrets.store_api_key(provider, api_key, keyring_module=_load_keyring())
    click.echo(f"API key for '{provider}' stored in the system keyring.")


@key_group.command("get")
@click.argument("provider")
def key_get(provider):
    """Print the stored API key for PROVIDER (use sparingly — it is a secret)."""
    _validate_provider(provider)
    value = _secrets.get_api_key(provider, keyring_module=_load_keyring())
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
        _secrets.delete_api_key(provider, keyring_module=keyring)
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


@cloud_group.command("ping")
@click.argument("provider", required=False)
@click.option("--timeout", default=15.0, show_default=True, type=float)
def cloud_ping(provider, timeout):
    """Probe cloud adapters with a trivial request; report reachability.

    Reports reachable/unreachable plus latency for each provider (or just
    PROVIDER when given). Never prints an API key value.
    """
    if provider is not None:
        _validate_provider(provider)
        providers: tuple[str, ...] = (provider,)
    else:
        providers = SUPPORTED_PROVIDERS

    results = []
    for name in providers:
        api_key = _secrets.get_api_key(name, keyring_module=_load_keyring())
        if api_key is None:
            results.append(
                {
                    "provider": name,
                    "model": _PING_MODEL[name],
                    "ok": False,
                    "latency": 0.0,
                    "error": f"no API key stored (set one with: mc cloud key set {name})",
                }
            )
            continue
        results.append(asyncio.run(_ping_provider(name, api_key, timeout)))

    for res in results:
        if res["ok"]:
            click.echo(f"{res['provider']}: reachable ({res['model']}, {res['latency']:.2f}s)")
        else:
            click.echo(f"{res['provider']}: unreachable ({res['error']})", err=True)
    if any(not res["ok"] for res in results):
        sys.exit(1)


# Registered at the bottom so cloud_smoke's own `from .cloud import` sees the
# fully-initialized names above (issue #152).
from .cloud_smoke import register_cloud_smoke  # noqa: E402

register_cloud_smoke(cloud_group)
