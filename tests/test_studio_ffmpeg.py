"""Tests for music_cli.studio.nodes.ffmpeg — P3.2 (issue #138).

Covers the SRT writer (``_srt_timestamp``/``write_srt``), ffmpeg/ffprobe
resolution via :func:`shutil.which`, the deterministic ``MixNode._build_command``
graph (no subprocess), ``MixNode.run`` with a mocked ffmpeg, and — when a real
ffmpeg is on PATH — one end-to-end smoke mix producing a valid WAV + SRT.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from music_cli.studio import nodes as nodes_pkg
from music_cli.studio.nodes.ffmpeg import (
    DEFAULT_FFMPEG,
    DEFAULT_SAMPLE_RATE,
    DUCK_ATTACK_MS,
    DUCK_RATIO,
    DUCK_RELEASE_MS,
    DUCK_THRESHOLD,
    MixNode,
    MixNodeError,
    _srt_timestamp,
    resolve_binary,
    write_srt,
)

HAS_FFMPEG = shutil.which("ffmpeg") is not None
HAS_FFPROBE = shutil.which("ffprobe") is not None


def _tone(path: Path, freq: float = 440.0, duration: float = 5.0) -> Path:
    """Generate a real WAV sine tone with the system ffmpeg (smoke only)."""
    ffmpeg_bin = shutil.which("ffmpeg")
    subprocess.run(
        [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={freq}:duration={duration}",
            str(path),
        ],
        check=True,
    )
    return path


# ---------------------------------------------------------------------------
# package surface
# ---------------------------------------------------------------------------


class TestPackageExports:
    def test_nodes_pkg_reexports_mixnode(self):
        assert nodes_pkg.MixNode is MixNode
        assert nodes_pkg.write_srt is write_srt
        assert nodes_pkg.resolve_binary is resolve_binary
        assert nodes_pkg.MixNodeError is MixNodeError

    def test_studio_pkg_reexports_mixnode(self):
        import music_cli.studio as studio_pkg

        assert studio_pkg.MixNode is MixNode
        assert studio_pkg.MixNodeError is MixNodeError
        assert studio_pkg.write_srt is write_srt
        assert studio_pkg.resolve_binary is resolve_binary


# ---------------------------------------------------------------------------
# _srt_timestamp
# ---------------------------------------------------------------------------


class TestSrtTimestamp:
    def test_basic_round_trip(self):
        assert _srt_timestamp(0.0) == "00:00:00,000"
        assert _srt_timestamp(1.23456) == "00:00:01,235"
        assert _srt_timestamp(2.0) == "00:00:02,000"

    def test_hour_rollover(self):
        assert _srt_timestamp(3661.75) == "01:01:01,750"

    def test_negative_clamps_to_zero(self):
        assert _srt_timestamp(-3.5) == "00:00:00,000"

    def test_millisecond_carry(self):
        # 0.9995 rounds up to 1000ms -> 00:00:01,000
        assert _srt_timestamp(0.9995) == "00:00:01,000"


# ---------------------------------------------------------------------------
# write_srt
# ---------------------------------------------------------------------------


class TestWriteSrt:
    def test_writes_indexed_blocks(self, tmp_path):
        out = write_srt(
            [(1.0, 2.0, "Hi there"), (3.0, 4.5, "World")],
            tmp_path / "nodes" / "captions.srt",
        )
        text = out.read_text(encoding="utf-8")
        expected = (
            "1\n00:00:01,000 --> 00:00:02,000\nHi there\n\n"
            "2\n00:00:03,000 --> 00:00:04,500\nWorld\n"
        )
        assert text == expected

    def test_empty_captions_writes_empty_file(self, tmp_path):
        out = write_srt([], tmp_path / "captions.srt")
        assert out.read_text(encoding="utf-8") == ""

    def test_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "deep" / "nested" / "captions.srt"
        write_srt([(0.0, 1.0, "ok")], out)
        assert out.exists()
        assert "ok" in out.read_text(encoding="utf-8")

    def test_extra_trailing_fields_ignored(self, tmp_path):
        # 4-tuple carries a narration path; only the first three are written.
        out = write_srt([(0.0, 1.0, "txt", "narration-1.wav")], tmp_path / "captions.srt")
        text = out.read_text(encoding="utf-8")
        assert "txt" in text
        assert "narration-1.wav" not in text
        assert text.startswith("1\n00:00:00,000 --> 00:00:01,000\ntxt\n")

    def test_custom_arrow(self, tmp_path):
        out = write_srt([(0.0, 1.0, "hi")], tmp_path / "c.srt", arrow=" ==> ")
        assert " ==> " in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# resolve_binary
# ---------------------------------------------------------------------------


class TestResolveBinary:
    def test_missing_binary_raises_clear_error(self):
        with pytest.raises(MixNodeError, match="not on PATH"):
            resolve_binary("definitely-not-a-real-binary-12345")

    def test_resolve_existing_binary(self):
        if HAS_FFMPEG:  # pragma: no cover - environment dependent
            assert resolve_binary(DEFAULT_FFMPEG) == shutil.which(DEFAULT_FFMPEG)


# ---------------------------------------------------------------------------
# _build_command (deterministic, no subprocess)
# ---------------------------------------------------------------------------


class TestBuildCommand:
    def setup_method(self):
        self.node = MixNode(ffmpeg="ffmpeg", duration_of=lambda p: 5.0)
        self.beds = [Path("nodes/music-1.wav"), Path("nodes/music-2.wav")]

    def _cmd(self, beds, cues, total=5.0):
        return self.node._build_command("ffmpeg", beds, cues, total, Path("nodes/mix-1.wav"))

    def _graph(self, cmd):
        return cmd[cmd.index("-filter_complex") + 1]

    def test_uses_ffmpeg_with_y_and_error_log(self):
        cmd = self._cmd(self.beds, [])
        assert cmd[:4] == ["ffmpeg", "-y", "-v", "error"]
        assert "-map" in cmd
        assert cmd[cmd.index("-map") + 1] == "[out]"

    def test_inputs_and_output_flags(self):
        cmd = self._cmd(self.beds, [])
        joined = " ".join(cmd)
        assert "-i nodes/music-1.wav" in joined
        assert "-i nodes/music-2.wav" in joined
        assert "-ac 2" in joined
        assert f"-ar {DEFAULT_SAMPLE_RATE}" in joined
        assert "nodes/mix-1.wav" in cmd

    def test_two_beds_no_captions_amix_only(self):
        graph = self._graph(self._cmd(self.beds, []))
        assert "amix=inputs=2:normalize=1[mbase]" in graph
        assert "sidechaincompress" not in graph
        assert "anoisesrc" not in graph

    def test_single_bed_no_captions_skips_amix(self):
        graph = self._graph(self._cmd([self.beds[0]], []))
        assert "amix=inputs=2" not in graph
        assert "[m0]" in graph
        assert "sidechaincompress" not in graph

    def test_captions_add_ducking_graph(self):
        cues = [(1.0, 2.0, "hello"), (3.0, 4.5, "world")]
        graph = self._graph(self._cmd(self.beds, cues))
        assert "amix=inputs=2:normalize=1[mbase]" in graph
        assert "anoisesrc=d=1.000000:r=44100" in graph
        assert "anoisesrc=d=1.500000:r=44100" in graph
        assert "adelay=1000|1000" in graph
        assert "adelay=3000|3000" in graph
        assert "amix=inputs=2:normalize=0" in graph  # key sum
        assert "apad=pad_dur=5.0" in graph
        assert "sidechaincompress=" in graph
        assert f"threshold={DUCK_THRESHOLD}" in graph
        assert f"ratio={DUCK_RATIO}" in graph
        assert f"attack={DUCK_ATTACK_MS}" in graph
        assert f"release={DUCK_RELEASE_MS}" in graph
        assert "aformat=channel_layouts=stereo" in graph
        assert "atrim=0:5.0" in graph

    def test_single_caption_no_key_amix(self):
        graph = self._graph(self._cmd(self.beds, [(0.5, 1.0, "hi")]))
        assert "anoisesrc=d=0.500000" in graph
        assert "adelay=500|500" in graph
        assert "[b0]apad" in graph
        assert "amix=inputs=2:normalize=0" not in graph
        assert "sidechaincompress=" in graph

    def test_start_at_zero_has_no_delay(self):
        graph = self._graph(self._cmd(self.beds, [(0.0, 1.0, "now")]))
        assert "adelay=0|0" in graph

    def test_zero_duration_cue_is_skipped(self):
        graph = self._graph(self._cmd(self.beds, [(1.0, 1.0, "noop"), (2.0, 3.0, "real")]))
        assert "raw0]" not in graph
        assert "adelay=1000|1000" not in graph
        assert "adelay=2000|2000" in graph
        assert "raw1]" in graph


# ---------------------------------------------------------------------------
# MixNode.run (subprocess mocked)
# ---------------------------------------------------------------------------


class TestRunMocked:
    def _node(self):
        return MixNode(ffmpeg="ffmpeg-fake", duration_of=lambda p: 5.0)

    def _touch_beds(self, tmp_path, names=("music-1.wav", "music-2.wav")):
        beds = []
        for n in names:
            p = tmp_path / n
            p.write_bytes(b"\x00\x00")
            beds.append(p)
        return beds

    def test_run_shells_ffmpeg_and_writes_srt(self, tmp_path, monkeypatch):
        node = self._node()
        beds = self._touch_beds(tmp_path)
        out = tmp_path / "nodes" / "mix-1.wav"
        out.parent.mkdir(parents=True)
        captured: dict[str, Any] = {}

        def fake_run(cmd, **_kw):
            captured["cmd"] = cmd
            out.write_bytes(b"\x00\x00\x00\x00")
            return mock.Mock(returncode=0, stderr="", stdout="")

        monkeypatch.setattr("music_cli.studio.nodes.ffmpeg.subprocess.run", fake_run)

        result = node.run(beds, [(1.0, 2.0, "Chapter 1"), (3.0, 4.0, "Chapter 2")], out)

        assert result == out
        assert out.exists()
        cmd = captured["cmd"]
        assert cmd[0] == "ffmpeg-fake"
        graph = cmd[cmd.index("-filter_complex") + 1]
        assert "amix=inputs=2:normalize=1[mbase]" in graph
        assert "sidechaincompress=" in graph
        srt = out.parent / "captions.srt"
        assert srt.exists()
        text = srt.read_text(encoding="utf-8")
        assert "Chapter 1" in text and "Chapter 2" in text
        assert "00:00:01,000 --> 00:00:02,000" in text
        assert "00:00:03,000 --> 00:00:04,000" in text

    def test_run_propagates_ffmpeg_failure(self, tmp_path, monkeypatch):
        node = self._node()
        beds = self._touch_beds(tmp_path, ("music-1.wav",))
        out = tmp_path / "out.wav"
        monkeypatch.setattr(
            "music_cli.studio.nodes.ffmpeg.subprocess.run",
            lambda cmd, **_kw: mock.Mock(returncode=1, stderr="boom", stdout=""),
        )
        with pytest.raises(MixNodeError, match="ffmpeg mix failed"):
            node.run(beds, [], out)

    def test_run_success_without_output_file_raises(self, tmp_path, monkeypatch):
        node = self._node()
        beds = self._touch_beds(tmp_path, ("music-1.wav",))
        out = tmp_path / "out.wav"
        monkeypatch.setattr(
            "music_cli.studio.nodes.ffmpeg.subprocess.run",
            lambda cmd, **_kw: mock.Mock(returncode=0, stderr="", stdout=""),
        )
        with pytest.raises(MixNodeError, match="produced no file"):
            node.run(beds, [], out)

    def test_run_missing_input_raises(self, tmp_path):
        node = self._node()
        with pytest.raises(MixNodeError, match="missing mix input"):
            node.run([tmp_path / "does-not-exist.wav"], [], tmp_path / "o.wav")

    def test_run_empty_nodes_raises(self, tmp_path):
        node = self._node()
        with pytest.raises(MixNodeError, match="nodes must not be empty"):
            node.run([], [], tmp_path / "o.wav")

    def test_run_bad_caption_window_raises(self, tmp_path):
        node = self._node()
        beds = self._touch_beds(tmp_path, ("music-1.wav",))
        with pytest.raises(MixNodeError, match="invalid caption window"):
            node.run(beds, [(2.0, 1.0, "bad")], tmp_path / "o.wav")


# ---------------------------------------------------------------------------
# real end-to-end smoke mix (requires ffmpeg + ffprobe on PATH)
# ---------------------------------------------------------------------------


_HAS_MEDIA = HAS_FFMPEG and HAS_FFPROBE


@pytest.mark.skipif(not _HAS_MEDIA, reason="ffmpeg/ffprobe not installed")
class TestSmoke:
    def test_real_mix_with_captions(self, tmp_path):
        nodes_dir = tmp_path / "nodes"
        nodes_dir.mkdir()
        bed1 = _tone(nodes_dir / "music-1.wav", freq=440, duration=5.0)
        bed2 = _tone(nodes_dir / "music-2.wav", freq=880, duration=5.0)
        out = nodes_dir / "mix-1.wav"

        # Real probing path (no duration_of injection -> uses run_ffprobe).
        node = MixNode(ffmpeg=resolve_binary(DEFAULT_FFMPEG))
        result = node.run(
            [bed1, bed2],
            [(1.0, 2.0, "Chapter 1"), (3.0, 4.0, "Chapter 2")],
            out,
        )

        assert result == out
        assert out.exists()
        probe = subprocess.run(
            [
                shutil.which("ffprobe"),
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=channels,sample_rate",
                "-of",
                "default=nw=1",
                str(out),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        stdout = probe.stdout
        assert "duration=5" in stdout
        assert "channels=2" in stdout
        assert "sample_rate=44100" in stdout

        srt = nodes_dir / "captions.srt"
        assert srt.exists()
        text = srt.read_text(encoding="utf-8")
        assert "Chapter 1" in text and "Chapter 2" in text
        assert "00:00:01,000 --> 00:00:02,000" in text
        assert "00:00:03,000 --> 00:00:04,000" in text
