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
import math
import re
import shutil
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .director import DirectorError, M3Director
from .nodes.assemble import AssembleNode, AssembleNodeError
from .nodes.base import NodeError, NodeLockedError
from .nodes.ffmpeg import DEFAULT_FFMPEG, MixNode, MixNodeError, resolve_binary
from .nodes.music import MusicNode
from .nodes.speech import SpeechNode
from .nodes.video import BuildBudget, VideoNode
from .schemas import CreativePlan, ProjectManifest
from .trace import (
    DEFAULT_DIST_DIR,
    NODES_DIRNAME,
    PLAN_FILENAME,
    PREMIERE_FILENAME,
    TRACE_FILENAME,
    TraceWriter,
    dump_plan_yaml,
    init_project_layout,
    load_plan_yaml,
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
_PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")


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
    video_nodes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_dir": str(self.project_dir),
            "plan_id": self.plan.get("plan_id"),
            "nodes": list(self.nodes),
            "video_nodes": list(self.video_nodes),
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
            raw_project_id = data["project_id"]
        except KeyError as exc:
            raise BuildError("plan", "brief missing 'project_id'") from exc
        if not isinstance(raw_project_id, str):
            raise BuildError("plan", "brief.project_id must be a string")
        project_id = raw_project_id.strip()
        if not _PROJECT_ID_RE.fullmatch(project_id):
            raise BuildError(
                "plan",
                "brief.project_id must be a lowercase slug (2-63 characters)",
            )
        raw_description = data.get("description") or data.get("brief")
        if not isinstance(raw_description, str) or not raw_description.strip():
            raise BuildError("plan", "brief.description (or brief) must be non-empty")
        description = raw_description.strip()
        duration = data.get("duration_seconds")
        if duration is not None:
            if isinstance(duration, bool):
                raise BuildError("plan", "brief.duration_seconds must be a number")
            try:
                duration = float(duration)
            except (TypeError, ValueError) as exc:
                raise BuildError("plan", "brief.duration_seconds must be a number") from exc
            if not math.isfinite(duration) or duration <= 0:
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
    # Lazy imports keep the studio package importable without the optional
    # cloud dependencies. Credentials are loaded from the same OS keyring
    # used by ``mc cloud key set gmi``; they never come from the brief.
    from ..cloud.gmi import GMIAdapter
    from ..cloud.secrets import get_api_key
    from .nodes.base import FfprobeProbe, default_download

    try:
        api_key = get_api_key("gmi")
    except Exception as exc:
        raise BuildError("plan", f"could not load the GMI Cloud API key: {exc}") from exc
    if not api_key:
        raise BuildError(
            "plan",
            "no GMI Cloud API key stored; set one with: mc cloud key set gmi",
        )

    adapter = GMIAdapter(api_key)
    director = M3Director(adapter, trace_path=proj_dir / "trace.jsonl")
    probe = FfprobeProbe()
    music = MusicNode(adapter, proj_dir=proj_dir, downloader=default_download, probe=probe)
    speech = SpeechNode(adapter, proj_dir=proj_dir, downloader=default_download, probe=probe)
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

    def run(
        self,
        brief: Brief,
        *,
        force: bool = False,
        confirm: bool = False,
        no_h3: bool = False,
        manifest: Any | None = None,
    ) -> BuildResult:
        """Run the build for ``brief`` and return the outcome.

        ``force`` ignores the node lock state and regenerates every audio node
        (useful for ``--force`` rebuilds or after a schema change).  Video
        scenes are generated only when ``confirm`` or ``no_h3`` is selected;
        this keeps the P3 audio-only default intact while exposing the P4
        scene controls before the full composer lands in P4.2.
        """
        if not isinstance(brief, Brief):
            raise BuildError("plan", f"brief must be a Brief, got {type(brief).__name__}")
        proj_dir = init_project_layout(self.dist_dir, brief.project_id)
        paths = project_paths(proj_dir)
        trace_path = paths[TRACE_FILENAME]
        result = BuildResult(project_dir=proj_dir, plan={})

        try:
            director, music_node, speech_node = self.adapter_factory(proj_dir, brief)
        except BuildError:
            raise
        except Exception as exc:
            raise BuildError("plan", f"adapter setup failed: {exc}") from exc
        # Re-point the director at the project's trace so all lines land in
        # the right file regardless of what the factory set up.
        director.trace_path = trace_path

        with TraceWriter(trace_path) as trace:
            # A non-forced invocation is also the resume path. Reuse the
            # persisted plan so a no-op cannot pair freshly planned metadata
            # with old node artifacts. ``--force`` intentionally starts over.
            plan = None
            persisted_plan = False
            if not force and paths[PLAN_FILENAME].exists():
                plan = self._load_persisted_plan(paths[PLAN_FILENAME], brief, trace)
                persisted_plan = plan is not None
            if plan is None:
                plan = self._plan(director, brief, trace)
                result.plan = plan.to_dict()
                self._write_plan(paths[PLAN_FILENAME], result.plan)
            else:
                result.plan = plan.to_dict()

            plan_data = result.plan
            if plan_data.get("project_id") != brief.project_id:
                raise BuildError(
                    "plan",
                    "director plan project_id does not match the brief project_id",
                )

            # Reuse node files only when the persisted manifest describes
            # this exact plan's node identities and prompts. A valid but
            # unrelated plan must not inherit assets merely by ordinal.
            node_force = force or not (
                persisted_plan and self._manifest_matches(proj_dir, plan_data, brief)
            )

            # ---- generate audio nodes ------------------------------------
            nodes, captions, any_regen = self._generate_nodes(
                brief, plan, music_node, speech_node, trace, force=node_force
            )
            result.nodes = nodes
            result.regenerated = any_regen

            if not nodes:
                raise BuildError(
                    "generate",
                    f"plan {plan_data.get('plan_id')!r} produced no audio nodes; nothing to build",
                )
            self._write_manifest(
                proj_dir,
                brief,
                plan_data,
                trace_path,
                nodes=nodes,
            )

            # ---- probe & mix ---------------------------------------------
            node_paths = [
                Path(n["output_path"])
                for n in nodes
                if n.get("output_path") and n.get("type") == "music"
            ]
            narration = [
                (Path(n["output_path"]), float(n.get("start") or 0.0))
                for n in nodes
                if n.get("output_path") and n.get("type") == "speech"
            ]
            if not node_paths:
                raise BuildError("generate", "plan produced no music tracks; nothing to mix")
            wav_out = proj_dir / NODES_DIRNAME / "premiere.wav"
            srt_src = wav_out.parent / "captions.srt"
            need_mix = any_regen or not wav_out.exists() or not srt_src.exists()
            if need_mix:
                mix = self._mix_node or MixNode(ffmpeg=self._ffmpeg)
                try:
                    mix.run(
                        node_paths,
                        captions,
                        wav_out,
                        duration=float(plan_data["duration_seconds"]),
                        narration=narration,
                    )
                except (MixNodeError, NodeError) as exc:
                    raise BuildError("compose", f"mix failed: {exc}") from exc
            result.premiere_wav = wav_out

            # The SRT was written next to the WAV by MixNode.run; copy it
            # next to the project root so ``dist/<project>/captions.srt``
            # mirrors what the on-disk spec describes.
            srt_dst = proj_dir / "captions.srt"
            if srt_src.exists():
                shutil.copy2(srt_src, srt_dst)
                result.captions_srt = srt_dst
            self._trace(
                trace,
                TRACE_COMPOSE,
                node_id=plan_data.get("plan_id"),
                payload=str(wav_out),
            )

            # ---- mux to MP4 ---------------------------------------------
            mp4_path = paths[PREMIERE_FILENAME]
            if any_regen or need_mix or not mp4_path.exists():
                result.premiere_mp4 = self._mux_mp4(wav_out, srt_src, mp4_path)
            else:
                result.premiere_mp4 = mp4_path

            # P4.1 creates individual scene assets.  P4.2 owns joining them
            # into the premiere, so the existing audio-only output remains
            # unchanged while the explicit scene flags are opt-in.
            if confirm or no_h3:
                video_nodes, video_budget = self._generate_video_nodes(
                    brief,
                    plan,
                    music_node,
                    trace,
                    confirm=confirm,
                    no_h3=no_h3,
                    manifest=manifest,
                )
                result.video_nodes = video_nodes
                result.nodes = [*nodes, *video_nodes]
                self._write_manifest(
                    proj_dir,
                    brief,
                    plan_data,
                    trace_path,
                    nodes=result.nodes,
                    budget=video_budget,
                )

                # P4.2: assemble scenes with xfade transitions into premiere.mp4
                scene_paths = [
                    Path(v["output_path"])
                    for v in video_nodes
                    if v.get("output_path")
                ]
                if scene_paths and wav_out.exists():
                    srt_for_assembly = wav_out.parent / "captions.srt"
                    premiere_comp = self._assemble_premiere(
                        scene_paths,
                        wav_out,
                        srt_for_assembly if srt_for_assembly.exists() else None,
                        paths[PREMIERE_FILENAME],
                        trace,
                    )
                    if premiere_comp:
                        result.premiere_mp4 = premiere_comp

        return result

    @staticmethod
    def _load_persisted_plan(
        path: Path,
        brief: Brief,
        trace: TraceWriter,
    ) -> CreativePlan | None:
        """Load a valid plan from disk for a resume/no-op build."""
        try:
            data = load_plan_yaml(path)
            plan = CreativePlan.model_validate(data)
        except (OSError, TypeError, ValueError):
            return None
        plan_data = plan.to_dict()
        if plan_data.get("project_id") != brief.project_id:
            return None
        BuildService._trace(
            trace,
            TRACE_PLAN,
            node_id=plan_data.get("plan_id"),
            payload=dump_plan_yaml(plan_data),
        )
        return plan

    @staticmethod
    def _manifest_matches(
        proj_dir: Path,
        plan_data: dict[str, Any],
        brief: Brief,
    ) -> bool:
        """Return whether persisted node metadata matches the current plan."""
        try:
            manifest = load_plan_yaml(proj_dir / "manifest.yaml")
        except (OSError, TypeError, ValueError):
            return False
        if manifest.get("plan_id") != plan_data.get("plan_id"):
            return False
        actual = manifest.get("nodes")
        if not isinstance(actual, list):
            return False
        expected = _expected_node_specs(plan_data, brief)
        if len(actual) != len(expected):
            return False
        for item, spec in zip(actual, expected, strict=True):
            if not isinstance(item, dict):
                return False
            if any(item.get(key) != value for key, value in spec.items()):
                return False
        return True

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
        except Exception as exc:
            # ``BuildService.run`` is synchronous, so an active event loop is
            # an unsupported caller context just like an adapter failure.
            coro.close()
            raise BuildError("plan", f"director.plan failed: {exc}") from exc
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

    @staticmethod
    def _prepare_node(
        node: MusicNode | SpeechNode,
        ordinal: int,
        *,
        force: bool,
    ) -> bool:
        """Select a valid persisted node output or prepare regeneration."""
        node._ordinal = ordinal - 1
        node._path = None
        existing = node._next_path()
        node._ordinal = ordinal - 1
        if not force and existing.exists():
            node._path = existing
            try:
                report = node.probe()
            except Exception:
                report = None
            if report is not None and report.get("ok"):
                node.lock()
                return True
        node._path = None
        node.unlock()
        return False

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
            duration = _coerce_duration(track.get("duration_seconds"))
            if duration is None:
                duration = brief.duration_seconds
            self._prepare_node(music_node, idx, force=force)
            self._trace(trace, TRACE_GENERATE, node_id=f"music-{idx}", payload=prompt)
            try:
                audio_path = asyncio.run(
                    music_node.generate(prompt, lyrics=lyrics, duration=duration)
                )
                any_regen = True
            except NodeLockedError as exc:
                if music_node.path is None:
                    raise BuildError(
                        "generate", f"music node {idx} is locked without an output"
                    ) from exc
                audio_path = music_node.path
            except Exception as exc:
                raise BuildError("generate", f"music node {idx} failed: {exc}") from exc
            try:
                report = music_node.probe()
            except Exception as exc:
                raise BuildError("probe", f"music node {idx} failed: {exc}") from exc
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
            start_value = _coerce_duration(line.get("start"))
            start = start_value if start_value is not None else 0.0
            end_value = _coerce_duration(line.get("end"))
            end = (
                end_value
                if end_value is not None
                else start + max(0.0, brief.duration_seconds or 0.0)
            )
            if end <= start:
                continue
            captions.append((float(start), float(end), text))
            self._prepare_node(speech_node, idx, force=force)
            self._trace(trace, TRACE_GENERATE, node_id=f"speech-{idx}", payload=text)
            try:
                audio_path = asyncio.run(
                    speech_node.generate(text, duration=float(end - start) or None)
                )
                any_regen = True
            except NodeLockedError as exc:
                if speech_node.path is None:
                    raise BuildError(
                        "generate", f"speech node {idx} is locked without an output"
                    ) from exc
                audio_path = speech_node.path
            except Exception as exc:
                raise BuildError("generate", f"speech node {idx} failed: {exc}") from exc
            try:
                report = speech_node.probe()
            except Exception as exc:
                raise BuildError("probe", f"speech node {idx} failed: {exc}") from exc
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
            # No explicit narration cues from the plan — use the brief as
            # one narration cue spanning the full duration. This keeps the
            # audio-only path's Music + Speech output contract intact while
            # still producing a caption for the SRT stream.
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
        try:
            ffmpeg_bin = self._ffmpeg or resolve_binary(DEFAULT_FFMPEG)
        except MixNodeError as exc:
            raise BuildError("compose", str(exc)) from exc
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
        ]
        if srt is None or not srt.exists():
            # With no subtitle input, the audio stream is the only output
            # duration and ``-shortest`` preserves the historical behavior.
            cmd.append("-shortest")
        if srt is not None and srt.exists():
            cmd += ["-map", "1:s", "-c:s", "mov_text"]
        cmd += ["-movflags", "+faststart", out.as_posix()]
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except OSError as exc:
            raise BuildError("compose", f"ffmpeg mp4 mux failed: {exc}") from exc
        if proc.returncode != 0 or not out.exists():
            detail = (proc.stderr or proc.stdout).strip() or "no stderr"
            raise BuildError("compose", f"ffmpeg mp4 mux failed: {detail}")
        return out

    def _assemble_premiere(
        self,
        scenes: list[Path],
        audio: Path,
        srt: Path | None,
        out: Path,
        trace: TraceWriter,
    ) -> Path | None:
        """Compose scene MP4s + audio + SRT into a single premiere with xfade.

        Returns the composed premiere path, or None on failure.
        """
        try:
            assemble = AssembleNode(ffmpeg=self._ffmpeg)
        except AssembleNodeError as exc:
            self._trace(
                trace,
                "assemble",
                node_id="premiere",
                payload=f"assemble failed: {exc}",
            )
            return None
        try:
            result_path = assemble.run(
                scenes,
                audio,
                srt=srt,
                out_path=out,
            )
            self._trace(
                trace,
                "assemble",
                node_id="premiere",
                payload=str(result_path),
            )
            return result_path
        except AssembleNodeError as exc:
            self._trace(
                trace,
                "assemble",
                node_id="premiere",
                payload=f"assemble failed: {exc}",
            )
            return None

    def _generate_video_nodes(
        self,
        brief: Brief,
        plan: CreativePlan,
        music_node: MusicNode,
        trace: TraceWriter,
        *,
        confirm: bool,
        no_h3: bool,
        manifest: Any | None,
    ) -> tuple[list[dict[str, Any]], BuildBudget]:
        """Generate opt-in P4.1 scene assets without composing the premiere."""
        plan_data = plan.to_dict()
        candidates = plan_data.get("scenes") or plan_data.get("shot_list") or []

        if manifest is None:
            manifest_data: dict[str, Any] = {"plan": plan_data}
        elif isinstance(manifest, dict):
            manifest_data = dict(manifest)
            manifest_data["plan"] = plan_data
        else:
            to_dict = getattr(manifest, "to_dict", None)
            manifest_data = dict(to_dict()) if callable(to_dict) else {"plan": plan_data}
            manifest_data["plan"] = plan_data
        if not isinstance(candidates, list):
            return [], BuildBudget.from_manifest(manifest_data)
        video = VideoNode(
            music_node.adapter,
            proj_dir=self.dist_dir / brief.project_id,
            manifest=manifest_data,
            no_h3=no_h3,
            confirm=confirm,
            cover_art=brief.cover_art,
        )
        generated: list[dict[str, Any]] = []
        total_duration = _coerce_duration(plan_data.get("duration_seconds"))
        if total_duration is None:
            total_duration = brief.duration_seconds or 1.0

        for index, scene in enumerate(candidates, start=1):
            if not isinstance(scene, dict):
                continue
            prompt = str(scene.get("visual_prompt") or scene.get("prompt") or "").strip()
            if not prompt:
                continue
            duration = _coerce_duration(scene.get("duration_seconds")) or total_duration
            caption = str(scene.get("description") or prompt)
            if index > 1:
                video.unlock()
            self._trace(trace, TRACE_GENERATE, node_id=f"scene-{index}", payload=prompt)
            try:
                output = asyncio.run(video.generate(prompt, duration, caption=caption))
            except Exception as exc:
                raise BuildError("generate", f"video scene {index} failed: {exc}") from exc
            self._trace(trace, TRACE_PROBE, node_id=f"scene-{index}", payload=str(output))
            generated.append(
                {
                    "id": f"scene-{index}",
                    "type": "video",
                    "status": "done",
                    "locked": True,
                    "output_path": str(output),
                    "duration_seconds": duration,
                    "prompt": prompt,
                }
            )
        return generated, video.budget

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
        *,
        nodes: list[dict[str, Any]],
        budget: BuildBudget | None = None,
    ) -> None:
        manifest_data: dict[str, Any] = {
            "project_id": brief.project_id,
            "plan_id": str(plan_dict.get("plan_id") or ""),
            "constitution": {"title": plan_dict.get("title", brief.project_id)},
            "plan": plan_dict,
            "nodes": [_manifest_node_record(node) for node in nodes],
            "locked_nodes": [node["id"] for node in nodes if node.get("locked") and node.get("id")],
            "dist_dir": str(proj_dir.parent),
            "premiere_path": str(proj_dir / PREMIERE_FILENAME),
            "trace_path": str(trace_path),
        }
        if budget is not None:
            manifest_data["budget"] = {
                "cap": float(budget.cap),
                "spent": float(budget.spent),
                "currency": budget.currency,
                "per_build_cap": float(budget.cap),
            }
        manifest = ProjectManifest(manifest_data)
        manifest_path = proj_dir / "manifest.yaml"
        write_plan_yaml(manifest_path, manifest.to_dict())


