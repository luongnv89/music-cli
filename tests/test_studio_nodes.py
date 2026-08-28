"""Tests for music_cli.studio.nodes — P3.1 (issue #137).

A scripted fake adapter replays recorded Music 3.0 / Speech 2.8 outcomes
(audio URLs only, matching the ``gmi_recorded.json`` fixture shapes) while an
injectable downloader writes the audio bytes and an injectable probe confirms
duration. No network and no bare ``ffprobe`` is needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from music_cli.studio import MusicNode, NodeError, NodeLockedError, SpeechNode
from music_cli.studio.nodes.base import NodeProtocol
from music_cli.studio.nodes.music import _audio_url
from music_cli.studio.trace import NODES_DIRNAME

# ---------------------------------------------------------------------------
# recorded-fixture shapes (mirror tests/fixtures/gmi_recorded.json outcomes)
# ---------------------------------------------------------------------------

MUSIC_FIXTURES: list[dict[str, Any]] = [
    {
        "status": "completed",
        "audio_url": "https://cdn.gmicloud.ai/recorded/music-rec-001.mp3",
        "duration_s": 96,
    },
    {
        "status": "completed",
        "audio_url": "https://cdn.gmicloud.ai/recorded/music-rec-002.mp3",
        "duration_s": 45,
    },
]

SPEECH_FIXTURES: list[dict[str, Any]] = [
    {
        "status": "completed",
        "media_urls": [
            {
                "url": "https://cdn.gmicloud.ai/recorded/speech-rec-001.mp3",
                "format": "mp3",
            }
        ],
    },
    {
        "status": "completed",
        "audio_url": "https://cdn.gmicloud.ai/recorded/speech-rec-002.mp3",
    },
]


class FakeAdapter:
    """Replays recorded audio outcomes from the two async adapter methods."""

    def __init__(self, music: list, speech: list) -> None:
        self.music = list(music)
        self.speech = list(speech)
        self.music_prompts: list[tuple[str, dict]] = []
        self.speech_calls: list[tuple[str, dict]] = []

    async def music3_generate(self, prompt: str, **params: Any) -> dict[str, Any]:
        self.music_prompts.append((prompt, params))
        return self.music.pop(0)

    async def speech28_synthesize(self, text: str, **params: Any) -> dict[str, Any]:
        self.speech_calls.append((text, params))
        return self.speech.pop(0)


def _fake_probe(path: Path) -> dict[str, Any]:
    return {"path": path, "duration_seconds": 60.0, "ok": path.exists()}


async def _fake_download(_url: str, dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"\x00" * 32)
    return 32


# ---------------------------------------------------------------------------
# Node protocol surface
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_protocol_names_expose_lifecycle_surface(self):
        for member in ("generate", "probe", "lock", "unlock", "path"):
            assert hasattr(NodeProtocol, member), f"protocol missing {member}"

    def test_music_and_speech_satisfy_protocol(self, tmp_path):
        adapter = FakeAdapter(MUSIC_FIXTURES, SPEECH_FIXTURES)
        for node in (
            MusicNode(adapter, proj_dir=tmp_path, downloader=_fake_download, probe=_fake_probe),
            SpeechNode(adapter, proj_dir=tmp_path, downloader=_fake_download, probe=_fake_probe),
        ):
            assert isinstance(node, NodeProtocol)


# ===========================================================================
# MusicNode
# ===========================================================================


class TestMusicNode:
    async def test_generate_calls_music3_and_writes_song_wav(self, tmp_path):
        adapter = FakeAdapter(MUSIC_FIXTURES, [])
        node = MusicNode(adapter, proj_dir=tmp_path, downloader=_fake_download, probe=_fake_probe)
        out = await node.generate("lo-fi focus beats", lyrics="la la", duration=90)
        assert out.name == "song-1.wav"
        assert out.parent.name == NODES_DIRNAME
        assert out.parent.parent == tmp_path
        assert node.path == out
        prompt, params = adapter.music_prompts[0]
        assert prompt == "lo-fi focus beats"
        assert params["lyrics"] == "la la"
        assert params["duration"] == 90

    async def test_second_generate_increments_song_index(self, tmp_path):
        adapter = FakeAdapter(MUSIC_FIXTURES, [])
        node = MusicNode(adapter, proj_dir=tmp_path, downloader=_fake_download, probe=_fake_probe)
        first = await node.generate("one")
        node.unlock()
        second = await node.generate("two")
        assert first.name == "song-1.wav"
        assert second.name == "song-2.wav"

    async def test_locked_node_refuses_to_regenerate(self, tmp_path):
        adapter = FakeAdapter(MUSIC_FIXTURES, [])
        node = MusicNode(adapter, proj_dir=tmp_path, downloader=_fake_download, probe=_fake_probe)
        out = await node.generate("first")
        assert node.path == out
        with pytest.raises(NodeLockedError):
            await node.generate("second")
        # explicit unlock allows regeneration
        node.unlock()
        out2 = await node.generate("second")
        assert out2.name == "song-2.wav"

    async def test_probe_failure_unlinks_output_and_does_not_lock(self, tmp_path):
        adapter = FakeAdapter(MUSIC_FIXTURES, [])

        def bad_probe(path):
            return {"path": path, "ok": False, "duration_seconds": None}

        node = MusicNode(adapter, proj_dir=tmp_path, downloader=_fake_download, probe=bad_probe)
        with pytest.raises(NodeError, match="probe failed"):
            await node.generate("bad")
        nodes_dir = tmp_path / NODES_DIRNAME
        assert not list(nodes_dir.glob("*.wav"))
        assert not list(nodes_dir.iterdir())
        node.unlock()  # still unlocked after failed probe

    async def test_lock_then_unlock_then_generate_again(self, tmp_path):
        adapter = FakeAdapter(MUSIC_FIXTURES, [])
        node = MusicNode(adapter, proj_dir=tmp_path, downloader=_fake_download, probe=_fake_probe)
        await node.generate("a")
        node.lock()
        with pytest.raises(NodeLockedError):
            await node.generate("b")

    def test_audio_url_from_media_urls(self):
        result = {
            "status": "completed",
            "media_urls": [{"url": "https://x/rec.mp3", "format": "mp3"}],
        }
        assert _audio_url(result) == "https://x/rec.mp3"
        with pytest.raises(ValueError):
            _audio_url({"status": "completed"})


# ===========================================================================
# SpeechNode
# ===========================================================================


class TestSpeechNode:
    async def test_generate_calls_speech_and_writes_narration_wav(self, tmp_path):
        adapter = FakeAdapter([], SPEECH_FIXTURES)
        node = SpeechNode(adapter, proj_dir=tmp_path, downloader=_fake_download, probe=_fake_probe)
        out = await node.generate("A cold night", voice="alto")
        assert out.name == "narration-1.wav"
        assert out.parent.name == NODES_DIRNAME
        assert node.path == out
        text, params = adapter.speech_calls[0]
        assert text == "A cold night"
        assert params["voice"] == "alto"

    async def test_locked_speech_refuses_regenerate(self, tmp_path):
        adapter = FakeAdapter([], SPEECH_FIXTURES)
        node = SpeechNode(adapter, proj_dir=tmp_path, downloader=_fake_download, probe=_fake_probe)
        await node.generate("first")
        with pytest.raises(NodeLockedError):
            await node.generate("second")
        node.unlock()
        out2 = await node.generate("second")
        assert out2.name == "narration-2.wav"

    async def test_speech_increments_index_across_generates(self, tmp_path):
        adapter = FakeAdapter([], SPEECH_FIXTURES)
        node = SpeechNode(adapter, proj_dir=tmp_path, downloader=_fake_download, probe=_fake_probe)
        await node.generate("a")
        node.unlock()
        await node.generate("b")
        files = sorted(p.name for p in (tmp_path / NODES_DIRNAME).iterdir())
        assert files == ["narration-1.wav", "narration-2.wav"]
