"""Tests for `mc cloud` CLI — keyring secrets and the ping probe (#134).

All HTTP traffic is faked; no test in this module touches the network or the
real OS keyring.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from music_cli.cli import main
from music_cli.cli.cloud import KEYRING_SERVICE, SUPPORTED_PROVIDERS
from music_cli.cloud import secrets

SECRET = "cli-cloud-test-secret-4e7a"  # noqa: S105 - fake value, never a real credential


class FakeKeyring:
    def __init__(self):
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, service, username, password):
        self._store[(service, username)] = password

    def get_password(self, service, username):
        return self._store.get((service, username))

    def delete_password(self, service, username):
        if (service, username) not in self._store:
            raise KeyError(f"no entry for {service}/{username}")
        del self._store[(service, username)]


@pytest.fixture
def fake_keyring(monkeypatch):
    backend = FakeKeyring()
    monkeypatch.setattr("music_cli.cli.cloud._load_keyring", lambda: backend)
    return backend


@pytest.fixture
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# `mc cloud key` — keyring round trip
# ---------------------------------------------------------------------------


class TestKeyRoundTrip:
    def test_set_then_get_reads_key_back(self, runner, fake_keyring):
        result = runner.invoke(main, ["cloud", "key", "set", "gmi"], input=SECRET + "\n")
        assert result.exit_code == 0, result.output
        assert fake_keyring.get_password(KEYRING_SERVICE, "gmi") == SECRET

        got = runner.invoke(main, ["cloud", "key", "get", "gmi"])
        assert got.exit_code == 0, got.output
        assert got.output.strip() == SECRET

    def test_set_hides_input_and_never_echoes_key(self, runner, fake_keyring):
        result = runner.invoke(main, ["cloud", "key", "set", "gmi"], input=SECRET + "\n")
        assert result.exit_code == 0
        assert SECRET not in result.output

    def test_get_missing_key_fails_without_leaking(self, runner, fake_keyring):
        result = runner.invoke(main, ["cloud", "key", "get", "gmi"])
        assert result.exit_code == 1
        assert SECRET not in result.output
        assert "No API key stored" in result.output

    def test_list_shows_providers_never_values(self, runner, fake_keyring):
        fake_keyring.set_password(KEYRING_SERVICE, "gmi", SECRET)
        result = runner.invoke(main, ["cloud", "key", "list"])
        assert result.exit_code == 0
        assert "gmi" in result.output
        assert SECRET not in result.output

    def test_delete_removes_key(self, runner, fake_keyring):
        fake_keyring.set_password(KEYRING_SERVICE, "gmi", SECRET)
        result = runner.invoke(main, ["cloud", "key", "delete", "gmi"], input="y\n")
        assert result.exit_code == 0
        assert fake_keyring.get_password(KEYRING_SERVICE, "gmi") is None

    def test_unsupported_provider_rejected(self, runner, fake_keyring):
        result = runner.invoke(main, ["cloud", "key", "get", "anthropic"])
        assert result.exit_code != 0
        assert "unsupported provider" in result.output

# ---------------------------------------------------------------------------
# `mc cloud ping`
# ---------------------------------------------------------------------------


class FakeAdapter:
    def __init__(self, *, ok=True, error=None):
        self.ok = ok
        self.error = error
        self.calls: list[dict] = []
        self.closed = False
        self.api_key: str | None = None

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        if not self.ok:
            raise RuntimeError(self.error or "boom")
        return {"text": "pong"}

    async def aclose(self):
        self.closed = True


@pytest.fixture
def patch_adapter(monkeypatch):
    """Patch the adapter factory; call with a {provider: FakeAdapter} map."""

    def _install(adapters):
        def factory(provider, api_key):
            adapter = adapters[provider]
            adapter.api_key = api_key
            return adapter

        monkeypatch.setattr("music_cli.cli.cloud._build_adapter", factory)
        return adapters

    return _install


class TestCloudPing:
    def test_reachable_reports_latency_and_exits_zero(
        self, runner, fake_keyring, patch_adapter
    ):
        fake_keyring.set_password(KEYRING_SERVICE, "gmi", SECRET)
        patch_adapter({"gmi": FakeAdapter(ok=True)})
        result = runner.invoke(main, ["cloud", "ping", "gmi"])
        assert result.exit_code == 0, result.output
        assert "gmi: reachable" in result.output

    def test_probe_uses_trivial_request(self, runner, fake_keyring, patch_adapter):
        fake_keyring.set_password(KEYRING_SERVICE, "gmi", SECRET)
        adapter = FakeAdapter(ok=True)
        patch_adapter({"gmi": adapter})
        result = runner.invoke(main, ["cloud", "ping", "gmi"])
        assert result.exit_code == 0
        assert len(adapter.calls) == 1
        assert adapter.calls[0]["prompt"] == "ping"
        assert adapter.closed

    def test_adapter_receives_stored_key_but_output_never_shows_it(
        self, runner, fake_keyring, patch_adapter
    ):
        fake_keyring.set_password(KEYRING_SERVICE, "gmi", SECRET)
        adapter = FakeAdapter(ok=True)
        patch_adapter({"gmi": adapter})
        result = runner.invoke(main, ["cloud", "ping", "gmi"])
        assert result.exit_code == 0
        assert adapter.api_key == SECRET
        assert SECRET not in result.output

    def test_unreachable_reports_error_and_exits_nonzero(
        self, runner, fake_keyring, patch_adapter
    ):
        fake_keyring.set_password(KEYRING_SERVICE, "gmi", SECRET)
        patch_adapter({"gmi": FakeAdapter(ok=False, error="HTTP 503")})
        result = runner.invoke(main, ["cloud", "ping", "gmi"])
        assert result.exit_code == 1
        assert "gmi: unreachable" in result.output
        assert SECRET not in result.output

    def test_missing_key_reports_unreachable_without_network(
        self, runner, fake_keyring
    ):
        result = runner.invoke(main, ["cloud", "ping", "gmi"])
        assert result.exit_code == 1
        assert "unreachable" in result.output
        assert "no API key stored" in result.output

    def test_no_argument_probes_every_provider(self, runner, fake_keyring, patch_adapter):
        for name in SUPPORTED_PROVIDERS:
            fake_keyring.set_password(KEYRING_SERVICE, name, SECRET)
        adapters = {name: FakeAdapter(ok=True) for name in SUPPORTED_PROVIDERS}
        patch_adapter(adapters)
        result = runner.invoke(main, ["cloud", "ping"])
        assert result.exit_code == 0, result.output
        for name in SUPPORTED_PROVIDERS:
            assert f"{name}: reachable" in result.output

    def test_unsupported_provider_rejected(self, runner, fake_keyring):
        result = runner.invoke(main, ["cloud", "ping", "nope"])
        assert result.exit_code != 0
        assert "unsupported provider" in result.output


# ---------------------------------------------------------------------------
# `mc cloud --help`
# ---------------------------------------------------------------------------


class TestCloudHelp:
    def test_help_lists_subcommands_and_examples(self, runner):
        result = runner.invoke(main, ["cloud", "--help"])
        assert result.exit_code == 0
        for token in ("key", "ping", "smoke", "Examples:", "mc cloud key set gmi"):
            assert token in result.output


# ---------------------------------------------------------------------------
# music_cli.cloud.secrets wrapper
# ---------------------------------------------------------------------------


class TestSecretsModule:
    def test_store_get_delete_round_trip(self):
        backend = FakeKeyring()
        assert secrets.get_api_key("gmi", keyring_module=backend) is None
        secrets.store_api_key("gmi", SECRET, keyring_module=backend)
        assert secrets.get_api_key("gmi", keyring_module=backend) == SECRET
        secrets.delete_api_key("gmi", keyring_module=backend)
        assert secrets.get_api_key("gmi", keyring_module=backend) is None

    def test_stored_providers_lists_only_stored(self):
        backend = FakeKeyring()
        secrets.store_api_key("openrouter", SECRET, keyring_module=backend)
        assert secrets.stored_providers(keyring_module=backend) == ["openrouter"]
        assert secrets.stored_providers(keyring_module=backend, providers=("gmi",)) == []

    def test_service_matches_cli_alias(self):
        assert KEYRING_SERVICE == secrets.SERVICE

    def test_missing_keyring_raises_unavailable(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name == "keyring":
                raise ImportError("No module named 'keyring'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", blocked)
        with pytest.raises(secrets.KeyringUnavailable):
            secrets.load_keyring()
