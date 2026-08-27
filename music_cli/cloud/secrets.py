"""Keyring-backed secret storage for cloud provider API keys (#134, task P1.3).

The only sanctioned home for provider credentials is the OS keyring via the
optional ``keyring`` package (``pip install 'coder-music-cli[gmi]'``). Nothing
in this module ever writes a secret to a file, an environment variable, or a
log line — values travel in memory only, and callers must not echo them.

The ``mc cloud key`` commands (``music_cli.cli.cloud``) are thin Click
facades over the functions here; the indirection seam they patch in tests is
``music_cli.cli.cloud._load_keyring``, so every wrapper accepts an optional
already-loaded ``keyring`` module.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Keyring service (namespace) shared by every provider credential. Keep in
#: sync with the value first shipped by PR #155 so existing credentials keep
#: resolving.
SERVICE = "coder-music-cli"

#: Providers with credential + adapter support (adapters landed in #133).
PROVIDERS = ("gmi", "openrouter")


class KeyringUnavailable(RuntimeError):
    """The optional ``keyring`` dependency is not installed."""


def load_keyring() -> Any:
    """Import and return the ``keyring`` module.

    Raises
    ------
    KeyringUnavailable
        If the optional ``keyring`` package is missing.
    """
    try:
        import keyring
    except ImportError as exc:
        raise KeyringUnavailable(
            "The 'keyring' package is not installed.\n"
            "Install it with: pip install 'coder-music-cli[gmi]'"
        ) from exc
    return keyring


def store_api_key(provider: str, api_key: str, keyring_module: Any | None = None) -> None:
    """Store ``api_key`` for ``provider`` in the OS keyring."""
    keyring = keyring_module if keyring_module is not None else load_keyring()
    keyring.set_password(SERVICE, provider, api_key)


def get_api_key(provider: str, keyring_module: Any | None = None) -> str | None:
    """Return the stored key for ``provider``, or ``None`` when absent."""
    keyring = keyring_module if keyring_module is not None else load_keyring()
    return keyring.get_password(SERVICE, provider)


def delete_api_key(provider: str, keyring_module: Any | None = None) -> None:
    """Delete the stored key for ``provider``.

    Propagates the backend's error when no credential exists (``keyring``
    backends vary; the CLI layer maps that onto a friendly message).
    """
    keyring = keyring_module if keyring_module is not None else load_keyring()
    keyring.delete_password(SERVICE, provider)


def stored_providers(
    keyring_module: Any | None = None,
    providers: tuple[str, ...] = PROVIDERS,
) -> list[str]:
    """Return the subset of ``providers`` that have a stored key."""
    keyring = keyring_module if keyring_module is not None else load_keyring()
    present = []
    for provider in providers:
        try:
            if keyring.get_password(SERVICE, provider) is not None:
                present.append(provider)
        except Exception as exc:  # keyring backends vary widely
            logger.debug("keyring lookup failed for '%s': %s", provider, exc)
    return present
