"""Assemble node: compose video scenes with xfade transitions (P4.2, issue #141).

:class:`AssembleNode` takes a list of scene MP4s, the mixed audio WAV, and the
SRT subtitle file, then uses ffmpeg's ``xfade`` filter to join scenes into a
single ``premiere.mp4`` with crossfade transitions between each scene.  If an
SRT is provided the subtitles are burnt in via the ``subtitles`` filter so the
final file carries visible captions rather than a separate subtitle stream.

The module is stdlib-only at import time and delegates all heavy lifting to
ffmpeg; a missing binary raises :class:`AssembleNodeError` with a clear hint.
"""

from __future__ import annotations

import math
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .ffmpeg import DEFAULT_FFMPEG, MixNodeError, resolve_binary

#: Default video size used when scene durations are unknown.
DEFAULT_VIDEO_SIZE = "1280x720"
#: Default frame rate for the output container.
DEFAULT_FPS = 30
#: Default xfade transition duration in seconds.
DEFAULT_XFADE_DURATION = 1.0


class AssembleNodeError(RuntimeError):
    """The assemble node could not resolve ffmpeg or run the compose command."""


def _ensure_video_size(path: Path, ffmpeg_bin: str, probe: Any | None = None) -> str:
    """Return ``WxH`` for ``path`` by probing or guessing."""
    if probe is not None:
        report = probe(path)
        w = report.get("width")
        h = report.get("height")
        if w and h:
            return f"{w}x{h}"
    try:
        report = _ffprobe_size(ffmpeg_bin, path)
        if report:
            return report
    except AssembleNodeError:
        pass
    return DEFAULT_VIDEO_SIZE


