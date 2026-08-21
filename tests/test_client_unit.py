"""DaemonClient unit tests (issue #72 — coverage raise).

The IPC transport is replaced with a scripted fake socket so request framing,
timeout selection, and response handling are verified without a real daemon
or platform sockets (keeps the suite Windows-safe).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import music_cli.client as client_module
from music_cli.client import (
    AI_TIMEOUT,
    DEFAULT_TIMEOUT,
    YOUTUBE_TIMEOUT,
    DaemonClient,
    get_client,
)


@pytest.fixture()
def ipc(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """A fake IPC client whose connect() returns a scripted socket."""
    fake_ipc = MagicMock()
    monkeypatch.setattr(client_module, "get_ipc_client", lambda: fake_ipc)
    return fake_ipc


@pytest.fixture()
def client(ipc: MagicMock) -> DaemonClient:
    return DaemonClient()


def make_socket(payload: bytes | list[bytes]) -> MagicMock:
    """A fake socket that streams the payload then returns b"" forever."""
    sock = MagicMock()
    chunks = [payload] if isinstance(payload, bytes) else payload
    stream = iter(chunks)
    sock.recv.side_effect = lambda *a: next(stream, b"")
    return sock


class TestTimeoutSelection:
    @pytest.mark.parametrize(
        ("command", "args", "expected"),
        [
            ("play", {"mode": "ai"}, AI_TIMEOUT),
            ("play", {"mode": "youtube"}, YOUTUBE_TIMEOUT),
            ("play", {"mode": "yt"}, YOUTUBE_TIMEOUT),
            ("ai_play", {}, AI_TIMEOUT),
            ("status", {}, DEFAULT_TIMEOUT),
        ],
    )
    def test_derived_timeouts(
        self,
        ipc: MagicMock,
        command: str,
        args: dict,
        expected: float,
    ) -> None:
        sock = make_socket(b'{"status": "ok"}')
        ipc.connect.return_value = sock
        DaemonClient().send_command(command, args)
        assert ipc.connect.call_args[0][1] == expected

    def test_explicit_timeout_wins(self, ipc: MagicMock) -> None:
        ipc.connect.return_value = make_socket(b"{}")
        DaemonClient().send_command("play", timeout=1.5)
        assert ipc.connect.call_args[0][1] == 1.5


class TestRequestFraming:
    def test_request_includes_command_args_and_token(
        self, ipc: MagicMock, client: DaemonClient, monkeypatch
    ) -> None:
        monkeypatch.setattr(client.config, "read_auth_token", lambda: "secret-token")
        ipc.connect.return_value = make_socket(b"{}")
        client.send_command("volume", {"level": 42})
        sent = ipc.connect.return_value.sendall.call_args[0][0]
        import json

        request = json.loads(sent.decode())
        assert request == {
            "command": "volume",
            "args": {"level": 42},
            "token": "secret-token",
        }

    def test_none_args_become_empty_dict(self, ipc: MagicMock) -> None:
        ipc.connect.return_value = make_socket(b"{}")
        DaemonClient().send_command("stop")
        import json

        request = json.loads(ipc.connect.return_value.sendall.call_args[0][0].decode())
        assert request["args"] == {}


class TestResponseHandling:
    def test_multi_chunk_response_is_reassembled(self, ipc: MagicMock) -> None:
        ipc.connect.return_value = make_socket([b'{"stat', b'us": "ok"}'])
        response = DaemonClient().send_command("status")
        assert response == {"status": "ok"}

    def test_oversized_response_is_rejected(self, ipc: MagicMock, monkeypatch, caplog) -> None:
        monkeypatch.setattr(client_module, "MAX_RESPONSE_SIZE", 4)
        big = b"12345"
        sock = MagicMock()
        sock.recv.side_effect = [big]
        ipc.connect.return_value = sock
        response = DaemonClient().send_command("status")
        assert response == {"error": "Response too large from daemon"}

    def test_empty_response_reports_error(self, ipc: MagicMock) -> None:
        ipc.connect.return_value = make_socket([])
        assert DaemonClient().send_command("ping") == {"error": "Empty response from daemon"}

    def test_invalid_json_reports_error(self, ipc: MagicMock) -> None:
        ipc.connect.return_value = make_socket(b"{not json")
        assert DaemonClient().send_command("ping") == {"error": "Invalid response from daemon"}

    def test_socket_closed_even_on_protocol_errors(self, ipc: MagicMock) -> None:
        sock = make_socket(b"{broken")
        ipc.connect.return_value = sock
        DaemonClient().send_command("ping")
        sock.close.assert_called_once()


class TestPing:
    def test_ping_ok(self, ipc: MagicMock) -> None:
        ipc.connect.return_value = make_socket(b'{"status": "ok"}')
        assert DaemonClient().ping() is True

    def test_ping_connection_error(self, ipc: MagicMock) -> None:
        ipc.connect.side_effect = ConnectionError("no daemon")
        assert DaemonClient().ping() is False


class TestConvenienceWrappers:
    def test_play_builds_full_args(self, ipc: MagicMock, client: DaemonClient) -> None:
        ipc.connect.return_value = make_socket(b"{}")
        with patch.object(client, "send_command", wraps=client.send_command):
            client.play(
                mode="history",
                source="src",
                mood="focus",
                auto=True,
                duration=60,
                index=3,
            )
            sent = ipc.connect.return_value.sendall.call_args[0][0]
        import json

        args = json.loads(sent.decode())["args"]
        assert args == {
            "mode": "history",
            "auto": True,
            "source": "src",
            "mood": "focus",
            "duration": 60,
            "index": 3,
        }

    def test_simple_wrappers_send_expected_commands(
        self, ipc: MagicMock, client: DaemonClient
    ) -> None:
        ipc.connect.return_value = make_socket(b"{}")
        import json

        def last_request() -> dict:
            return json.loads(ipc.connect.return_value.sendall.call_args[0][0].decode())

        client.stop()
        assert last_request()["command"] == "stop"
        client.pause()
        assert last_request()["command"] == "pause"
        client.resume()
        assert last_request()["command"] == "resume"
        client.status()
        assert last_request()["command"] == "status"
        client.next_track()
        assert last_request()["command"] == "next"

    def test_volume_get_and_set(self, ipc: MagicMock) -> None:
        ipc.connect.return_value = make_socket(b'{"volume": 55}')
        client = DaemonClient()
        assert client.get_volume() == 55

        ipc.connect.return_value = make_socket(b"{}")
        client.set_volume(30)
        import json

        assert json.loads(ipc.connect.return_value.sendall.call_args[0][0].decode())["args"] == {
            "level": 30
        }

    def test_get_volume_defaults_to_80_when_missing(self, ipc: MagicMock) -> None:
        ipc.connect.return_value = make_socket(b"{}")
        assert DaemonClient().get_volume() == 80

    def test_list_endpoints_unwrap_payloads(self, ipc: MagicMock) -> None:
        ipc.connect.return_value = make_socket(b'{"stations": [{"name": "jazz"}]}')
        assert DaemonClient().list_radios() == [{"name": "jazz"}]

        ipc.connect.return_value = make_socket(b'{"history": [{"t": 1}]}')
        assert DaemonClient().list_history(limit=5) == [{"t": 1}]

        ipc.connect.return_value = make_socket(b'{"tracks": [{"id": 1}]}')
        assert DaemonClient().ai_list() == [{"id": 1}]

    def test_ai_play_builds_optional_args(self, ipc: MagicMock, client: DaemonClient) -> None:
        ipc.connect.return_value = make_socket(b"{}")
        import json

        client.ai_play(
            prompt="lofi beats",
            duration=15,
            mood="focus",
            model="musicgen-small",
            lyrics="la la",
        )
        request = json.loads(ipc.connect.return_value.sendall.call_args[0][0].decode())
        assert request["command"] == "ai_play"
        assert request["args"] == {
            "duration": 15,
            "prompt": "lofi beats",
            "mood": "focus",
            "model": "musicgen-small",
            "lyrics": "la la",
        }
        assert ipc.connect.call_args[0][1] == AI_TIMEOUT

    def test_ai_replay_timeout_depends_on_regenerate(self, ipc: MagicMock) -> None:
        ipc.connect.return_value = make_socket(b"{}")
        client = DaemonClient()

        client.ai_replay(2)
        assert ipc.connect.call_args[0][1] == DEFAULT_TIMEOUT

        client.ai_replay(2, regenerate=True)
        assert ipc.connect.call_args[0][1] == AI_TIMEOUT

    def test_youtube_history_wrappers(self, ipc: MagicMock) -> None:
        ipc.connect.return_value = make_socket(b"{}")

        client = DaemonClient()
        client.youtube_cached()
        assert last_command(ipc) == "youtube_history_list"
        client.youtube_play(1)
        assert last_command(ipc) == "youtube_history_play"
        client.youtube_remove(2)
        assert last_command(ipc) == "youtube_history_remove"
        client.youtube_clear()
        assert last_command(ipc) == "youtube_history_clear"


def last_command(ipc: MagicMock) -> str:
    import json

    return json.loads(ipc.connect.return_value.sendall.call_args[0][0].decode())["command"]


class TestFactory:
    def test_get_client_returns_daemon_client(self) -> None:
        assert isinstance(get_client(), DaemonClient)
