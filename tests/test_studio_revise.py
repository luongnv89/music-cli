"""Tests for ``BuildService.revise`` — plan-diff and partial rebuild (#143).

These tests exercise the revise path without requiring a real M3 adapter:
a scripted ``FakeAdapter`` returns a valid :class:`PlanDiff` so the
plan-diff and partial-rebuild logic can be verified in isolation.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from music_cli.studio.build import (
    BuildError,
    BuildResult,
    BuildService,
    Brief,
    PlanDiff,
    TRACE_PLAN_DIFF,
    TRACE_REGENERATE,
)
from music_cli.studio.director import M3Director
from music_cli.studio.nodes.base import NodeLockedError, NodeError
from music_cli.studio.nodes.ffmpeg import MixNode
from music_cli.studio.nodes.music import MusicNode
from music_cli.studio.nodes.speech import SpeechNode
from music_cli.studio.trace import (
    DEFAULT_DIST_DIR,
    NODES_DIRNAME,
    PLAN_FILENAME,
    PREMIERE_FILENAME,
    TRACE_FILENAME,
    load_plan_yaml,
    load_trace,
    project_dir,
    project_paths,
    write_plan_yaml,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

VALID_PLAN = {
    "plan_id": "plan-001",
    "project_id": "neon-rain",
    "title": "Neon Rain",
    "objective": "Ship a 60s premiere",
    "brief": "A noir rooftop chase in the rain",
    "duration_seconds": 60,
}

VALID_DIFF = {
    "from_plan_id": "plan-001",
    "to_plan_id": "plan-002",
    "reason": "swap motif from rain to thunder",
    "affected_nodes": ["music-1"],
    "locked_nodes": ["speech-1"],
    "regenerate_nodes": ["music-1"],
}

VALID_MANIFEST = {
    "project_id": "neon-rain",
    "plan_id": "plan-001",
    "constitution": {"title": "Neon Rain"},
    "nodes": [
        {"id": "music-1", "type": "music", "status": "done", "locked": True, "output_path": "nodes/asset-1.wav", "prompt": "rain motif"},
        {"id": "speech-1", "type": "speech", "status": "done", "locked": True, "output_path": "nodes/asset-2.wav", "prompt": "narration"},
    ],
    "locked_nodes": ["music-1", "speech-1"],
    "dist_dir": str(DEFAULT_DIST_DIR),
    "premiere_path": "dist/neon-rain/premiere.mp4",
    "trace_path": "dist/neon-rain/trace.jsonl",
}


class FakeAdapter:
    """Replays scripted replies; returns a valid PlanDiff for revise().

    The M3Director calls m3_plan() for both plan and revise steps.
    This adapter returns the plan on the first call and the diff on
    subsequent calls.
    """

    def __init__(self, diff: dict | None = None) -> None:
        self.diff = diff or VALID_DIFF
        self.plan_prompts: list[str] = []
        self.call_count: int = 0

    async def m3_plan(self, prompt: str, **_: object) -> dict[str, str]:
        self.call_count += 1
        self.plan_prompts.append(prompt)
        if self.call_count == 1:
            return {"text": json.dumps(VALID_PLAN)}
        return {"text": json.dumps(self.diff)}

    async def m3_critique(self, prompt: str, **_: object) -> dict[str, str]:
        return {"text": json.dumps({"ok": True})}

    async def m3_speech28_synthesize(self, *args: object, **kwargs: object) -> dict[str, str]:
        return {"text": "https://example.com/speech.wav"}

    async def m3_music3_generate(self, *args: object, **kwargs: object) -> dict[str, str]:
        return {"text": "https://example.com/music.wav"}


def _make_project(tmp_path: Path, manifest: dict | None = None) -> Path:
    """Create a minimal project layout under ``tmp_path/dist/<id>/``."""
    m = manifest or VALID_MANIFEST
    proj = project_dir(tmp_path, m["project_id"])
    proj.mkdir(parents=True, exist_ok=True)
    (proj / NODES_DIRNAME).mkdir(exist_ok=True)

    write_plan_yaml(proj / PLAN_FILENAME, VALID_PLAN)
    write_plan_yaml(proj / "manifest.yaml", m)
    (proj / TRACE_FILENAME).touch()

    for node in m.get("nodes") or []:
        op = node.get("output_path", "")
        if op:
            p = proj / op
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"dummy audio")

    (proj / PREMIERE_FILENAME).write_bytes(b"dummy mp4")
    return proj


def _fake_adapter_factory(
    proj_dir: Path, brief: Brief
) -> tuple[M3Director, MusicNode, SpeechNode]:
    """Return a trio with injectable nodes."""
    adapter = FakeAdapter()
    director = M3Director(adapter, trace_path=proj_dir / TRACE_FILENAME)
    music = MagicMock(spec=MusicNode)
    speech = MagicMock(spec=SpeechNode)
    music.path = proj_dir / NODES_DIRNAME / "asset-1.wav"
    speech.path = proj_dir / NODES_DIRNAME / "asset-2.wav"
    music.lock = MagicMock()
    music.unlock = MagicMock()
    speech.lock = MagicMock()
    speech.unlock = MagicMock()

    async def mock_generate_music(*args, **kwargs):
        return proj_dir / NODES_DIRNAME / "asset-1.wav"

    async def mock_generate_speech(*args, **kwargs):
        return proj_dir / NODES_DIRNAME / "asset-2.wav"

    music.generate = mock_generate_music
    speech.generate = mock_generate_speech
    music.probe = MagicMock(return_value={"ok": True, "duration_seconds": 30.0})
    speech.probe = MagicMock(return_value={"ok": True, "duration_seconds": 15.0})

    return director, music, speech


def _make_service(
    tmp_path: Path, manifest: dict | None = None
) -> BuildService:
    """Create a BuildService with mocked nodes and mix node."""
    _make_project(tmp_path, manifest)

    def factory(proj_dir, brief):
        return _fake_adapter_factory(proj_dir, brief)

    mock_mix = MagicMock()
    mock_mix.run = MagicMock()

    service = BuildService(
        dist_dir=tmp_path,
        adapter_factory=factory,
        mix_node=mock_mix,
    )
    # Mock _mux_mp4 to create a dummy premiere.mp4
    def mock_mux_mp4(wav, srt, out):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"dummy mp4")
        return out
    service._mux_mp4 = mock_mux_mp4

    return service


# ===========================================================================
# revise — happy path
# ===========================================================================


class TestReviseHappyPath:
    def test_revise_returns_build_result(self, tmp_path):
        service = _make_service(tmp_path)
        result = service.revise("neon-rain", "Change the final scene to dawn")
        assert isinstance(result, BuildResult)
        assert result.project_dir.name == "neon-rain"
        assert result.regenerated is True
        assert result.premiere_mp4 is not None

    def test_revise_updates_plan_id(self, tmp_path):
        service = _make_service(tmp_path)
        service.revise("neon-rain", "revise intent")
        updated_plan = load_plan_yaml(tmp_path / "neon-rain" / PLAN_FILENAME)
        assert updated_plan.get("plan_id") == "plan-002"

    def test_revise_appends_plan_diff_trace_entry(self, tmp_path):
        service = _make_service(tmp_path)
        service.revise("neon-rain", "revise intent")
        trace_lines = load_trace(tmp_path / "neon-rain" / TRACE_FILENAME)
        step_values = [rec["step"] for rec in trace_lines]
        assert TRACE_PLAN_DIFF in step_values

    def test_revise_appends_regenerate_trace_entry(self, tmp_path):
        service = _make_service(tmp_path)
        service.revise("neon-rain", "revise intent")
        trace_lines = load_trace(tmp_path / "neon-rain" / TRACE_FILENAME)
        step_values = [rec["step"] for rec in trace_lines]
        assert TRACE_REGENERATE in step_values


# ===========================================================================
# locked nodes stay untouched
# ===========================================================================


class TestLockedNodes:
    def test_locked_nodes_not_in_regenerate_list(self, tmp_path):
        """speech-1 is in locked_nodes; only music-1 should regenerate."""
        _make_project(tmp_path)
        adapter = FakeAdapter({
            **VALID_DIFF,
            "regenerate_nodes": ["music-1"],
            "locked_nodes": ["speech-1"],
        })

        def factory(proj_dir, brief):
            director, music, speech = _fake_adapter_factory(proj_dir, brief)
            director._adapter = adapter
            return director, music, speech

        service = BuildService(
            dist_dir=tmp_path,
            adapter_factory=factory,
            mix_node=MagicMock(),
        )
        service._mux_mp4 = lambda wav, srt, out: (out.write_bytes(b"dummy mp4") or out)
        result = service.revise("neon-rain", "revise intent")
        assert result.regenerated is True

        speech_node = tmp_path / "neon-rain" / NODES_DIRNAME / "asset-2.wav"
        assert speech_node.exists()
        assert speech_node.read_bytes() == b"dummy audio"

    def test_revise_with_no_regenerate_nodes(self, tmp_path):
        """When regenerate_nodes is empty, no nodes are touched."""
        _make_project(tmp_path)
        adapter = FakeAdapter({
            "from_plan_id": "plan-001",
            "to_plan_id": "plan-003",
            "reason": "metadata only",
            "affected_nodes": [],
            "regenerate_nodes": [],
            "locked_nodes": ["music-1", "speech-1"],
        })

        def factory(proj_dir, brief):
            director, music, speech = _fake_adapter_factory(proj_dir, brief)
            director._adapter = adapter
            return director, music, speech

        service = BuildService(
            dist_dir=tmp_path,
            adapter_factory=factory,
            mix_node=MagicMock(),
        )
        service._mux_mp4 = lambda wav, srt, out: (out.write_bytes(b"dummy mp4") or out)
        result = service.revise("neon-rain", "revise intent")
        assert result.regenerated is False


# ===========================================================================
# error paths
# ===========================================================================


class TestReviseErrors:
    def test_project_not_found(self, tmp_path):
        service = BuildService(dist_dir=tmp_path)
        with pytest.raises(BuildError) as excinfo:
            service.revise("nonexistent", "intent")
        assert "not found" in str(excinfo.value)

    def test_no_plan_file(self, tmp_path):
        proj = project_dir(tmp_path, "neon-rain")
        proj.mkdir(parents=True, exist_ok=True)
        (proj / NODES_DIRNAME).mkdir(exist_ok=True)
        service = BuildService(dist_dir=tmp_path, adapter_factory=_fake_adapter_factory)
        with pytest.raises(BuildError) as excinfo:
            service.revise("neon-rain", "intent")
        assert "no plan" in str(excinfo.value)

    def test_no_manifest_file(self, tmp_path):
        proj = project_dir(tmp_path, "neon-rain")
        proj.mkdir(parents=True, exist_ok=True)
        (proj / NODES_DIRNAME).mkdir(exist_ok=True)
        write_plan_yaml(proj / PLAN_FILENAME, VALID_PLAN)
        (proj / TRACE_FILENAME).touch()
        service = BuildService(dist_dir=tmp_path, adapter_factory=_fake_adapter_factory)
        with pytest.raises(BuildError) as excinfo:
            service.revise("neon-rain", "intent")
        assert "no manifest" in str(excinfo.value)

    def test_unknown_node_in_diff(self, tmp_path):
        _make_project(tmp_path)
        adapter = FakeAdapter({
            "from_plan_id": "plan-001",
            "to_plan_id": "plan-002",
            "reason": "bad diff",
            "affected_nodes": ["nonexistent-node"],
            "regenerate_nodes": ["nonexistent-node"],
            "locked_nodes": [],
        })

        def factory(proj_dir, brief):
            director, music, speech = _fake_adapter_factory(proj_dir, brief)
            director._adapter = adapter
            return director, music, speech

        service = BuildService(
            dist_dir=tmp_path,
            adapter_factory=factory,
            mix_node=MagicMock(),
        )
        with pytest.raises(BuildError) as excinfo:
            service.revise("neon-rain", "intent")
        assert "unknown node" in str(excinfo.value)


# ===========================================================================
# plan-diff schema validation
# ===========================================================================


class TestPlanDiffValidation:
    def test_valid_plan_diff_accepted(self):
        assert PlanDiff.validate(VALID_DIFF) == []

    def test_missing_required_fields_rejected(self):
        bad = {"from_plan_id": "a"}
        errs = PlanDiff.validate(bad)
        assert any("to_plan_id" in e for e in errs)
        assert any("reason" in e for e in errs)
        assert any("affected_nodes" in e for e in errs)

    def test_regenerate_nodes_must_be_list(self):
        bad = {**VALID_DIFF, "regenerate_nodes": "music-1"}
        errs = PlanDiff.validate(bad)
        assert any("regenerate_nodes: must be list" in e for e in errs)

    def test_locked_nodes_must_be_list(self):
        bad = {**VALID_DIFF, "locked_nodes": "speech-1"}
        errs = PlanDiff.validate(bad)
        assert any("locked_nodes: must be list" in e for e in errs)

    def test_empty_affected_nodes_is_valid(self):
        empty = {**VALID_DIFF, "affected_nodes": []}
        assert PlanDiff.validate(empty) == []


# ===========================================================================
# trace format
# ===========================================================================


class TestTraceFormat:
    def test_plan_diff_trace_has_step(self, tmp_path):
        service = _make_service(tmp_path)
        service.revise("neon-rain", "revise intent")
        trace_lines = load_trace(tmp_path / "neon-rain" / TRACE_FILENAME)
        diff_entry = next(r for r in trace_lines if r["step"] == TRACE_PLAN_DIFF)
        assert diff_entry.get("node_id") == "plan-002"
        assert "payload_hash" in diff_entry

    def test_regenerate_trace_has_node_id(self, tmp_path):
        service = _make_service(tmp_path)
        service.revise("neon-rain", "revise intent")
        trace_lines = load_trace(tmp_path / "neon-rain" / TRACE_FILENAME)
        regen_entry = next(r for r in trace_lines if r["step"] == TRACE_REGENERATE)
        assert regen_entry.get("node_id") == "music-1"


# ===========================================================================
# CLI integration
# ===========================================================================


class TestCLIRevise:
    def test_revise_command_exists(self):
        from click.testing import CliRunner
        from music_cli.cli.studio import studio_group

        runner = CliRunner()
        result = runner.invoke(studio_group, ["--help"])
        assert "revise" in result.output

    def test_revise_command_requires_project_and_intent(self):
        from click.testing import CliRunner
        from music_cli.cli.studio import studio_revise

        runner = CliRunner()
        result = runner.invoke(studio_revise, ["intent"])
        assert result.exit_code != 0

        result = runner.invoke(studio_revise, ["project"])
        assert result.exit_code != 0


# ===========================================================================
# plan-diff schema validation
# ===========================================================================


class TestPlanDiffValidation:
    def test_valid_plan_diff_accepted(self):
        assert PlanDiff.validate(VALID_DIFF) == []

    def test_missing_required_fields_rejected(self):
        bad = {"from_plan_id": "a"}
        errs = PlanDiff.validate(bad)
        assert any("to_plan_id" in e for e in errs)
        assert any("reason" in e for e in errs)
        assert any("affected_nodes" in e for e in errs)

    def test_regenerate_nodes_must_be_list(self):
        bad = {**VALID_DIFF, "regenerate_nodes": "music-1"}
        errs = PlanDiff.validate(bad)
        assert any("regenerate_nodes: must be list" in e for e in errs)

    def test_locked_nodes_must_be_list(self):
        bad = {**VALID_DIFF, "locked_nodes": "speech-1"}
        errs = PlanDiff.validate(bad)
        assert any("locked_nodes: must be list" in e for e in errs)

    def test_empty_affected_nodes_is_valid(self):
        empty = {**VALID_DIFF, "affected_nodes": []}
        assert PlanDiff.validate(empty) == []
