"""Audio-only build service for ``mc studio build`` (issue #139, task P3.3).

:class:`BuildService` owns the audio-only pipeline end-to-end: it loads a
YAML brief, calls the :class:`~music_cli.studio.director.M3Director` to
generate a :class:`~music_cli.studio.schemas.CreativePlan`, instantiates
:class:`~music_cli.studio.nodes.music.MusicNode` and
:class:`~music_cli.studio.nodes.speech.SpeechNode`, runs the
:class:`~music_cli.studio.nodes.ffmpeg.MixNode` to blend the audio and
write the SRT, and finally muxes the WAV + SRT into ``premiere.mp4``.

The service is a thin orchestration layer over the existing studio
components, designed to be reused by the later video, revise, and
doctor paths. The Click handler in :mod:`music_cli.cli.studio` does
nothing more than parse arguments and call :meth:`BuildService.run` so
unit tests can exercise the whole pipeline without Click.

The pipeline is **idempotent**: locked nodes are skipped, and the
``premiere.mp4`` is only re-muxed when at least one node was regenerated
(so a no-op rebuild does not bump the premiere's mtime).

A short, fixed event vocabulary is appended to ``trace.jsonl``:

- ``plan`` — the M3 plan arrived (PLAN).
- ``generate`` — a node was generated (one per audio asset).
- ``probe`` — a node was probed (one per audio asset).
- ``compose`` — the final premiere was muxed (COMPOSE).

The :class:`BuildError` raised on pipeline failures carries the failing
stage (``plan`` / ``generate`` / ``probe`` / ``compose``) so the CLI
wrapper can render an actionable ``mc studio build --resume`` hint.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .director import DirectorError, M3Director
from .nodes.base import NodeError, NodeLockedError
from .nodes.ffmpeg import DEFAULT_FFMPEG, MixNode, MixNodeError, resolve_binary
from .nodes.music import MusicNode
from .nodes.speech import SpeechNode
from .schemas import CreativePlan, ProjectManifest
from .trace import (
    DEFAULT_DIST_DIR,
    NODES_DIRNAME,
    PLAN_FILENAME,
    PREMIERE_FILENAME,
    TraceWriter,
    dump_plan_yaml,
    init_project_layout,
    project_paths,
    write_plan_yaml,
)

#: Fixed event vocabulary appended to the trace (P3.3 acceptance).
TRACE_PLAN = "plan"
TRACE_GENERATE = "generate"
TRACE_PROBE = "probe"
TRACE_COMPOSE = "compose"

#: Premiere container — audio-only MP4 with the SRT muxed as a subtitle.
PREMIERE_CODEC = "aac"


class BuildError(RuntimeError):
    """The audio-only build failed; ``stage`` names the failing pipeline step."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(f"[{stage}] {message}")
        self.stage = stage


@dataclass
class BuildResult:
    """Outcome of a :meth:`BuildService.run` call.

    The fields are populated for the audio-only pipeline: ``nodes`` is the
    ordered list of audio nodes that were generated (or skipped because
    locked), and ``premieres`` records the source WAV, the SRT, and the
    final ``premiere.mp4`` paths.
    """

    project_dir: Path
    plan: dict[str, Any]
    nodes: list[dict[str, Any]] = field(default_factory=list)
    premiere_wav: Path | None = None
    captions_srt: Path | None = None
    premiere_mp4: Path | None = None
    regenerated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_dir": str(self.project_dir),
            "plan_id": self.plan.get("plan_id"),
            "nodes": list(self.nodes),
            "premiere_wav": str(self.premiere_wav) if self.premiere_wav else None,
            "captions_srt": str(self.captions_srt) if self.captions_srt else None,
            "premiere_mp4": str(self.premiere_mp4) if self.premiere_mp4 else None,
            "regenerated": self.regenerated,
        }


