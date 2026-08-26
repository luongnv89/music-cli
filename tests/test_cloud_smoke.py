"""Tests for `mc cloud smoke` — one real call per free MiniMax model (#152).

All HTTP traffic is faked; no test in this module touches the network.
"""

from __future__ import annotations

import json
import sys
import types

import pytest
from click.testing import CliRunner

from music_cli.cli import main
from music_cli.cli.cloud import KEYRING_SERVICE
from music_cli.cli.cloud_smoke import (
    DEFAULT_M3_MODEL,
    GMI_QUEUE_URL,
    GMI_SERVING_CHAT_URL,
    MUSIC_MODEL,
    SPEECH_MODEL,
    run_all_checks,
)

SECRET = "gmi-test-secret-value-9f2c"  # noqa: S105 - fake value, never a real credential


class FakeKeyring:
    def __init__(self):
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, service, username, password):
        self._store[(service, username)] = password

    def get_password(self, service, username):
        return self._store.get((service, username))


@pytest.fixture
def fake_keyring(monkeypatch):
    backend = FakeKeyring()
    monkeypatch.setattr("music_cli.cli.cloud._load_keyring", lambda: backend)
    return backend


@pytest.fixture
def runner():
    return CliRunner()


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, content=b""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.content = content

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    """Scripted httpx client: pops queued responses per (method, url substring)."""

    def __init__(self, script):
        # script: list of (method, url_substring, response-or-exception)
        self.script = list(script)
        self.calls: list[tuple[str, str]] = []

    def request(self, method, url, **kwargs):
        for i, (want_method, substring, item) in enumerate(self.script):
            if want_method == method and substring in url:
                del self.script[i]
                self.calls.append((method, url))
                if isinstance(item, Exception):
                    raise item
                return item
        raise AssertionError(f"unexpected {method} {url}")

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)


class FakeHttpx(types.ModuleType):
    """Stand-in for the httpx module whose Client yields scripted clients."""

    def __init__(self, script):
        super().__init__("httpx")
        self._script = script
        self.clients: list[FakeClient] = []

    def Client(self, **kwargs):  # noqa: N802 - mirrors the httpx API name
        client = FakeClient(self._script)
        self.clients.append(client)
        return client


@pytest.fixture
def fake_httpx(monkeypatch):
    holder: dict[str, FakeHttpx] = {}

    def install(script):
        module = FakeHttpx(script)
        monkeypatch.setitem(sys.modules, "httpx", module)
        holder["module"] = module
        return module

    holder["install"] = install
    yield holder


def _m3_ok():
    return FakeResponse(
        json_data={"choices": [{"message": {"content": "smoke ok"}}]},
    )


def _queue_success(audio_url="https://storage.googleapis.com/bucket/out.mp3"):
    return FakeResponse(
        json_data={
            "request_id": "req-1",
            "status": "success",
            "outcome": {"audio_url": audio_url, "media_urls": [{"url": audio_url}]},
        },
    )


AUDIO_BYTES = b"ID3faketunedata"


class TestMissingPrerequisites:
    def test_no_key_fails_with_hint(self, runner, fake_keyring):
        result = runner.invoke(main, ["cloud", "smoke"])
        assert result.exit_code == 1
        assert "mc cloud key set gmi" in result.output

    def test_missing_httpx_gives_install_hint(self, runner, fake_keyring, monkeypatch):
        fake_keyring.set_password(KEYRING_SERVICE, "gmi", SECRET)
        import builtins

        original = builtins.__import__

        def _no_httpx(name, *args, **kwargs):
            if name == "httpx":
                raise ImportError("No module named 'httpx'")
            return original(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_httpx)
        result = runner.invoke(main, ["cloud", "smoke"])
        assert result.exit_code != 0
        assert "coder-music-cli[gmi]" in result.output


