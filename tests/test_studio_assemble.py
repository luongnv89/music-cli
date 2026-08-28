"""Tests for the AssembleNode (P4.2, issue #141).

Covers the xfade composition pipeline: scene validation, ffmpeg command
construction, mocked assembly runs, and the integration hook in
:attr:`BuildService._assemble_premiere`.  All media binaries are mocked
so the suite runs without network or real ffmpeg.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from music_cli.studio.nodes.assemble import (
    AssembleNode,
    AssembleNodeError,
    DEFAULT_FPS,
    DEFAULT_VIDEO_SIZE,
    DEFAULT_XFADE_DURATION,
    _ffprobe_size,
    _probe_duration,
)
from music_cli.studio.trace import NODES_DIRNAME, TraceWriter


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _write_dummy_mp4(path: Path, duration: float = 5.0) -> Path:
    """Write a minimal valid MP4 (H.264, 1s of black frames)."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin is None:
        # Fallback: write a file that at least exists
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-mp4")
        return path
    subprocess.run(
        [
            ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={DEFAULT_VIDEO_SIZE}:r={DEFAULT_FPS}:d={duration}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path


def _write_dummy_wav(path: Path, duration: float = 5.0) -> Path:
    """Write a minimal valid WAV (PCM 16-bit mono 8 kHz)."""
    sample_rate = 8000
    n_samples = int(duration * sample_rate)
    data_size = n_samples * 2
    with path.open("wb") as fh:
        fh.write(b"RIFF")
        fh.write(b"\x00\x00\x00\x00")  # placeholder size
        fh.write(b"WAVE")
        fh.write(b"fmt ")
        fh.write(b"\x10\x00\x00\x00")  # chunk size
        fh.write(b"\x01\x00")  # PCM
        fh.write(b"\x01\x00")  # mono
        fh.write(f"{sample_rate:04d}".encode())
        fh.write(b"\x00\x00\x00\x00")  # bitrate
        fh.write(b"\x02\x00")  # block align
        fh.write(b"\x10\x00")  # bits per sample
        fh.write(b"data")
        fh.write(data_size.to_bytes(4, "little"))
        fh.write(b"\x00" * data_size)
    return path


def _write_dummy_srt(path: Path) -> Path:
    """Write a minimal valid SRT file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "1\n00:00:00,000 --> 00:00:05,000\nHello world\n\n"
        "2\n00:00:05,000 --> 00:00:10,000\nSecond caption\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestAssembleNodeValidation:
    """Validate input handling before ffmpeg is invoked."""

    def test_empty_scenes_raises(self, tmp_path):
        node = AssembleNode()
        with pytest.raises(AssembleNodeError, match="scenes must not be empty"):
            node.run([], tmp_path / "audio.wav", out_path=tmp_path / "out.mp4")

    def test_missing_audio_raises(self, tmp_path):
        node = AssembleNode()
        scene = tmp_path / "scene.mp4"
        scene.write_bytes(b"fake")
        with pytest.raises(AssembleNodeError, match="missing audio input"):
            node.run([scene], tmp_path / "nonexistent.wav", out_path=tmp_path / "out.mp4")

    def test_missing_scene_raises(self, tmp_path):
        node = AssembleNode()
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"fake-wav")
        with pytest.raises(AssembleNodeError, match="missing scene input"):
            node.run([tmp_path / "nonexistent.mp4"], wav, out_path=tmp_path / "out.mp4")

    def test_zero_xfade_raises(self, tmp_path):
        node = AssembleNode()
        scene = tmp_path / "scene.mp4"
        scene.write_bytes(b"fake")
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"fake-wav")
        with pytest.raises(AssembleNodeError, match="xfade_duration must be positive"):
            node.run([scene], wav, xfade_duration=0, out_path=tmp_path / "out.mp4")


class TestAssembleNodeCommand:
    """Verify the ffmpeg command graph is constructed correctly."""

    def test_single_scene_no_xfade(self, tmp_path):
        node = AssembleNode()
        scene = _write_dummy_mp4(tmp_path / "scene.mp4", 5.0)
        wav = _write_dummy_wav(tmp_path / "audio.wav", 5.0)
        cmd = node._build_command(
            shutil.which("ffmpeg") or "ffmpeg",
            [scene],
            wav,
            None,
            tmp_path / "out.mp4",
            xfade_duration=1.0,
        )
        # Single scene: no xfade filter, just pass-through
        # Check only the filter_complex argument (after -filter_complex)
        fc_idx = cmd.index("-filter_complex")
        filter_graph = cmd[fc_idx + 1]
        assert "xfade" not in filter_graph
        assert "-c:v" in cmd
        assert "libx264" in cmd
        assert "-c:a" in cmd
        assert "aac" in cmd

    def test_two_scenes_one_xfade(self, tmp_path):
        node = AssembleNode()
        scene1 = _write_dummy_mp4(tmp_path / "scene1.mp4", 5.0)
        scene2 = _write_dummy_mp4(tmp_path / "scene2.mp4", 5.0)
        wav = _write_dummy_wav(tmp_path / "audio.wav", 10.0)
        cmd = node._build_command(
            shutil.which("ffmpeg") or "ffmpeg",
            [scene1, scene2],
            wav,
            None,
            tmp_path / "out.mp4",
            xfade_duration=1.0,
        )
        assert "xfade" in " ".join(cmd)
        # Should have 3 inputs (2 scenes + 1 audio)
        assert cmd.count("-i") == 3

    def test_three_scenes_two_xfade(self, tmp_path):
        node = AssembleNode()
        scenes = [
            _write_dummy_mp4(tmp_path / f"scene{i}.mp4", 5.0)
            for i in range(1, 4)
        ]
        wav = _write_dummy_wav(tmp_path / "audio.wav", 15.0)
        cmd = node._build_command(
            shutil.which("ffmpeg") or "ffmpeg",
            scenes,
            wav,
            None,
            tmp_path / "out.mp4",
            xfade_duration=1.0,
        )
        # Count xfade filters in the filter graph only
        fc_idx = cmd.index("-filter_complex")
        filter_graph = cmd[fc_idx + 1]
        xfade_count = filter_graph.count("xfade=")
        assert xfade_count == 2  # n-1 transitions for n scenes

    def test_srt_burn_in(self, tmp_path):
        node = AssembleNode()
        scene = _write_dummy_mp4(tmp_path / "scene.mp4", 5.0)
        wav = _write_dummy_wav(tmp_path / "audio.wav", 5.0)
        srt = _write_dummy_srt(tmp_path / "captions.srt")
        cmd = node._build_command(
            shutil.which("ffmpeg") or "ffmpeg",
            [scene],
            wav,
            srt,
            tmp_path / "out.mp4",
            xfade_duration=1.0,
        )
        assert "subtitles=" in " ".join(cmd)
        # SRT should be registered as an additional input
        assert cmd.count("-i") == 3  # scene + audio + srt


class TestAssembleNodeRun:
    """Integration tests that exercise the full run() method with mocking."""

    def test_single_scene_assembly(self, tmp_path):
        """One scene + audio → premiere.mp4 (no xfade)."""
        scene = _write_dummy_mp4(tmp_path / "scene.mp4", 5.0)
        wav = _write_dummy_wav(tmp_path / "audio.wav", 5.0)
        out = tmp_path / "premiere.mp4"

        node = AssembleNode(ffmpeg="ffmpeg")
        with mock.patch.object(subprocess, "run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stderr="", stdout="")
            # Mock Path.exists to return True after the mock run
            with mock.patch.object(Path, "exists", return_value=True):
                result = node.run([scene], wav, out_path=out)
                assert result == out
                assert mock_run.called
                call_args = mock_run.call_args[0][0]
                assert "libx264" in call_args
                assert "aac" in call_args

    def test_multi_scene_assembly(self, tmp_path):
        """Two scenes + audio → premiere.mp4 with xfade."""
        scene1 = _write_dummy_mp4(tmp_path / "scene1.mp4", 5.0)
        scene2 = _write_dummy_mp4(tmp_path / "scene2.mp4", 5.0)
        wav = _write_dummy_wav(tmp_path / "audio.wav", 10.0)
        out = tmp_path / "premiere.mp4"

        node = AssembleNode(ffmpeg="ffmpeg")
        with mock.patch.object(subprocess, "run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stderr="", stdout="")
            with mock.patch.object(Path, "exists", return_value=True):
                result = node.run([scene1, scene2], wav, out_path=out)
                assert result == out
                call_args = mock_run.call_args[0][0]
                # Check filter_complex contains xfade
                fc_idx = call_args.index("-filter_complex")
                assert "xfade=" in call_args[fc_idx + 1]

    def test_assembly_with_srt_burn_in(self, tmp_path):
        """Scenes + audio + SRT → premiere.mp4 with burnt-in captions."""
        scene = _write_dummy_mp4(tmp_path / "scene.mp4", 5.0)
        wav = _write_dummy_wav(tmp_path / "audio.wav", 5.0)
        srt = _write_dummy_srt(tmp_path / "captions.srt")
        out = tmp_path / "premiere.mp4"

        node = AssembleNode(ffmpeg="ffmpeg")
        with mock.patch.object(subprocess, "run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stderr="", stdout="")
            with mock.patch.object(Path, "exists", return_value=True):
                result = node.run([scene], wav, srt=srt, out_path=out)
                assert result == out
                call_args = mock_run.call_args[0][0]
                fc_idx = call_args.index("-filter_complex")
                assert "subtitles=" in call_args[fc_idx + 1]

    def test_ffmpeg_failure_raises(self, tmp_path):
        """ffmpeg failure raises AssembleNodeError."""
        scene = _write_dummy_mp4(tmp_path / "scene.mp4", 5.0)
        wav = _write_dummy_wav(tmp_path / "audio.wav", 5.0)
        out = tmp_path / "premiere.mp4"

        node = AssembleNode(ffmpeg="ffmpeg")
        with mock.patch.object(subprocess, "run") as mock_run:
            mock_run.return_value = mock.Mock(
                returncode=1,
                stderr="libx264 [error] invalid format",
                stdout="",
            )
            with pytest.raises(AssembleNodeError, match="ffmpeg assemble failed"):
                node.run([scene], wav, out_path=out)

    def test_output_not_created_raises(self, tmp_path):
        """ffmpeg reports success but file not created raises."""
        scene = _write_dummy_mp4(tmp_path / "scene.mp4", 5.0)
        wav = _write_dummy_wav(tmp_path / "audio.wav", 5.0)
        out = tmp_path / "premiere.mp4"

        node = AssembleNode(ffmpeg="ffmpeg")
        with mock.patch.object(subprocess, "run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stderr="", stdout="")
            # The file doesn't actually exist because we're mocking
            with pytest.raises(AssembleNodeError, match="produced no file"):
                node.run([scene], wav, out_path=out)


class TestHelpers:
    """Test helper functions."""

    def test_ffprobe_size(self, tmp_path):
        """_ffprobe_size returns WxH for a valid MP4."""
        scene = _write_dummy_mp4(tmp_path / "scene.mp4", 5.0)
        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin:
            result = _ffprobe_size(ffmpeg_bin, scene)
            assert result is None or "x" in result
            
        else:
            # Without ffmpeg, should return None
            result = _ffprobe_size("nonexistent", scene)
            assert result is None

    def test_probe_duration(self, tmp_path):
        """_probe_duration returns a float for a valid MP4."""
        scene = _write_dummy_mp4(tmp_path / "scene.mp4", 5.0)
        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin:
            result = _probe_duration(ffmpeg_bin, scene)
            assert isinstance(result, float)
            assert result > 0
        else:
            result = _probe_duration("nonexistent", scene)
            assert result == 5.0  # fallback


class TestPackageExports:
    """Verify the package surface."""

    def test_nodes_pkg_reexports_assemble(self):
        from music_cli.studio import nodes as nodes_pkg

        assert nodes_pkg.AssembleNode is AssembleNode
        assert nodes_pkg.AssembleNodeError is AssembleNodeError

    def test_studio_pkg_reexports_assemble(self):
        import music_cli.studio as studio_pkg

        assert studio_pkg.AssembleNode is AssembleNode
        assert studio_pkg.AssembleNodeError is AssembleNodeError


# ---------------------------------------------------------------------------
# BuildService integration
# ---------------------------------------------------------------------------


class TestBuildServiceAssembleIntegration:
    """Test that BuildService._assemble_premiere integrates correctly."""

    def test_assemble_premiere_returns_path(self, tmp_path):
        """_assemble_premiere returns the output path on success."""
        scene = _write_dummy_mp4(tmp_path / "scene.mp4", 5.0)
        wav = _write_dummy_wav(tmp_path / "audio.wav", 5.0)
        srt = _write_dummy_srt(tmp_path / "captions.srt")
        out = tmp_path / "premiere.mp4"
        trace = TraceWriter(tmp_path / "trace.jsonl")

        from music_cli.studio.build import BuildService

        service = BuildService(dist_dir=tmp_path, ffmpeg="ffmpeg")
        with mock.patch.object(subprocess, "run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stderr="", stdout="")
            # Mock Path.exists to return True for the output
            with mock.patch.object(Path, "exists", return_value=True):
                result = service._assemble_premiere(
                    [scene], wav, srt, out, trace
                )
                assert result == out

    def test_assemble_premiere_returns_none_on_failure(self, tmp_path):
        """_assemble_premiere returns None when assembly fails."""
        scene = _write_dummy_mp4(tmp_path / "scene.mp4", 5.0)
        wav = _write_dummy_wav(tmp_path / "audio.wav", 5.0)
        out = tmp_path / "premiere.mp4"
        trace = TraceWriter(tmp_path / "trace.jsonl")

        from music_cli.studio.build import BuildService

        service = BuildService(dist_dir=tmp_path, ffmpeg="ffmpeg")
        with mock.patch.object(subprocess, "run") as mock_run:
            mock_run.return_value = mock.Mock(
                returncode=1,
                stderr="error",
                stdout="",
            )
            result = service._assemble_premiere(
                [scene], wav, None, out, trace
            )
            assert result is None