# ---------------------------------------------------------------------------
# helpers for the loose plan dict the director returns
# ---------------------------------------------------------------------------


def _manifest_node_record(node: dict[str, Any]) -> dict[str, Any]:
    """Keep persisted node metadata within the manifest schema."""
    record = {
        key: value
        for key, value in node.items()
        if key
        in {
            "id",
            "type",
            "status",
            "locked",
            "output_path",
            "prompt",
            "duration_seconds",
        }
    }
    if node.get("type") == "speech" and "prompt" not in record:
        record["prompt"] = node.get("text", "")
    return record


def _expected_node_specs(plan_dict: dict[str, Any], brief: Brief) -> list[dict[str, str]]:
    """Build stable node identities used to validate resume metadata."""
    specs: list[dict[str, str]] = []
    for idx, track in enumerate(_iter_tracks(plan_dict), start=1):
        specs.append(
            {
                "id": f"music-{idx}",
                "type": "music",
                "prompt": str(track.get("prompt") or brief.description),
            }
        )
    for idx, line in enumerate(_iter_narration(plan_dict, brief), start=1):
        text = str(line.get("text") or "").strip()
        start_value = _coerce_duration(line.get("start"))
        start = start_value if start_value is not None else 0.0
        end_value = _coerce_duration(line.get("end"))
        end = (
            end_value if end_value is not None else start + max(0.0, brief.duration_seconds or 0.0)
        )
        if not text or end <= start:
            continue
        specs.append({"id": f"speech-{idx}", "type": "speech", "prompt": text})
    return specs


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
    no scenes/shot_list, the brief description is used as a single speech
    cue spanning the full duration — which is what the M3 acceptance
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
    if cue_count == 0 and (plan_dict.get("tracks") or plan_dict.get("track")):
        text = (plan_dict.get("brief") or brief.description or "").strip()
        if text:
            yield {"text": text, "start": 0.0, "end": total, "explicit": True}


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