@dataclass
class Brief:
    """A user-supplied brief, decoupled from the M3 plan shape.

    The brief is the minimal input the build service needs: the
    ``project_id`` (the slug under ``dist/``), a free-form description
    that is forwarded to M3, and an optional ``taste`` profile that
    augments the brief for the plan call. ``Cover_art`` is a hint for
    future video stages; the audio-only build does not consume it yet.
    """

    project_id: str
    description: str
    taste: dict[str, Any] | None = None
    cover_art: str | None = None
    duration_seconds: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Brief:
        if not isinstance(data, dict):
            raise BuildError("plan", f"brief must be a mapping, got {type(data).__name__}")
        try:
            project_id = str(data["project_id"]).strip()
        except KeyError as exc:
            raise BuildError("plan", "brief missing 'project_id'") from exc
        if not project_id:
            raise BuildError("plan", "brief.project_id must be non-empty")
        description = str(data.get("description") or data.get("brief") or "").strip()
        if not description:
            raise BuildError("plan", "brief.description (or brief) must be non-empty")
        duration = data.get("duration_seconds")
        if duration is not None:
            try:
                duration = float(duration)
            except (TypeError, ValueError) as exc:
                raise BuildError("plan", "brief.duration_seconds must be a number") from exc
            if duration <= 0:
                raise BuildError("plan", "brief.duration_seconds must be > 0")
        taste = data.get("taste")
        if taste is not None and not isinstance(taste, dict):
            raise BuildError("plan", "brief.taste must be a mapping when present")
        cover_art = data.get("cover_art")
        if cover_art is not None and not isinstance(cover_art, str):
            raise BuildError("plan", "brief.cover_art must be a string when present")
        return cls(
            project_id=project_id,
            description=description,
            taste=taste,
            cover_art=cover_art,
            duration_seconds=duration,
        )


#: Default factory for the (M3Director, MusicNode, SpeechNode) trio. Tests
#: swap this out to avoid real API calls; production leaves it alone.
AdapterFactory = Callable[[Path, Brief], tuple[M3Director, MusicNode, SpeechNode]]


def default_adapter_factory(
    proj_dir: Path, brief: Brief
) -> tuple[M3Director, MusicNode, SpeechNode]:
    """Default ``(director, music, speech)`` factory.

    Real builds would inject a :class:`~music_cli.cloud.gmi.GMIAdapter`
    here; for the audio-only MVP we keep the trio lazy so callers can
    inject a fake adapter via :attr:`BuildService.adapter_factory`.
    """
    # Lazy import: the cloud adapter is only required at runtime, not at
    # import time, so unit tests can exercise BuildService without
    # keyring/httpx.
    from ..cloud.gmi import GMIAdapter  # noqa: WPS433 — intentional lazy import
    from .nodes.base import default_download
    from .nodes.ffmpeg import DEFAULT_FFPROBE

    adapter = GMIAdapter()
    director = M3Director(adapter, trace_path=proj_dir / "trace.jsonl")
    music = MusicNode(adapter, proj_dir=proj_dir, downloader=default_download, probe=None)
    speech = SpeechNode(adapter, proj_dir=proj_dir, downloader=default_download, probe=None)
    # attach the default probe explicitly to mirror the FFmpegProbe binary
    from .nodes.base import FfprobeProbe

    music._probe = FfprobeProbe(DEFAULT_FFPROBE)  # type: ignore[attr-defined]
    speech._probe = FfprobeProbe(DEFAULT_FFPROBE)  # type: ignore[attr-defined]
    _ = brief  # factory is per-brief, no per-brief state yet
    return director, music, speech