def _ffprobe_size(ffmpeg_bin: str, path: Path) -> str | None:
    """Return ``WxH`` from ffprobe, or None on failure."""
    try:
        result = subprocess.run(
            [
                ffmpeg_bin,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        line = result.stdout.strip()
        if "," in line:
            w, h = line.split(",", 1)
            return f"{w.strip()}x{h.strip()}"
    except OSError:
        pass
    return None


def _probe_duration(ffmpeg_bin: str, path: Path) -> float:
    """Return the duration of ``path`` in seconds via ffprobe."""
    try:
        result = subprocess.run(
            [
                ffmpeg_bin,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=duration",
                "-of", "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            val = result.stdout.strip()
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    except OSError:
        pass
    # Fallback: return a generous default
    return 5.0


class AssembleNode:
    """Compose scene MP4s + audio + SRT into a single premiere MP4.

    ``run(scenes, audio, srt, out_path)`` builds an ffmpeg command that
    chains every scene through an ``xfade`` filter with a configurable
    transition duration, overlays the mixed audio, and optionally burns in
    the SRT subtitles.  The result is written to ``out_path``.

    When ``no_h3`` is True (static-visual fallback scenes), scenes are
    plain MP4s produced by :class:`~music_cli.studio.nodes.video.VideoNode`
    and the same xfade logic applies — no H3 is invoked here.
    """

    def __init__(
        self,
        *,
        ffmpeg: str | Path | None = None,
        xfade_duration: float = DEFAULT_XFADE_DURATION,
        video_size: str | None = None,
        fps: int = DEFAULT_FPS,
    ) -> None:
        self._ffmpeg = str(ffmpeg) if ffmpeg else None
        self.xfade_duration = float(xfade_duration)
        self._video_size = video_size
        self.fps = int(fps)

    def ffmpeg_bin(self) -> str:
        """Return the ffmpeg binary to shell out to (injected or resolved)."""
        return self._ffmpeg or resolve_binary(DEFAULT_FFMPEG)

    def run(
        self,
        scenes: Sequence[str | Path],
        audio: str | Path,
        srt: str | Path | None = None,
        out_path: str | Path | None = None,
        *,
        xfade_duration: float | None = None,
    ) -> Path:
        """Compose scenes + audio + SRT into ``out_path``.

        ``scenes`` is an ordered list of scene MP4 paths.  ``audio`` is the
        mixed WAV from :class:`MixNode`.  ``srt`` is the SubRip subtitle
        file (burnt in when present).  ``xfade_duration`` overrides the
        instance default for this single call.

        Returns the path to the composed premiere MP4.
        """
        if not scenes:
            raise AssembleNodeError("run(scenes, audio, srt, out_path): scenes must not be empty")
        audio_path = Path(audio)
        if not audio_path.exists():
            raise AssembleNodeError(f"missing audio input: {audio_path}")

        scene_paths = [Path(s) for s in scenes]
        for sp in scene_paths:
            if not sp.exists():
                raise AssembleNodeError(f"missing scene input: {sp}")

        duration = float(xfade_duration) if xfade_duration is not None else self.xfade_duration
        if duration <= 0:
            raise AssembleNodeError("xfade_duration must be positive")

        out = Path(out_path) if out_path else (scene_paths[0].parent / "premiere.mp4")

        ffmpeg_bin = self.ffmpeg_bin()
        cmd = self._build_command(
            ffmpeg_bin,
            scene_paths,
            audio_path,
            Path(srt) if srt is not None else None,
            out,
            xfade_duration=duration,
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise AssembleNodeError(f"ffmpeg assemble failed for {out}: {detail}")
        if not out.exists():
            raise AssembleNodeError("ffmpeg reported success but produced no file: " + str(out))
        return out

    def _build_command(
        self,
        ffmpeg_bin: str,
        scenes: list[Path],
        audio: Path,
        srt: Path | None,
        out: Path,
        *,
        xfade_duration: float,
    ) -> list[str]:
        """Assemble the FFmpeg argv for xfade composition.

        The filter graph chains scenes through ``xfade`` transitions:

        .. code-block:: text

            [0:v]setpts=PTS-STARTPTS[v0]
            [1:v]setpts=PTS-STARTPTS[v1]
            [v0][v1]xfade=transition=fade:duration=D:offset=T0[vf0]
            [vf0][v2]xfade=transition=fade:duration=D:offset=T1[vf1]
            ...

        Audio is mapped from the mixed WAV.  When an SRT is present it is
        burnt in via the ``subtitles`` filter applied to the final video
        stream.
        """
        n = len(scenes)
        xfade_dur = xfade_duration
        inputs: list[str] = []
        parts: list[str] = []

        # Register inputs
        for i, sp in enumerate(scenes):
            inputs.extend(["-i", str(sp)])
        inputs.extend(["-i", str(audio)])
        if srt is not None:
            inputs.extend(["-i", str(srt)])

        # Video: setpts on each input to avoid timestamp issues
        for i in range(n):
            parts.append(f"[{i}:v]setpts=PTS-STARTPTS[v{i}]")

        if n == 1:
            # Single scene: no xfade needed, just pass through
            video_out = "[v0]"
        else:
            # Chain xfade filters
            # offset = cumulative duration of previous scenes minus overlap
            offset = 0.0
            prev_label = "v0"
            for i in range(1, n):
                dur = _probe_duration(ffmpeg_bin, scenes[i - 1])
                offset += dur - xfade_dur
                next_label = f"v{i}"
                xf_label = f"xf{i - 1}"
                parts.append(
                    f"[v{prev_label}][v{next_label}]"
                    f"xfade=transition=fade:duration={xfade_dur:.3f}:offset={offset:.3f}[{xf_label}]"
                )
                prev_label = xf_label
            video_out = f"[{prev_label}]"

        cmd: list[str] = [ffmpeg_bin, "-y", "-v", "error"]
        cmd.extend(inputs)

        # Build filter graph
        filter_parts = list(parts)

        # Scale to uniform size if needed
        if self._video_size:
            filter_parts.append(f"{video_out}scale={self._video_size},setfps={self.fps}[vs]")
            video_out = "[vs]"
        else:
            filter_parts.append(f"{video_out}setfps={self.fps}[vs]")
            video_out = "[vs]"

        # Burn in SRT subtitles if present
        if srt is not None:
            filter_parts.append(f"[vs]subtitles='{srt.as_posix()}'[final]")
            video_out = "[final]"

        cmd.extend([
            "-filter_complex",
            ";".join(filter_parts),
            "-map", video_out,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-map", f"{n}:a",  # audio from the WAV input (index n)
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(out.resolve()),
        ])

        return cmd


__all__ = [
    "AssembleNode",
    "AssembleNodeError",
    "DEFAULT_FPS",
    "DEFAULT_VIDEO_SIZE",
    "DEFAULT_XFADE_DURATION",
]