def _strip_yaml_comment(value: str) -> str:
    """Remove an unquoted inline YAML comment from a scalar."""
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote == '"':
            escaped = True
            continue
        if char in {'"', "'"}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            continue
        if char == "#" and quote is None and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.strip()


def _brief_scalar(value: str) -> Any:
    """Parse the scalar subset accepted by a user brief."""
    value = _strip_yaml_comment(value)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1] if value[0] == "'" else value[1:-1].replace('\\"', '"')
    if value == "null":
        return None
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def _load_brief_yaml(path: Path) -> dict[str, Any]:
    """Load the top-level mapping and block scalars used by brief files.

    The project deliberately has no runtime PyYAML dependency. The existing
    plan serializer handles generated plan files, while briefs additionally
    need YAML literal/folded block scalars for a multi-line description.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    data: dict[str, Any] = {}
    index = 0
    while index < len(lines):
        raw = lines[index]
        if not raw.strip() or raw.lstrip().startswith("#"):
            index += 1
            continue
        if raw[0].isspace():
            raise ValueError(f"unexpected indentation on line {index + 1}")
        key, separator, value = raw.partition(":")
        if not separator or not key.strip():
            raise ValueError(f"expected 'key: value' on line {index + 1}")
        key = key.strip()
        value = _strip_yaml_comment(value)
        if value.startswith(("|", ">")):
            style = value[0]
            index += 1
            block: list[str] = []
            while index < len(lines):
                candidate = lines[index]
                if candidate.strip() and not candidate[0].isspace():
                    break
                block.append(candidate)
                index += 1
            nonempty = [line for line in block if line.strip()]
            indent = min(
                (len(line) - len(line.lstrip()) for line in nonempty),
                default=0,
            )
            content = [line[indent:] if line else "" for line in block]
            if style == ">":
                parsed = " ".join(line.strip() for line in content if line.strip())
            else:
                parsed = "\n".join(content)
            if not value.startswith(("|-", ">-")):
                parsed += "\n"
            data[key] = parsed
            continue
        if value in {"", "{}"}:
            nested: dict[str, Any] = {}
            index += 1
            while index < len(lines):
                candidate = lines[index]
                if not candidate.strip() or candidate.lstrip().startswith("#"):
                    index += 1
                    continue
                if not candidate[0].isspace():
                    break
                subkey, sub_separator, subvalue = candidate.strip().partition(":")
                if not sub_separator or not subkey:
                    raise ValueError(f"invalid mapping on line {index + 1}")
                nested[subkey.strip()] = _brief_scalar(subvalue)
                index += 1
            data[key] = nested
            continue
        data[key] = _brief_scalar(value)
        index += 1
    return data


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
        data = _load_brief_yaml(p)
    except (OSError, UnicodeError, ValueError) as exc:
        raise BuildError("plan", f"could not parse brief {p}: {exc}") from exc
    return Brief.from_dict(data)
