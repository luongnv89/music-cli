"""FFmpeg mix node and SRT caption generation (issue #138, task P3.2).

:class:`MixNode` layers the audio-only build's generated WAVs with ffmpeg
(``amix`` to blend the music/instrument beds) and ducks them under the
narration driven by the same caption list that :func:`write_srt` turns into a
SubRip subtitle file. The mix node emits the final audio-only WAV into the
project's ``nodes/`` directory and writes ``captions.srt`` beside it; the SRT
is reused when the video nodes land in Phase P4.

Ducking is applied with ffmpeg's ``sidechaincompress``: each caption's
``(start, end)`` window gates a short white-noise burst that acts as the
sidechain key, so the music is attenuated exactly where narration will sit
while remaining at full level elsewhere. No narration audio is required in the
audio-only pipeline — only the caption timing and text.

Like :mod:`music_cli.studio.nodes.base`, this module is stdlib-only and the
ffmpeg/ffprobe binaries are resolved via :func:`shutil.which` so a missing
binary fails fast with a clear message instead of a cryptic subprocess error.
The ffmpeg command is built by :meth:`MixNode._build_command`, which tests can
call without ever launching a real subprocess.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

from .base import NodeError, run_ffprobe

#: Default ``ffmpeg`` binary looked up on PATH.
DEFAULT_FFMPEG = "ffmpeg"
#: Default ``ffprobe`` binary looked up on PATH.
DEFAULT_FFPROBE = "ffprobe"

#: Sample rate (Hz) the mix graph normalises every input to before mixing.
DEFAULT_SAMPLE_RATE = 44100

#: Sidechain ducking parameters used when narration is present. ``attack`` and
#: ``release`` are in milliseconds (ffmpeg's ``sidechaincompress`` units).
DUCK_THRESHOLD = 0.03
DUCK_RATIO = 8.0
DUCK_ATTACK_MS = 20
DUCK_RELEASE_MS = 300


class MixNodeError(RuntimeError):
    """The mix node could not resolve ffmpeg or run a mix command."""


def resolve_binary(name: str) -> str:
    """Resolve an ffmpeg-family binary on PATH, raising a clear error if absent.

    ``shutil.which`` is used so resolution honours PATH exactly like the probe
    runner in :mod:`music_cli.studio.nodes.base`.
    """
    found = shutil.which(name)
    if found is None:
        raise MixNodeError(f"'{name}' not on PATH; install ffmpeg or pass an explicit clone path")
    return found


def _srt_timestamp(seconds: float) -> str:
    """Format a float number of seconds as an SRT ``HH:MM:SS,mmm`` stamp."""
    total_ms = int(round(max(0.0, float(seconds)) * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def write_srt(
    captions: Iterable[Sequence[Any]],
    out_path: str | Path,
    *,
    arrow: str = " --> ",
) -> Path:
    """Write a valid SubRip ``.srt`` file from ``(start, end, text)`` cues.

    ``captions`` is an iterable of cues, each either a ``(start, end, text)``
    triple or a longer sequence whose first three elements are consumed — any
    trailing entries (such as a narration audio path) are ignored so the same
    caption list can drive both the SRT and the mix node. Indexed blocks are
    separated by blank lines per the SubRip spec. Returns the path written.
    """
    lines: list[str] = []
    for index, cue in enumerate(captions, start=1):
        start, end, text = cue[0], cue[1], cue[2]
        lines.append(f"{index}\n{_srt_timestamp(start)}{arrow}{_srt_timestamp(end)}\n{text}")
    block = "\n\n".join(lines)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(block + ("\n" if block else ""), encoding="utf-8")
    return out


class MixNode:
    """Mix track audio, duck narration under it, and emit a final WAV.

    ``run(nodes, captions, out_path)`` layers every WAV in ``nodes`` with an
    ``amix`` filter, builds a sidechain key from the ``captions`` timing, and
    ducks the mixed bed under narration with ``sidechaincompress``. The final
    WAV is written to ``out_path`` and a ``captions.srt`` is written beside it.
    """

    def __init__(
        self,
        *,
        ffmpeg: str | Path | None = None,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        duck_threshold: float = DUCK_THRESHOLD,
        duck_ratio: float = DUCK_RATIO,
        duck_attack_ms: float = DUCK_ATTACK_MS,
        duck_release_ms: float = DUCK_RELEASE_MS,
        duration_of: Callable[[Path], float] | None = None,
    ) -> None:
        self._ffmpeg = str(ffmpeg) if ffmpeg else None
        self.sample_rate = sample_rate
        self._duck_threshold = duck_threshold
        self._duck_ratio = duck_ratio
        self._duck_attack = duck_attack_ms
        self._duck_release = duck_release_ms
        # Optional duration resolver; defaults to a real ffprobe probe.
        self._duration_of = duration_of

    # -- resolution / probing ------------------------------------------------

    def ffmpeg_bin(self) -> str:
        """Return the ffmpeg binary to shell out to (injected or resolved)."""
        return self._ffmpeg or resolve_binary(DEFAULT_FFMPEG)

    def _duration(self, path: Path) -> float:
        """Return the probed duration of ``path`` in seconds."""
        if self._duration_of is not None:
            return float(self._duration_of(path))
        try:
            report = run_ffprobe(path)
        except NodeError as exc:
            raise MixNodeError(str(exc)) from exc
        duration = report.get("duration_seconds")
        if duration is None:
            raise MixNodeError(f"could not determine duration of {path}")
        return float(duration)

    # -- public API ----------------------------------------------------------

    def run(
        self,
        nodes: Iterable[str | Path],
        captions: Iterable[Sequence[Any]],
        out_path: str | Path,
    ) -> Path:
        """Mix ``nodes`` into ``out_path`` as a single WAV, ducking under narr.

        ``nodes`` is an iterable of music-bed WAV paths layered with
        ``amix``. ``captions`` is a list of ``(start, end, text)`` cues: the
        timing gates the sidechain key that ducks the bed, and the text is
        written to ``out_path.parent / "captions.srt"`` for later reuse in P4.
        """
        music_beds = [Path(n) for n in nodes]
        if not music_beds:
            raise MixNodeError("run(nodes, captions, out_path): nodes must not be empty")
        for bed in music_beds:
            if not bed.exists():
                raise MixNodeError(f"missing mix input: {bed}")

        cue_list = list(captions)
        for cue in cue_list:
            if len(cue) < 3:
                raise MixNodeError(f"captions must be (start, end, text); got {cue!r}")
            start, end = float(cue[0]), float(cue[1])
            if start < 0 or end <= start:
                raise MixNodeError(f"invalid caption window (start, end)=({start}, {end})")

        total_seconds = max(self._duration(bed) for bed in music_beds)
        ffmpeg_bin = self.ffmpeg_bin()
        out = Path(out_path)
        cmd = self._build_command(ffmpeg_bin, music_beds, cue_list, total_seconds, out)

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise MixNodeError(f"ffmpeg mix failed for {out}: {detail}")
        if not out.exists():
            raise MixNodeError("ffmpeg reported success but produced no file: " + str(out))

        # The SRT is written next to the mixed WAV for reuse in P4.
        write_srt(cue_list, out.parent / "captions.srt")
        return out

    # -- command construction ------------------------------------------------

    def _build_command(
        self,
        ffmpeg_bin: str,
        nodes: list[Path],
        cues: list[Sequence[Any]],
        total_seconds: float,
        out: Path,
    ) -> list[str]:
        """Assemble the FFmpeg ``argv`` from the node/caption inputs.

        Separated so tests can assert the exact command/graph without a real
        subprocess. Layering uses ``amix`` for the track beds; narration timing
        drives a synthetic ``anoisesrc`` sidechain key gated by ``adelay`` and
        ``amix``; ``sidechaincompress`` ducks the bed under that key.
        """
        sr = str(self.sample_rate)
        duration = str(float(total_seconds))
        parts: list[str] = []

        for i, _bed in enumerate(nodes):
            parts.append(f"[{i}:a]aresample={sr},aformat=channel_layouts=stereo[m{i}]")
        if len(nodes) > 1:
            beds_in = "".join(f"[m{i}]" for i in range(len(nodes)))
            parts.append(f"{beds_in}amix=inputs={len(nodes)}:normalize=1[mbase]")
            music_base = "[mbase]"
        else:
            music_base = "[m0]"

        intervals: list[int] = []
        if cues:
            for j, cue in enumerate(cues):
                start, end = float(cue[0]), float(cue[1])
                cue_dur = end - start
                if cue_dur <= 0:
                    continue
                delay_ms = int(round(start * 1000))
                parts.append(f"anoisesrc=d={cue_dur:.6f}:r={sr}[raw{j}]")
                parts.append(f"[raw{j}]adelay={delay_ms}|{delay_ms}[b{j}]")
                intervals.append(j)
            if len(intervals) == 1:
                parts.append(f"[b{intervals[0]}]apad=pad_dur={duration}[keypad]")
            else:
                key_ins = "".join(f"[b{j}]" for j in intervals)
                parts.append(
                    f"{key_ins}amix=inputs={len(intervals)}:normalize=0,"
                    f"apad=pad_dur={duration}[keypad]"
                )
            parts.append(
                f"{music_base}[keypad]sidechaincompress="
                f"threshold={self._duck_threshold}:ratio={self._duck_ratio}:"
                f"attack={self._duck_attack}:release={self._duck_release}[ducked]"
            )
            parts.append(f"[ducked]aformat=channel_layouts=stereo,atrim=0:{duration}[out]")
        else:
            parts.append(f"{music_base}aformat=channel_layouts=stereo,atrim=0:{duration}[out]")

        cmd = [ffmpeg_bin, "-y", "-v", "error"]
        for path in nodes:
            cmd += ["-i", str(path)]
        cmd += [
            "-filter_complex",
            ";".join(parts),
            "-map",
            "[out]",
            "-ac",
            "2",
            "-ar",
            sr,
            str(out),
        ]
        return cmd


__all__ = [
    "DEFAULT_FFMPEG",
    "DEFAULT_FFPROBE",
    "DEFAULT_SAMPLE_RATE",
    "DUCK_ATTACK_MS",
    "DUCK_RATIO",
    "DUCK_RELEASE_MS",
    "DUCK_THRESHOLD",
    "MixNode",
    "MixNodeError",
    "resolve_binary",
    "write_srt",
]