class TestHappyPath:
    def test_all_three_checks_pass_and_write_files(
        self, runner, fake_keyring, fake_httpx, tmp_path
    ):
        fake_keyring.set_password(KEYRING_SERVICE, "gmi", SECRET)
        install = fake_httpx["install"]
        # One shared script consumed in order across the three clients.
        install(
            [
                ("POST", "/v1/chat/completions", _m3_ok()),
                (
                    "POST",
                    "requestqueue/apikey/requests",
                    FakeResponse(json_data={"request_id": "m-1"}),
                ),
                ("GET", "requests/m-1", _queue_success("https://storage.googleapis.com/music.mp3")),
                ("GET", "storage.googleapis.com/music.mp3", FakeResponse(content=AUDIO_BYTES)),
                (
                    "POST",
                    "requestqueue/apikey/requests",
                    FakeResponse(json_data={"request_id": "s-1"}),
                ),
                (
                    "GET",
                    "requests/s-1",
                    _queue_success("https://storage.googleapis.com/speech.mp3"),
                ),
                ("GET", "storage.googleapis.com/speech.mp3", FakeResponse(content=AUDIO_BYTES)),
            ]
        )

        outdir = tmp_path / "_smoke"
        result = runner.invoke(main, ["cloud", "smoke", "--output-dir", str(outdir)])
        assert result.exit_code == 0, result.output

        m3_text = (outdir / "m3_response.txt").read_text(encoding="utf-8")
        assert m3_text == "smoke ok"
        assert (outdir / "music.mp3").read_bytes() == AUDIO_BYTES
        assert (outdir / "speech.mp3").read_bytes() == AUDIO_BYTES

        summary = json.loads((outdir / "summary.json").read_text(encoding="utf-8"))
        by_check = {r["check"]: r for r in summary["results"]}
        assert set(by_check) == {"m3", "music", "speech"}
        for record in by_check.values():
            assert record["status"] == "ok"
            assert record["timestamp"]
            assert isinstance(record["latency_s"], float)
            assert record["size_bytes"] > 0
            assert record["format"] in ("text", "mp3")

        assert by_check["m3"]["model"] == DEFAULT_M3_MODEL
        assert by_check["music"]["model"] == MUSIC_MODEL
        assert by_check["speech"]["model"] == SPEECH_MODEL

    def test_requests_hit_documented_endpoints(self, runner, fake_keyring, fake_httpx, tmp_path):
        fake_keyring.set_password(KEYRING_SERVICE, "gmi", SECRET)
        module = fake_httpx["install"](
            [
                ("POST", "/v1/chat/completions", _m3_ok()),
                (
                    "POST",
                    "requestqueue/apikey/requests",
                    FakeResponse(json_data={"request_id": "m-1"}),
                ),
                ("GET", "requests/m-1", _queue_success()),
                ("GET", "storage.googleapis.com", FakeResponse(content=AUDIO_BYTES)),
                (
                    "POST",
                    "requestqueue/apikey/requests",
                    FakeResponse(json_data={"request_id": "s-1"}),
                ),
                ("GET", "requests/s-1", _queue_success()),
                ("GET", "storage.googleapis.com", FakeResponse(content=AUDIO_BYTES)),
            ]
        )
        result = runner.invoke(main, ["cloud", "smoke", "--output-dir", str(tmp_path / "s")])
        assert result.exit_code == 0, result.output

        urls = [url for client in module.clients for _, url in client.calls]
        assert any(GMI_SERVING_CHAT_URL in u for u in urls)
        assert any(GMI_QUEUE_URL in u for u in urls)


