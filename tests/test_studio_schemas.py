"""Tests for music_cli.studio.schemas — P1.1.

Each schema has >=3 valid and >=3 invalid examples.
Validate() returns list[str]; empty means valid.
"""

from __future__ import annotations

from music_cli.studio.schemas import Constitution, CreativePlan, PlanDiff, ProjectManifest

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _assert_valid(cls, data):
    errs = cls.validate(data)
    assert errs == [], f"expected valid but got errors: {errs}"
    # instance path
    assert cls(data).validate() == []


def _assert_invalid(cls, data, substr: str | None = None):
    errs = cls.validate(data)
    assert errs, f"expected invalid but got no errors for {data}"
    if substr:
        assert any(substr in e for e in errs), f"expected '{substr}' in {errs}"
    # instance path
    assert cls(data).validate() == errs


# ===========================================================================
# Constitution
# ===========================================================================


class TestConstitutionValid:
    def test_minimal(self):
        _assert_valid(
            Constitution,
            {
                "project_id": "neon-rain",
                "title": "Neon Rain",
                "brief": "A noir rooftop",
                "narrative": "A story",
            },
        )

    def test_full(self):
        _assert_valid(
            Constitution,
            {
                "project_id": "proj-123",
                "title": "Neon Rain",
                "brief": "A 60s premiere",
                "narrative": "Rain on neon",
                "style": "noir",
                "motifs": ["rain", "neon"],
                "voice_profile": {"tone": "warm", "narrator": "alto"},
                "visual_style": "cinematic",
                "constraints": {"duration_seconds": 60, "budget_cap": 1.0},
                "version": 1,
            },
        )

    def test_with_taste_profile(self):
        _assert_valid(
            Constitution,
            {
                "project_id": "taste-proj",
                "title": "T",
                "brief": "B",
                "narrative": "N",
                "taste_profile": {"tempo_histogram": [1, 2], "key_distribution": {"C": 0.5}},
                "version": "1.0",
            },
        )


class TestConstitutionInvalid:
    def test_missing_required(self):
        _assert_invalid(Constitution, {"project_id": "x", "title": "t"}, "missing required")

    def test_bad_slug(self):
        _assert_invalid(
            Constitution,
            {"project_id": "Bad Slug!", "title": "t", "brief": "b", "narrative": "n"},
            "slug",
        )

    def test_extra_field(self):
        _assert_invalid(
            Constitution,
            {"project_id": "proj1", "title": "t", "brief": "b", "narrative": "n", "unknown": 1},
            "unexpected",
        )

    def test_bad_motifs(self):
        _assert_invalid(
            Constitution,
            {
                "project_id": "proj1",
                "title": "t",
                "brief": "b",
                "narrative": "n",
                "motifs": "not-a-list",
            },
            "motifs",
        )

    def test_bad_duration(self):
        _assert_invalid(
            Constitution,
            {
                "project_id": "proj1",
                "title": "t",
                "brief": "b",
                "narrative": "n",
                "constraints": {"duration_seconds": -5},
            },
            "duration_seconds",
        )


# ===========================================================================
# CreativePlan
# ===========================================================================


class TestCreativePlanValid:
    def test_minimal(self):
        _assert_valid(
            CreativePlan,
            {
                "plan_id": "plan-001",
                "project_id": "neon-rain",
                "title": "Neon Rain",
                "objective": "60s premiere",
                "brief": "A noir rooftop",
                "duration_seconds": 60,
            },
        )

    def test_with_scenes(self):
        _assert_valid(
            CreativePlan,
            {
                "plan_id": "plan-002",
                "project_id": "neon-rain",
                "title": "T",
                "objective": "O",
                "brief": "B",
                "duration_seconds": 62,
                "scenes": [
                    {"id": "scene-1", "prompt": "rainy skyline", "duration_seconds": 10},
                    {"id": "scene-2", "prompt": "neon sign closeup", "duration_seconds": 15},
                ],
                "shot_list": [
                    {"id": "scene-1", "prompt": "rainy skyline", "duration_seconds": 10},
                ],
                "motifs": ["rain"],
                "locked_assets": [],
                "cover_art": "cover.png",
            },
        )

    def test_with_tracks_and_arc(self):
        _assert_valid(
            CreativePlan,
            {
                "plan_id": "plan-003",
                "project_id": "proj1",
                "title": "T",
                "objective": "O",
                "brief": "B",
                "duration_seconds": 90,
                "arc": ["act 1: intro", "act 2: tension", "act 3: resolve"],
                "tracks": [
                    {"id": "song-1", "prompt": "lofi rain track", "duration_seconds": 60},
                ],
                "voice": {"tone": "warm"},
                "validation_rubric": {"duration_tolerance": 2},
            },
        )