class BuildService:
    """Audio-only build pipeline.

    Construction is cheap (no I/O); :meth:`run` is the only method that
    touches the filesystem. The service is intentionally async-free at
    the public boundary — the audio generation is awaited internally so
    the Click wrapper can call it from a sync context without spinning
    an event loop per invocation.
    """

    def __init__(
        self,
        *,
        dist_dir: str | Path = DEFAULT_DIST_DIR,
        ffmpeg: str | Path | None = None,
        adapter_factory: AdapterFactory | None = None,
        mix_node: MixNode | None = None,
    ) -> None:
        self.dist_dir = Path(dist_dir)
        self._ffmpeg = str(ffmpeg) if ffmpeg else None
        self.adapter_factory: AdapterFactory = adapter_factory or default_adapter_factory
        self._mix_node = mix_node

    # -- public API --------------------------------------------------------

    def run(self, brief: Brief, *, force: bool = False) -> BuildResult:
        """Run the audio-only build for ``brief`` and return the outcome.

        ``force`` ignores the node lock state and regenerates every node
        (useful for ``--force`` rebuilds or after a schema change).
        Idempotent by default: re-running with no changes does not
        regenerate assets or bump the ``premiere.mp4`` mtime.
        """
        if not isinstance(brief, Brief):
            raise BuildError("plan", f"brief must be a Brief, got {type(brief).__name__}")
        proj_dir = init_project_layout(self.dist_dir, brief.project_id)
        paths = project_paths(proj_dir)
        trace_path = paths[PLAN_FILENAME].parent / "trace.jsonl"
        result = BuildResult(project_dir=proj_dir, plan={})

        director, music_node, speech_node = self.adapter_factory(proj_dir, brief)
        # re-point the director at the project's trace so all lines land
        # in the right file regardless of what the factory set up.
        director.trace_path = trace_path

        with TraceWriter(trace_path) as trace:
            # ---- plan ----------------------------------------------------
            plan = self._plan(director, brief, trace)
            result.plan = plan.to_dict()
            self._write_plan(paths[PLAN_FILENAME], result.plan)
            self._write_manifest(proj_dir, brief, result.plan, trace_path)

            # ---- generate audio nodes ------------------------------------
            nodes, captions, any_regen = self._generate_nodes(
                brief, plan, music_node, speech_node, trace, force=force
            )
            result.nodes = nodes
            result.regenerated = any_regen

            if not nodes:
                raise BuildError(
                    "generate",
                    f"plan {plan.plan_id!r} produced no audio nodes; nothing to build",
                )

            # ---- probe & mix ---------------------------------------------
            node_paths = [Path(n["output_path"]) for n in nodes if n.get("output_path")]
            mix = self._mix_node or MixNode(ffmpeg=self._ffmpeg)
            try:
                wav_out = proj_dir / NODES_DIRNAME / "premiere.wav"
                mix.run(node_paths, captions, wav_out)
            except (MixNodeError, NodeError) as exc:
                raise BuildError("compose", f"mix failed: {exc}") from exc
            result.premiere_wav = wav_out

            # The SRT was written next to the WAV by MixNode.run; copy it
            # next to the project root so ``dist/<project>/captions.srt``
            # mirrors what the on-disk spec describes.
            srt_src = wav_out.parent / "captions.srt"
            srt_dst = paths["captions.srt"] if "captions.srt" in paths else None
            if srt_src.exists():
                if srt_dst is None:
                    srt_dst = proj_dir / "captions.srt"
                shutil.copy2(srt_src, srt_dst)
                result.captions_srt = srt_dst
            self._trace(
                trace, TRACE_COMPOSE, node_id=plan.to_dict().get("plan_id"), payload=str(wav_out)
            )

            # ---- mux to MP4 ---------------------------------------------
            if any_regen or not (paths[PREMIERE_FILENAME]).exists():
                mp4 = self._mux_mp4(wav_out, srt_src, paths[PREMIERE_FILENAME])
                result.premiere_mp4 = mp4

        return result

    # -- pipeline stages ---------------------------------------------------

    def _plan(
        self,
        director: M3Director,
        brief: Brief,
        trace: TraceWriter,
    ) -> CreativePlan:
        try:
            coro = director.plan(brief.description)
        except (DirectorError, TypeError, ValueError) as exc:
            raise BuildError("plan", f"director.plan failed: {exc}") from exc
        try:
            plan_obj = asyncio.run(coro)
        except DirectorError as exc:
            raise BuildError("plan", f"director.plan failed: {exc}") from exc
        except RuntimeError:
            # already inside a loop — unlikely in the CLI but defensible
            loop = asyncio.new_event_loop()
            try:
                plan_obj = loop.run_until_complete(coro)
            except DirectorError as exc:
                raise BuildError("plan", f"director.plan failed: {exc}") from exc
            finally:
                loop.close()
        # ``director.plan`` returns a :class:`CreativePlan` already; if a
        # custom adapter returns a raw dict, validate it now.
        if isinstance(plan_obj, CreativePlan):
            plan = plan_obj
        elif isinstance(plan_obj, dict):
            try:
                plan = CreativePlan.model_validate(plan_obj)
            except (ValueError, TypeError) as exc:
                raise BuildError("plan", f"plan schema validation failed: {exc}") from exc
        else:
            raise BuildError("plan", f"director.plan returned unexpected {type(plan_obj).__name__}")
        self._trace(
            trace,
            TRACE_PLAN,
            node_id=plan.to_dict().get("plan_id"),
            payload=dump_plan_yaml(plan.to_dict()),
        )
        return plan

    def _generate_nodes(
        self,
        brief: Brief,
        plan: CreativePlan,
        music_node: MusicNode,
        speech_node: SpeechNode,
        trace: TraceWriter,
        *,
        force: bool,
    ) -> tuple[list[dict[str, Any]], list[tuple[float, float, str]], bool]:
        """Run every audio node from the plan and probe it.

        Returns ``(nodes, captions, any_regen)``. ``nodes`` is the
        manifest-shaped list of node summaries; ``captions`` is the
        sidechain key the mix node will use; ``any_regen`` is True when
        at least one node was regenerated (i.e. the premiere should be
        re-muxed).
        """
        nodes: list[dict[str, Any]] = []
        captions: list[tuple[float, float, str]] = []
        any_regen = False
        plan_dict = plan.to_dict()

        for idx, track in enumerate(_iter_tracks(plan_dict), start=1):
            prompt = str(track.get("prompt") or brief.description)
            lyrics = track.get("lyrics")
            duration = _coerce_duration(track.get("duration_seconds")) or brief.duration_seconds
            music_node._ordinal = idx - 1  # type: ignore[attr-defined]
            music_node._path = None
            existing = music_node._next_path()  # type: ignore[attr-defined]
            music_node._ordinal = idx - 1  # type: ignore[attr-defined]
            locked = (not force) and existing.exists()
            if locked:
                music_node._path = existing  # type: ignore[attr-defined]
                music_node.lock()
            else:
                music_node.unlock()
            self._trace(trace, TRACE_GENERATE, node_id=f"music-{idx}", payload=prompt)
            try:
                audio_path = asyncio.run(
                    music_node.generate(prompt, lyrics=lyrics, duration=duration)
                )
                any_regen = True
            except NodeLockedError:
                if not music_node.path:
                    raise
                audio_path = music_node.path
            except (NodeError, ValueError, TypeError) as exc:
                raise BuildError("generate", f"music node {idx} failed: {exc}") from exc
            report = music_node.probe()
            self._trace(
                trace,
                TRACE_PROBE,
                node_id=f"music-{idx}",
                payload=str(audio_path),
            )
            nodes.append(
                {
                    "id": f"music-{idx}",
                    "type": "music",
                    "status": "done",
                    "locked": True,
                    "output_path": str(audio_path),
                    "duration_seconds": report.get("duration_seconds"),
                    "prompt": prompt,
                }
            )

        for idx, line in enumerate(_iter_narration(plan_dict, brief), start=1):
            text = str(line.get("text") or "").strip()
            if not text:
                continue
            start = _coerce_duration(line.get("start")) or 0.0
            end = _coerce_duration(line.get("end")) or (
                start + max(0.0, brief.duration_seconds or 0.0)
            )
            captions.append((float(start), float(end), text))
            # A speech node is only generated when the plan provides an
            # explicit cue. The brief-as-caption fallback is a caption
            # only — it does not synthesize a narration audio.
            if not line.get("explicit"):
                continue
            speech_node._ordinal = idx - 1  # type: ignore[attr-defined]
            speech_node._path = None
            existing = speech_node._next_path()  # type: ignore[attr-defined]
            speech_node._ordinal = idx - 1  # type: ignore[attr-defined]
            locked = (not force) and existing.exists()
            if locked:
                speech_node._path = existing  # type: ignore[attr-defined]
                speech_node.lock()
            else:
                speech_node.unlock()
            self._trace(trace, TRACE_GENERATE, node_id=f"speech-{idx}", payload=text)
            try:
                audio_path = asyncio.run(
                    speech_node.generate(text, duration=float(end - start) or None)
                )
                any_regen = True
            except NodeLockedError:
                if not speech_node.path:
                    raise
                audio_path = speech_node.path
            except (NodeError, ValueError, TypeError) as exc:
                raise BuildError("generate", f"speech node {idx} failed: {exc}") from exc
            report = speech_node.probe()
            self._trace(
                trace,
                TRACE_PROBE,
                node_id=f"speech-{idx}",
                payload=str(audio_path),
            )
            nodes.append(
                {
                    "id": f"speech-{idx}",
                    "type": "speech",
                    "status": "done",
                    "locked": True,
                    "output_path": str(audio_path),
                    "duration_seconds": report.get("duration_seconds"),
                    "start": float(start),
                    "end": float(end),
                    "text": text,
                }
            )

        if not nodes:
            raise BuildError("generate", "plan produced no audio tracks; nothing to build")
        if not captions:
            # No explicit narration cues from the plan — emit a single
            # caption spanning the full duration so the SRT is still
            # produced and ffprobe shows ≥ 1 subtitle stream. The text
            # is the plan's brief.
            text = (plan_dict.get("brief") or brief.description or "").strip()
            if text:
                captions.append(
                    (
                        0.0,
                        float(plan_dict.get("duration_seconds") or brief.duration_seconds or 60.0),
                        text,
                    )
                )
            else:
                raise BuildError("generate", "plan produced no narration cues; nothing to caption")
        return nodes, captions, any_regen

    def _mux_mp4(self, wav: Path, srt: Path | None, out: Path) -> Path:
        """Wrap ``wav`` (+ optional ``srt``) into ``out`` as an MP4.

        The audio-only MVP uses ffmpeg to repackage the WAV into an MP4
        container with the SRT muxed as a ``mov_text`` subtitle stream
        so ``ffprobe`` reports a video-less, single-audio, single-sub
        file — which is what the M4 acceptance criterion asks for.
        """
        ffmpeg_bin = self._ffmpeg or resolve_binary(DEFAULT_FFMPEG)
        cmd: list[str] = [
            ffmpeg_bin,
            "-y",
            "-v",
            "error",
            "-i",
            wav.as_posix(),
        ]
        if srt is not None and srt.exists():
            cmd += ["-i", srt.as_posix()]
        cmd += [
            "-map",
            "0:a",
            "-c:a",
            PREMIERE_CODEC,
            "-b:a",
            "192k",
            "-shortest",
        ]
        if srt is not None and srt.exists():
            cmd += ["-map", "1:s", "-c:s", "mov_text"]
        cmd += ["-movflags", "+faststart", out.as_posix()]
        out.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0 or not out.exists():
            detail = (proc.stderr or proc.stdout).strip() or "no stderr"
            raise BuildError("compose", f"ffmpeg mp4 mux failed: {detail}")
        return out

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _trace(
        trace: TraceWriter,
        step: str,
        *,
        node_id: str | None = None,
        payload: str | None = None,
    ) -> None:
        trace.append(step=step, node_id=node_id, payload=payload)

    @staticmethod
    def _write_plan(path: Path, plan_dict: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_plan_yaml(path, plan_dict)

    @staticmethod
    def _write_manifest(
        proj_dir: Path,
        brief: Brief,
        plan_dict: dict[str, Any],
        trace_path: Path,
    ) -> None:
        manifest = ProjectManifest(
            project_id=brief.project_id,
            plan_id=str(plan_dict.get("plan_id") or ""),
            constitution={"title": plan_dict.get("title", brief.project_id)},
            plan=plan_dict,
            nodes=[],
            locked_nodes=[],
            dist_dir=str(proj_dir.parent),
            premiere_path=str(proj_dir / PREMIERE_FILENAME),
            trace_path=str(trace_path),
        )
        manifest_path = proj_dir / "manifest.yaml"
        write_plan_yaml(manifest_path, manifest.to_dict())


# ---------------------------------------------------------------------------
# helpers for the loose plan dict the director returns
# ---------------------------------------------------------------------------


def _iter_tracks(plan_dict: dict[str, Any]) -> Iterable[dict[str, Any]]:
    tracks = plan_dict.get("tracks")
    if isinstance(tracks, list):
        for t in tracks:
            if isinstance(t, dict):
                yield t
            else:
                yield {"prompt": str(t)}
    if "track" in plan_dict and isinstance(plan_dict["track"], dict):
        yield plan_dict["track"]


def _iter_narration(plan_dict: dict[str, Any], brief: Brief) -> Iterable[dict[str, Any]]:
    """Yield ``(start, end, text)`` caption cues for the mix sidechain.

    The CreativePlan schema keeps ``scenes``/``shot_list``/``tracks`` as
    structured ``{id, prompt, description, duration_seconds, visual_prompt}``
    entries (no narration field), so the audio-only build treats the
    first scene/shot description as the narration cue. When the plan has
    no scenes/shot_list, the brief description is used as a single cue
    spanning the full duration — which is what the M3 acceptance
    criterion expects.
    """
    candidates = plan_dict.get("scenes") or plan_dict.get("shot_list") or []
    total = float(plan_dict.get("duration_seconds") or brief.duration_seconds or 60.0)
    cue_count = 0
    if isinstance(candidates, list):
        cursor = 0.0
        for s in candidates:
            if not isinstance(s, dict):
                continue
            text = str(s.get("description") or s.get("prompt") or "").strip()
            if not text:
                continue
            dur = _coerce_duration(s.get("duration_seconds")) or 5.0
            yield {
                "text": text,
                "start": cursor,
                "end": min(total, cursor + dur),
                "explicit": True,
            }
            cursor = min(total, cursor + dur)
            cue_count += 1
    if cue_count == 0:
        text = (plan_dict.get("brief") or brief.description or "").strip()
        if text:
            yield {"text": text, "start": 0.0, "end": total, "explicit": False}


def _coerce_duration(value: Any) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v < 0:
        return 0.0
    return v


__all__ = [
    "BuildError",
    "BuildResult",
    "BuildService",
    "Brief",
    "TRACE_COMPOSE",
    "TRACE_GENERATE",
    "TRACE_PLAN",
    "TRACE_PROBE",
    "default_adapter_factory",
    "load_brief_from_yaml",
]


# ---------------------------------------------------------------------------
# YAML brief loader (stdlib YAML in music_cli.studio.trace)
# ---------------------------------------------------------------------------


def load_brief_from_yaml(path: str | Path) -> Brief:
    """Read a YAML brief from ``path`` and return a :class:`Brief`.

    The accepted shape is::

        project_id: neon-rain
        description: |
          A neon-drenched synthwave short set on a rain-slick night
          in a futuristic city.
        duration_seconds: 60
        taste:                  # optional, consumed by the P6.1 stage
          tempo_bpm: 96
        cover_art: dist/neon-rain/cover.png  # optional, consumed by P4

    Raises :class:`BuildError` with stage ``plan`` on any parse or
    validation error.
    """
    p = Path(path)
    if not p.exists():
        raise BuildError("plan", f"brief file not found: {p}")
    try:
        from .trace import load_plan_yaml  # already supports general YAML
    except ImportError as exc:  # pragma: no cover — defensive
        raise BuildError("plan", "yaml loader unavailable") from exc
    data = load_plan_yaml(p)
    return Brief.from_dict(data)
