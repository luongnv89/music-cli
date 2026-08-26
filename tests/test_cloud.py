"""Tests for `mc cloud key` — keyring-backed provider credential storage (issue #151)."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

import pytest
from click.testing import CliRunner

from music_cli.cli import main
from music_cli.cli.cloud import KEYRING_SERVICE, SUPPORTED_PROVIDERS, _load_keyring

_REPO_ROOT = Path(__file__).resolve().parents[1]


class FakeKeyring:
    """In-memory keyring backend standing in for the OS keychain."""

    def __init__(self):
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, service, username, password):
        self._store[(service, username)] = password

    def get_password(self, service, username):
        return self._store.get((service, username))

    def delete_password(self, service, username):
        if (service, username) not in self._store:
            raise KeyError(f"no entry for {(service, username)}")
        del self._store[(service, username)]


@pytest.fixture
def fake_keyring(monkeypatch):
    backend = FakeKeyring()
    monkeypatch.setattr("music_cli.cli.cloud._load_keyring", lambda: backend)
    return backend


@pytest.fixture
def runner():
    return CliRunner()


SECRET = "gmi-test-secret-value-9f2c"  # noqa: S105 - fake value, never a real credential


class TestKeySetGet:
    def test_set_then_get_round_trips(self, runner, fake_keyring):
        result = runner.invoke(main, ["cloud", "key", "set", "gmi"], input=f"{SECRET}\n")
        assert result.exit_code == 0, result.output

        result = runner.invoke(main, ["cloud", "key", "get", "gmi"])
        assert result.exit_code == 0, result.output
        assert result.output.strip() == SECRET
        assert fake_keyring.get_password(KEYRING_SERVICE, "gmi") == SECRET

    def test_set_hides_input_and_never_echoes_secret(self, runner, fake_keyring):
        result = runner.invoke(main, ["cloud", "key", "set", "gmi"], input=f"{SECRET}\n")
        assert result.exit_code == 0, result.output
        assert SECRET not in result.output

    def test_get_missing_key_fails_with_hint(self, runner, fake_keyring):
        result = runner.invoke(main, ["cloud", "key", "get", "gmi"])
        assert result.exit_code == 1
        assert "mc cloud key set gmi" in result.output


class TestKeyDeleteList:
    def test_delete_removes_entry(self, runner, fake_keyring):
        runner.invoke(main, ["cloud", "key", "set", "gmi"], input=f"{SECRET}\n")
        result = runner.invoke(
            main, ["cloud", "key", "delete", "gmi"], input="y\n"
        )
        assert result.exit_code == 0, result.output
        assert fake_keyring.get_password(KEYRING_SERVICE, "gmi") is None

    def test_delete_missing_key_fails(self, runner, fake_keyring):
        result = runner.invoke(main, ["cloud", "key", "delete", "gmi"], input="y\n")
        assert result.exit_code == 1

    def test_list_empty_then_stored(self, runner, fake_keyring):
        result = runner.invoke(main, ["cloud", "key", "list"])
        assert result.exit_code == 0
        assert "No cloud API keys stored." in result.output

        runner.invoke(main, ["cloud", "key", "set", "gmi"], input=f"{SECRET}\n")
        result = runner.invoke(main, ["cloud", "key", "list"])
        assert result.exit_code == 0
        assert "gmi" in result.output
        assert SECRET not in result.output


class TestProviderValidation:
    @pytest.mark.parametrize("subcommand", ["set", "get", "delete"])
    def test_unsupported_provider_rejected(self, runner, fake_keyring, subcommand):
        args = ["cloud", "key", subcommand, "openai"]
        result = runner.invoke(main, args, input=f"{SECRET}\ny\n")
        assert result.exit_code != 0
        assert "unsupported provider" in result.output

    def test_gmi_is_supported(self):
        assert "gmi" in SUPPORTED_PROVIDERS


class TestNoEnvLeakage:
    def test_key_is_not_exposed_to_child_processes_via_env(self, runner, fake_keyring):
        """The key lives only in the keyring — never in the process environment."""
        before_env = dict(os.environ)
        result = runner.invoke(main, ["cloud", "key", "set", "gmi"], input=f"{SECRET}\n")
        assert result.exit_code == 0, result.output

        after_env = dict(os.environ)
        assert before_env == after_env, "set must not mutate the environment"
        for name, value in after_env.items():
            assert SECRET not in value, f"secret leaked into env var {name}"


class TestGmiExtraDeclaration:
    def _pyproject(self) -> dict:
        with (_REPO_ROOT / "pyproject.toml").open("rb") as f:
            return tomllib.load(f)

    def test_gmi_extra_declares_keyring_and_httpx(self):
        extras = self._pyproject()["project"]["optional-dependencies"]
        assert "gmi" in extras, (
            "the 'gmi' extra is required by issue #151 (keyring-backed cloud keys)"
        )

        declared = {
            dep.split("[", 1)[0].split(">", 1)[0].split("=", 1)[0].split("<", 1)[0]
            .strip().lower()
            for dep in extras["gmi"]
        }
        assert {"keyring", "httpx"} <= declared, (
            f"gmi extra lost required deps: {sorted({'keyring', 'httpx'} - declared)}"
        )


class TestLazyImport:
    def test_load_keyring_raises_actionable_error_without_dependency(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def _no_keyring(name, *args, **kwargs):
            if name == "keyring":
                raise ImportError("No module named 'keyring'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_keyring)
        with pytest.raises(Exception) as excinfo:
            _load_keyring()
        assert "coder-music-cli[gmi]" in str(excinfo.value)