class TestCreativePlanInvalid:
    def test_missing_required(self):
        _assert_invalid(CreativePlan, {"plan_id": "p1"}, "missing required")

    def test_extra_field(self):
        _assert_invalid(
            CreativePlan,
            {
                "plan_id": "p1",
                "project_id": "proj1",
                "title": "t",
                "objective": "o",
                "brief": "b",
                "duration_seconds": 60,
                "unknown_field": 1,
            },
            "unexpected",
        )

    def test_bad_duration(self):
        _assert_invalid(
            CreativePlan,
            {
                "plan_id": "p1",
                "project_id": "proj1",
                "title": "t",
                "objective": "o",
                "brief": "b",
                "duration_seconds": 0,
            },
            "duration_seconds",
        )

    def test_bad_scene_missing_prompt(self):
        _assert_invalid(
            CreativePlan,
            {
                "plan_id": "p1",
                "project_id": "proj1",
                "title": "t",
                "objective": "o",
                "brief": "b",
                "duration_seconds": 60,
                "scenes": [{"id": "scene-1"}],
            },
            "prompt",
        )

    def test_empty_brief(self):
        _assert_invalid(
            CreativePlan,
            {
                "plan_id": "p1",
                "project_id": "proj1",
                "title": "t",
                "objective": "o",
                "brief": "   ",
                "duration_seconds": 60,
            },
            "brief",
        )


# ===========================================================================
# ProjectManifest
# ===========================================================================


class TestProjectManifestValid:
    def test_minimal(self):
        _assert_valid(ProjectManifest, {"project_id": "neon-rain", "plan_id": "plan-001"})

    def test_with_nodes_and_budget(self):
        _assert_valid(
            ProjectManifest,
            {
                "project_id": "neon-rain",
                "plan_id": "plan-001",
                "nodes": [
                    {
                        "id": "song-1",
                        "type": "music",
                        "status": "done",
                        "locked": True,
                        "output_path": "nodes/song-1.wav",
                    },
                    {"id": "scene-1", "type": "video", "status": "pending", "locked": False},
                ],
                "locked_nodes": ["song-1"],
                "budget": {"cap": 1.0, "spent": 0.2, "currency": "USD"},
                "dist_dir": "dist/neon-rain",
                "premiere_path": "dist/neon-rain/premiere.mp4",
                "trace_path": "dist/neon-rain/trace.jsonl",
                "created_at": "2026-08-26T12:00:00Z",
                "version": 1,
            },
        )

    def test_with_nested_plan_and_constitution(self):
        _assert_valid(
            ProjectManifest,
            {
                "project_id": "proj1",
                "plan_id": "plan-001",
                "constitution": {
                    "project_id": "proj1",
                    "title": "T",
                    "brief": "B",
                    "narrative": "N",
                },
                "plan": {
                    "plan_id": "plan-001",
                    "project_id": "proj1",
                    "title": "T",
                    "objective": "O",
                    "brief": "B",
                    "duration_seconds": 60,
                },
            },
        )


class TestProjectManifestInvalid:
    def test_missing_required(self):
        _assert_invalid(ProjectManifest, {"project_id": "proj1"}, "missing required")

    def test_extra_field(self):
        _assert_invalid(
            ProjectManifest, {"project_id": "proj1", "plan_id": "p1", "extra": 1}, "unexpected"
        )

    def test_bad_node_type(self):
        _assert_invalid(
            ProjectManifest,
            {
                "project_id": "proj1",
                "plan_id": "p1",
                "nodes": [{"id": "n1", "type": "unknown_type"}],
            },
            "unknown node type",
        )

    def test_duplicate_node_id(self):
        _assert_invalid(
            ProjectManifest,
            {
                "project_id": "proj1",
                "plan_id": "p1",
                "nodes": [
                    {"id": "dup", "type": "music"},
                    {"id": "dup", "type": "speech"},
                ],
            },
            "duplicate",
        )

    def test_bad_budget(self):
        _assert_invalid(
            ProjectManifest,
            {"project_id": "proj1", "plan_id": "p1", "budget": {"cap": -1}},
            "budget.cap",
        )

    def test_bad_datetime(self):
        _assert_invalid(
            ProjectManifest,
            {"project_id": "proj1", "plan_id": "p1", "created_at": "not-a-date"},
            "ISO-8601",
        )


