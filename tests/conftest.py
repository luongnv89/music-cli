"""Shared pytest fixtures for the music-cli test suite.

The single most important contract here is **hermetic isolation**: the suite must
never read or write the developer's real ``~/.config/music-cli/``. Before this
conftest, ``Config.__init__`` created ``config.toml``, ``radios.txt``,
``history.jsonl`` and ``ai_tracks.json`` in the real home as a constructor side
effect, and ``get_config()`` was a module-level singleton that leaked that state
across tests — so coverage was non-deterministic (53%–55%) and the suite could
spawn a real background daemon (issue #43 / F-TEST-007).

``isolate_home`` (autouse) points ``HOME`` / ``XDG_CONFIG_HOME`` (and Windows
``LOCALAPPDATA``) at a per-test ``tmp_path`` and resets the ``get_config``
singleton before every test. This makes the config directory resolve under the
temp dir for every code path, so:
  * the real ``~/.config/music-cli/`` is left untouched,
  * coverage is identical run-to-run and matches a fresh ``HOME``, and
  * the daemon's socket/pid files resolve under temp, so a stray ``start()``
    can't bind the real home socket or leave a live process.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import music_cli.config as _config_module


@pytest.fixture(scope="session")
def _isolated_home(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A session-scoped temp HOME, isolated from the developer's real home.

    Session scope (not per-test) so config default files are written once, not
    rebuilt for every test — that keeps the suite fast (the cold-start 3×
    variance in F-TEST-007 came from per-run recreation, which we avoid by
    writing the defaults once and reusing them). Every test still gets a clean
    ``get_config()`` singleton via ``isolate_config_singleton``.
    """
    home = tmp_path_factory.mktemp("music-cli-home")
    (home / ".config").mkdir(parents=True, exist_ok=True)
    (home / "AppData" / "Local").mkdir(parents=True, exist_ok=True)
    return home


@pytest.fixture(autouse=True)
def isolate_home(_isolated_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect HOME/config to a temp dir, reset the config singleton, and
    block real daemon spawning.

    Autouse so every test — including ones that construct ``MusicDaemon()`` /
    ``DaemonClient()`` and hit the module-level ``get_config()`` singleton — gets
    isolation without opting in. The singleton is dropped on entry so a prior
    test's cached ``Config`` (which may have captured the real or a stale
    directory) is never reused. ``HOME`` / ``XDG_CONFIG_HOME`` / ``LOCALAPPDATA``
    point at a session-scoped temp dir, so the path providers
    (``music_cli/platform/paths.py``) resolve ``~/.config/music-cli`` and
    ``%LOCALAPPDATA%\\music-cli`` under temp — leaving the real home untouched.

    ``start_daemon_background`` is replaced with a no-op so the suite can never
    spawn a real ``python -m music_cli.daemon`` process (F-TEST-007): the bare
    ``mc`` invocation tests reach ``ensure_daemon()``, which would otherwise fork
    a background daemon and wait ~2s per call. With the no-op, they take the
    "Failed to start daemon" path (exit 1) that those tests already accept.
    """
    # Reset the module-level singleton on every test so a previous test's Config
    # (which may have captured the real or another temp home) is never reused.
    _config_module._config = None

    monkeypatch.setenv("HOME", str(_isolated_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(_isolated_home / ".config"))
    monkeypatch.setenv("LOCALAPPDATA", str(_isolated_home / "AppData" / "Local"))
    # Clear any USERPROFILE on Windows too, in case a provider falls back to it.
    monkeypatch.delenv("USERPROFILE", raising=False)

    # Never let the suite spawn a real background daemon, and never wait on the
    # ~2s "is the daemon up yet?" retry loop in ``ensure_daemon``. Tests that
    # need a working daemon already patch ``ensure_daemon`` explicitly; this
    # only short-circuits the un-patched bare-invocation path. ``is_daemon_running``
    # -> True makes ``ensure_daemon`` skip the spawn + wait loop, after which the
    # real (temp-dir) socket connect fails fast — exit 1, which those tests
    # already accept, with no real process forked.
    import music_cli.cli.runtime as _cli_module

    monkeypatch.setattr(_cli_module, "start_daemon_background", lambda *a, **k: None)
    monkeypatch.setattr(_cli_module, "is_daemon_running", lambda *a, **k: True)