class TestPollingAndFailures:
    def test_music_polls_until_success(
        self, runner, fake_keyring, fake_httpx, tmp_path, monkeypatch
    ):
        fake_keyring.set_password(KEYRING_SERVICE, "gmi", SECRET)
        monkeypatch.setattr("music_cli.cli.cloud_smoke.time.sleep", lambda _s: None)
        fake_httpx["install"](
            [
                ("POST", "/v1/chat/completions", _m3_ok()),
                (
                    "POST",
                    "requestqueue/apikey/requests",
                    FakeResponse(json_data={"request_id": "p-1"}),
                ),
                ("GET", "requests/p-1", FakeResponse(json_data={"status": "queued"})),
                ("GET", "requests/p-1", FakeResponse(json_data={"status": "running"})),
                ("GET", "requests/p-1", _queue_success()),
                ("GET", "storage.googleapis.com", FakeResponse(content=AUDIO_BYTES)),
                (
                    "POST",
                    "requestqueue/apikey/requests",
                    FakeResponse(json_data={"request_id": "s-9"}),
                ),
                ("GET", "requests/s-9", _queue_success()),
                ("GET", "storage.googleapis.com", FakeResponse(content=AUDIO_BYTES)),
            ]
        )
        result = runner.invoke(
            main,
            [
                "cloud",
                "smoke",
                "--output-dir",
                str(tmp_path / "o"),
                "--poll-interval",
                "0",
            ],
        )
        assert result.exit_code == 0, result.output
        summary = json.loads((tmp_path / "o" / "summary.json").read_text())
        assert [r["status"] for r in summary["results"]] == ["ok", "ok", "ok"]

    def test_failed_job_records_error_and_exits_nonzero(
        self, runner, fake_keyring, fake_httpx, tmp_path
    ):
        fake_keyring.set_password(KEYRING_SERVICE, "gmi", SECRET)
        fake_httpx["install"](
            [
                ("POST", "/v1/chat/completions", _m3_ok()),
                (
                    "POST",
                    "requestqueue/apikey/requests",
                    FakeResponse(json_data={"request_id": "f-1"}),
                ),
                ("GET", "requests/f-1", FakeResponse(json_data={"status": "failed"})),
            ]
        )
        outdir = tmp_path / "f"
        result = runner.invoke(main, ["cloud", "smoke", "--output-dir", str(outdir)])
        assert result.exit_code == 1
        summary = json.loads((outdir / "summary.json").read_text())
        failed = [r for r in summary["results"] if r["check"] == "music"][0]
        assert failed["status"] == "error"
        assert failed["error"]

    def test_m3_timeout_is_recorded_not_raised(self, runner, fake_keyring, tmp_path):
        def boom(*args, **kwargs):
            raise TimeoutError("timed out")

        client = FakeClient([])
        client.post = boom
        from music_cli.cli.cloud_smoke import run_m3

        record = run_m3(client, SECRET, timeout=30.0)
        assert record["status"] == "error"
        assert "timed out" in record["error"]

    def test_run_all_checks_never_raises_on_client_errors(self, fake_keyring, tmp_path):
        class ExplodingClient(FakeClient):
            def post(self, url, **kwargs):
                raise RuntimeError("connection refused")

            def get(self, url, **kwargs):
                raise RuntimeError("connection refused")

        results = run_all_checks(lambda: ExplodingClient([]), SECRET, output_dir=tmp_path / "x")
        assert [r["status"] for r in results] == ["error", "error", "error"]


class TestSkips:
    def test_skip_flag_leaves_only_requested_checks(
        self, runner, fake_keyring, fake_httpx, tmp_path
    ):
        fake_keyring.set_password(KEYRING_SERVICE, "gmi", SECRET)
        fake_httpx["install"]([("POST", "/v1/chat/completions", _m3_ok())])
        outdir = tmp_path / "sk"
        result = runner.invoke(
            main,
            ["cloud", "smoke", "--output-dir", str(outdir), "--skip", "music", "--skip", "speech"],
        )
        assert result.exit_code == 0, result.output
        summary = json.loads((outdir / "summary.json").read_text())
        statuses = {r["check"]: r["status"] for r in summary["results"]}
        assert statuses == {
            "m3": "ok",
            "music": "skipped",
            "speech": "skipped",
        }