# ===========================================================================
# PlanDiff
# ===========================================================================


class TestPlanDiffValid:
    def test_minimal(self):
        _assert_valid(
            PlanDiff,
            {
                "from_plan_id": "plan-001",
                "to_plan_id": "plan-002",
                "reason": "change final scene to dawn",
                "affected_nodes": [],
            },
        )

    def test_with_changes(self):
        _assert_valid(
            PlanDiff,
            {
                "from_plan_id": "plan-001",
                "to_plan_id": "plan-002",
                "reason": "revise dawn",
                "affected_nodes": ["scene-3"],
                "changes": [
                    {
                        "op": "replace",
                        "path": "/scenes/2/prompt",
                        "old_value": "night",
                        "new_value": "dawn",
                    },
                ],
                "added": ["scene-3"],
                "removed": [],
                "modified": ["scene-3"],
                "summary": "final scene now dawn",
            },
        )

    def test_with_field_changes(self):
        _assert_valid(
            PlanDiff,
            {
                "from_plan_id": "a",
                "to_plan_id": "b",
                "reason": "lock song",
                "affected_nodes": ["scene-1"],
                "changes": [
                    {
                        "op": "update",
                        "field": "locked_assets",
                        "old_value": [],
                        "new_value": ["song-1"],
                    }
                ],
            },
        )


class TestPlanDiffInvalid:
    def test_missing_required(self):
        _assert_invalid(PlanDiff, {"from_plan_id": "a"}, "missing required")

    def test_extra_field(self):
        _assert_invalid(
            PlanDiff,
            {
                "from_plan_id": "a",
                "to_plan_id": "b",
                "reason": "r",
                "affected_nodes": [],
                "extra": 1,
            },
            "unexpected",
        )

    def test_bad_op(self):
        _assert_invalid(
            PlanDiff,
            {
                "from_plan_id": "a",
                "to_plan_id": "b",
                "reason": "r",
                "affected_nodes": [],
                "changes": [{"op": "bad_op", "path": "/x"}],
            },
            "op: must be",
        )

    def test_empty_reason(self):
        _assert_invalid(
            PlanDiff,
            {"from_plan_id": "a", "to_plan_id": "b", "reason": "   ", "affected_nodes": []},
            "reason",
        )

    def test_bad_affected_nodes(self):
        _assert_invalid(
            PlanDiff,
            {"from_plan_id": "a", "to_plan_id": "b", "reason": "r", "affected_nodes": "not-a-list"},
            "affected_nodes",
        )

    def test_change_missing_path_and_field(self):
        _assert_invalid(
            PlanDiff,
            {
                "from_plan_id": "a",
                "to_plan_id": "b",
                "reason": "r",
                "affected_nodes": [],
                "changes": [{"op": "add"}],
            },
            "must have",
        )


# ===========================================================================
# GMI-free import check (acceptance criterion)
# ===========================================================================


class TestGmiFreeImport:
    def test_import_without_gmi_deps(self):
        # schemas must not import keyring/httpx; verify by checking for import statements
        import pathlib
        import re

        src = (
            pathlib.Path(__file__).resolve().parent.parent / "music_cli" / "studio" / "schemas.py"
        ).read_text()
        assert not re.search(r"^\s*import\s+keyring", src, re.MULTILINE)
        assert not re.search(r"^\s*from\s+keyring", src, re.MULTILINE)
        assert not re.search(r"^\s*import\s+httpx", src, re.MULTILINE)
        assert not re.search(r"^\s*from\s+httpx", src, re.MULTILINE)
        # direct import check already done at top; if we are here, import succeeded
        assert Constitution is not None
        assert CreativePlan is not None
        assert ProjectManifest is not None
        assert PlanDiff is not None

    def test_validate_returns_list(self):
        for cls in (Constitution, CreativePlan, ProjectManifest, PlanDiff):
            result = cls.validate({})
            assert isinstance(result, list)
            assert all(isinstance(e, str) for e in result)
