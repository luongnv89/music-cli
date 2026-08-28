"""Tests for the studio dependency graph (issue #142, task P5.1).

Covers:

- ``Node`` lock/unlock lifecycle
- ``ProjectGraph`` construction from a ``CreativePlan``
- Dependency validation (missing refs, cycles)
- Deterministic topological ordering
- Lock enforcement on ``generate()``
- Manifest persistence and re-hydration of lock state
"""

from __future__ import annotations

import pytest

from music_cli.studio.graph import (
    GraphCycleError,
    GraphError,
    GraphMissingDependency,
    Node,
    NodeLockedError,
    ProjectGraph,
)
from music_cli.studio.schemas import CreativePlan


# ---------------------------------------------------------------------------
# Node tests
# ---------------------------------------------------------------------------


class TestNode:
    """Tests for the ``Node`` dataclass."""

    def test_node_creation(self) -> None:
        node = Node(id="music-1", node_type="music", prompt="test prompt")
        assert node.id == "music-1"
        assert node.node_type == "music"
        assert node.prompt == "test prompt"
        assert node.depends_on == []
        assert node.output_path is None
        assert not node.locked
        assert node.lock_reason == ""

    def test_node_lock_unlock(self) -> None:
        node = Node(id="music-1", node_type="music")
        assert not node.locked
        node.lock()
        assert node.locked
        node.unlock("revising lyrics")
        assert not node.locked
        assert node.lock_reason == "revising lyrics"

    def test_node_unlock_requires_reason(self) -> None:
        node = Node(id="music-1", node_type="music")
        node.lock()
        with pytest.raises(ValueError, match="non-empty reason"):
            node.unlock("")
        with pytest.raises(ValueError, match="non-empty reason"):
            node.unlock("   ")

    def test_node_generate(self) -> None:
        node = Node(id="music-1", node_type="music")
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            node.output_path = str(Path(tmpdir) / "output.wav")
            result = node.generate()
            assert result.exists()
            assert node.locked
            assert node.output_path == str(Path(tmpdir) / "output.wav")

    def test_node_generate_locked_raises(self) -> None:
        node = Node(id="music-1", node_type="music")
        node.lock()
        with pytest.raises(NodeLockedError, match="locked"):
            node.generate()

    def test_node_to_dict_roundtrip(self) -> None:
        node = Node(
            id="music-1",
            node_type="music",
            prompt="test",
            depends_on=["speech-1"],
            output_path="/tmp/out.wav",
            locked=True,
            lock_reason="revised",
        )
        data = node.to_dict()
        restored = Node.from_dict(data)
        assert restored.id == node.id
        assert restored.node_type == node.node_type
        assert restored.prompt == node.prompt
        assert restored.depends_on == node.depends_on
        assert restored.output_path == node.output_path
        assert restored.locked == node.locked
        assert restored.lock_reason == node.lock_reason

    def test_node_default_output_path(self) -> None:
        node = Node(id="music-1", node_type="music")
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            import os
            os.chdir(tmpdir)
            result = node.generate()
            assert result.exists()
            assert "music-1" in str(result)


# ---------------------------------------------------------------------------
# ProjectGraph — construction from CreativePlan
# ---------------------------------------------------------------------------


class TestProjectGraphFromPlan:
    """Tests for ``ProjectGraph.from_plan``."""

    def _make_plan(self, **overrides: object) -> CreativePlan:
        """Build a minimal CreativePlan dict and validate it."""
        data = {
            "plan_id": "test-plan-1",
            "project_id": "test-project",
            "title": "Test Plan",
            "objective": "Test objective",
            "brief": "Test brief",
            "duration_seconds": 60,
            "tracks": [
                {"id": "t1", "prompt": "synthwave track", "lyrics": "la la"},
                {"id": "t2", "prompt": "ambient pad", "lyrics": "mmm"},
            ],
            "scenes": [
                {
                    "id": "s1",
                    "prompt": "neon city",
                    "description": "neon city narration",
                    "duration_seconds": 30,
                },
                {
                    "id": "s2",
                    "prompt": "rain street",
                    "description": "rain narration",
                    "duration_seconds": 30,
                },
            ],
        }
        data.update(overrides)
        return CreativePlan(data)

    def test_graph_from_plan_has_music_nodes(self) -> None:
        plan = self._make_plan()
        graph = ProjectGraph.from_plan(plan)
        assert "music-1" in graph.nodes
        assert "music-2" in graph.nodes
        assert graph.nodes["music-1"].node_type == "music"
        assert graph.nodes["music-2"].node_type == "music"

    def test_graph_from_plan_has_speech_nodes(self) -> None:
        plan = self._make_plan()
        graph = ProjectGraph.from_plan(plan)
        assert "speech-1" in graph.nodes
        assert "speech-2" in graph.nodes
        assert graph.nodes["speech-1"].node_type == "speech"
        assert graph.nodes["speech-2"].node_type == "speech"

    def test_graph_from_plan_has_video_nodes(self) -> None:
        plan = self._make_plan()
        graph = ProjectGraph.from_plan(plan)
        assert "scene-1" in graph.nodes
        assert "scene-2" in graph.nodes
        assert graph.nodes["scene-1"].node_type == "video"
        assert graph.nodes["scene-2"].node_type == "video"

    def test_graph_from_plan_has_mix_node(self) -> None:
        plan = self._make_plan()
        graph = ProjectGraph.from_plan(plan)
        assert "mix" in graph.nodes
        assert graph.nodes["mix"].node_type == "mix"
        # Mix depends on all music nodes
        deps = graph.get_dependencies("mix")
        assert "music-1" in deps
        assert "music-2" in deps
        # Speech nodes are independent (not mixed)
        assert "speech-1" not in deps
        assert "speech-2" not in deps

    def test_graph_from_plan_has_assemble_node(self) -> None:
        plan = self._make_plan()
        graph = ProjectGraph.from_plan(plan)
        assert "assemble" in graph.nodes
        assert graph.nodes["assemble"].node_type == "assemble"
        deps = graph.get_dependencies("assemble")
        assert "scene-1" in deps
        assert "scene-2" in deps
        assert "mix" in deps

    def test_graph_from_plan_no_video_no_assemble(self) -> None:
        """When there are no scenes/shot_list, no assemble node is created."""
        plan = self._make_plan(scenes=[], shot_list=[])
        graph = ProjectGraph.from_plan(plan)
        assert "assemble" not in graph.nodes
        # Mix should still exist (depends on music nodes)
        assert "mix" in graph.nodes

    def test_graph_from_plan_no_tracks_no_mix(self) -> None:
        """When there are no tracks, no mix node is created."""
        plan = self._make_plan(tracks=[])
        graph = ProjectGraph.from_plan(plan)
        assert "mix" not in graph.nodes
        # assemble still exists because video nodes exist
        assert "assemble" in graph.nodes


# ---------------------------------------------------------------------------
# Dependency validation
# ---------------------------------------------------------------------------


class TestGraphValidation:
    """Tests for graph validation (missing deps, cycles)."""

    def test_validate_no_errors_valid_graph(self) -> None:
        plan_data = {
            "plan_id": "p1",
            "project_id": "proj",
            "title": "T",
            "objective": "O",
            "brief": "B",
            "duration_seconds": 60,
            "tracks": [{"prompt": "a"}],
        }
        plan = CreativePlan(plan_data)
        graph = ProjectGraph.from_plan(plan)
        errors = graph.validate()
        assert errors == []

    def test_validate_missing_dependency(self) -> None:
        graph = ProjectGraph()
        node = Node(id="a", node_type="music", depends_on=["nonexistent"])
        graph.nodes["a"] = node
        graph._edges["a"] = {"nonexistent"}
        errors = graph.validate()
        assert any("nonexistent" in e for e in errors)

    def test_validate_duplicate_ids(self) -> None:
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music")
        graph.nodes["a"] = Node(id="a", node_type="speech")  # overwrite
        # After overwrite, there's only one entry, so no duplicate.
        # To test duplicate, we need two different keys with same id.
        # Since dict keys are unique, we test differently.
        errors = graph.validate()
        assert errors == []  # dict deduplicates

    def test_validate_cycle(self) -> None:
        """Nodes A → B → C → A form a cycle."""
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music", depends_on=["b"])
        graph.nodes["b"] = Node(id="b", node_type="speech", depends_on=["c"])
        graph.nodes["c"] = Node(id="c", node_type="video", depends_on=["a"])
        graph._edges["a"] = {"b"}
        graph._edges["b"] = {"c"}
        graph._edges["c"] = {"a"}
        errors = graph.validate()
        assert any("cycle" in e.lower() for e in errors)

    def test_validate_self_cycle(self) -> None:
        """A node depending on itself is a cycle."""
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music", depends_on=["a"])
        graph._edges["a"] = {"a"}
        errors = graph.validate()
        assert any("cycle" in e.lower() for e in errors)

    def test_topological_order_raises_on_cycle(self) -> None:
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music", depends_on=["b"])
        graph.nodes["b"] = Node(id="b", node_type="speech", depends_on=["a"])
        graph._edges["a"] = {"b"}
        graph._edges["b"] = {"a"}
        with pytest.raises(GraphCycleError):
            graph.topological_order()


# ---------------------------------------------------------------------------
# Topological ordering
# ---------------------------------------------------------------------------


class TestTopologicalOrder:
    """Tests for deterministic topological ordering."""

    def test_simple_linear_order(self) -> None:
        """A → B → C should yield [A, B, C]."""
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music")
        graph.nodes["b"] = Node(id="b", node_type="speech", depends_on=["a"])
        graph.nodes["c"] = Node(id="c", node_type="video", depends_on=["b"])
        graph._edges["a"] = set()
        graph._edges["b"] = {"a"}
        graph._edges["c"] = {"b"}
        order = graph.topological_order()
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")

    def test_deterministic_within_wave(self) -> None:
        """Two independent nodes should always appear in id order."""
        graph = ProjectGraph()
        graph.nodes["b"] = Node(id="b", node_type="music")
        graph.nodes["a"] = Node(id="a", node_type="speech")
        graph.nodes["c"] = Node(id="c", node_type="video", depends_on=["a", "b"])
        graph._edges["a"] = set()
        graph._edges["b"] = set()
        graph._edges["c"] = {"a", "b"}
        order = graph.topological_order()
        # a and b are in the same wave, should be sorted by id
        assert order[0] == "a"
        assert order[1] == "b"
        assert order[2] == "c"

    def test_topo_order_from_plan(self) -> None:
        """Topo order respects plan dependencies."""
        plan_data = {
            "plan_id": "p1",
            "project_id": "proj",
            "title": "T",
            "objective": "O",
            "brief": "B",
            "duration_seconds": 60,
            "tracks": [{"prompt": "a"}],
            "scenes": [
                {"id": "s1", "prompt": "v1", "description": "n1", "duration_seconds": 30},
            ],
        }
        plan = CreativePlan(plan_data)
        graph = ProjectGraph.from_plan(plan)
        order = graph.topological_order()

        # music-1 should come before mix
        mix_idx = order.index("mix")
        assert order.index("music-1") < mix_idx

        # mix should come before assemble
        assemble_idx = order.index("assemble")
        assert mix_idx < assemble_idx

    def test_all_nodes_present_in_order(self) -> None:
        plan_data = {
            "plan_id": "p1",
            "project_id": "proj",
            "title": "T",
            "objective": "O",
            "brief": "B",
            "duration_seconds": 60,
            "tracks": [{"prompt": "a"}],
            "scenes": [
                {"id": "s1", "prompt": "v1", "description": "n1", "duration_seconds": 30},
                {"id": "s2", "prompt": "v2", "description": "n2", "duration_seconds": 30},
            ],
        }
        plan = CreativePlan(plan_data)
        graph = ProjectGraph.from_plan(plan)
        order = graph.topological_order()
        assert set(order) == set(graph.nodes)


# ---------------------------------------------------------------------------
# Lock enforcement
# ---------------------------------------------------------------------------


class TestLockEnforcement:
    """Tests for lock enforcement on nodes and the graph."""

    def test_graph_lock_node(self) -> None:
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music")
        graph.lock_node("a")
        assert graph.is_locked("a")

    def test_graph_unlock_node(self) -> None:
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music")
        graph.lock_node("a")
        graph.unlock_node("a", reason="needs regen")
        assert not graph.is_locked("a")

    def test_graph_unlock_requires_reason(self) -> None:
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music")
        graph.lock_node("a")
        with pytest.raises(ValueError, match="non-empty reason"):
            graph.unlock_node("a", reason="")

    def test_graph_unknown_node_raises(self) -> None:
        graph = ProjectGraph()
        with pytest.raises(KeyError):
            graph.lock_node("nonexistent")
        with pytest.raises(KeyError):
            graph.unlock_node("nonexistent", reason="test")
        with pytest.raises(KeyError):
            graph.is_locked("nonexistent")

    def test_node_generate_blocked_when_locked(self) -> None:
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music")
        graph.lock_node("a")
        with pytest.raises(NodeLockedError):
            graph.nodes["a"].generate()

    def test_node_generate_succeeds_when_unlocked(self) -> None:
        import tempfile
        from pathlib import Path

        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music")
        with tempfile.TemporaryDirectory() as tmpdir:
            graph.nodes["a"].output_path = str(Path(tmpdir) / "out.wav")
            result = graph.nodes["a"].generate()
            assert result.exists()
            assert graph.is_locked("a")


# ---------------------------------------------------------------------------
# Manifest persistence
# ---------------------------------------------------------------------------


class TestManifestPersistence:
    """Tests for lock state persistence to/from manifest."""

    def test_persist_locks(self) -> None:
        manifest: dict[str, object] = {
            "project_id": "test",
            "plan_id": "p1",
            "nodes": [
                {"id": "a", "type": "music", "locked": False},
                {"id": "b", "type": "speech", "locked": False},
            ],
        }
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music")
        graph.nodes["b"] = Node(id="b", node_type="speech")
        graph.lock_node("a")

        updated = graph.persist_locks(manifest)
        assert "a" in updated["locked_nodes"]
        assert "b" not in updated["locked_nodes"]
        # Check per-node state
        for n in updated["nodes"]:
            if n["id"] == "a":
                assert n["locked"] is True
            elif n["id"] == "b":
                assert n["locked"] is False

    def test_load_locks_from_manifest(self) -> None:
        manifest: dict[str, object] = {
            "project_id": "test",
            "plan_id": "p1",
            "locked_nodes": ["a"],
            "nodes": [
                {"id": "a", "type": "music", "locked": True},
                {"id": "b", "type": "speech", "locked": False},
            ],
        }
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music")
        graph.nodes["b"] = Node(id="b", node_type="speech")
        graph.load_locks(manifest)
        assert graph.is_locked("a")
        assert not graph.is_locked("b")

    def test_load_locks_empty_manifest(self) -> None:
        manifest: dict[str, object] = {
            "project_id": "test",
            "plan_id": "p1",
            "nodes": [],
        }
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music")
        graph.lock_node("a")
        graph.load_locks(manifest)
        assert not graph.is_locked("a")

    def test_from_manifest_rehydrates_locks(self) -> None:
        manifest = {
            "project_id": "test",
            "plan_id": "p1",
            "locked_nodes": ["music-1"],
            "nodes": [
                {"id": "music-1", "type": "music", "locked": True},
                {"id": "speech-1", "type": "speech", "locked": False},
            ],
        }
        graph = ProjectGraph.from_manifest(manifest)
        assert graph.is_locked("music-1")
        assert not graph.is_locked("speech-1")


# ---------------------------------------------------------------------------
# Edge management
# ---------------------------------------------------------------------------


class TestEdgeManagement:
    """Tests for adding and querying edges."""

    def test_add_edge(self) -> None:
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music")
        graph.nodes["b"] = Node(id="b", node_type="speech")
        graph.add_edge("b", "a")
        assert "a" in graph.get_dependencies("b")

    def test_add_edge_unknown_node(self) -> None:
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music")
        with pytest.raises(KeyError):
            graph.add_edge("a", "nonexistent")
        with pytest.raises(KeyError):
            graph.add_edge("nonexistent", "a")

    def test_get_dependents(self) -> None:
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music")
        graph.nodes["b"] = Node(id="b", node_type="speech", depends_on=["a"])
        graph._edges["a"] = set()
        graph._edges["b"] = {"a"}
        dependents = graph.get_dependents("a")
        assert "b" in dependents
        assert len(dependents) == 1

    def test_get_dependencies(self) -> None:
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music")
        graph.nodes["b"] = Node(id="b", node_type="speech", depends_on=["a"])
        graph._edges["a"] = set()
        graph._edges["b"] = {"a"}
        deps = graph.get_dependencies("b")
        assert deps == {"a"}


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    """Tests for graph serialization and deserialization."""

    def test_to_dict_from_dict_roundtrip(self) -> None:
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music", depends_on=[])
        graph.nodes["b"] = Node(id="b", node_type="speech", depends_on=["a"])
        graph._edges["a"] = set()
        graph._edges["b"] = {"a"}

        data = graph.to_dict()
        restored = ProjectGraph.from_dict(data)

        assert set(restored.nodes) == {"a", "b"}
        assert "a" in restored.get_dependencies("b")

    def test_graph_serialization_preserves_lock_state(self) -> None:
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music")
        graph.lock_node("a")
        data = graph.to_dict()
        restored = ProjectGraph.from_dict(data)
        assert restored.is_locked("a")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_graph(self) -> None:
        graph = ProjectGraph()
        assert graph.validate() == []
        assert graph.topological_order() == []

    def test_single_node_graph(self) -> None:
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music")
        graph._edges["a"] = set()
        assert graph.validate() == []
        assert graph.topological_order() == ["a"]

    def test_graph_from_plan_empty_tracks_and_scenes(self) -> None:
        plan = CreativePlan({
            "plan_id": "p1",
            "project_id": "proj",
            "title": "T",
            "objective": "O",
            "brief": "B",
            "duration_seconds": 60,
            "tracks": [],
            "scenes": [],
        })
        graph = ProjectGraph.from_plan(plan)
        assert len(graph.nodes) == 0
        assert graph.validate() == []
        assert graph.topological_order() == []

    def test_graph_validate_returns_all_errors(self) -> None:
        """Multiple errors should all be reported."""
        graph = ProjectGraph()
        graph.nodes["a"] = Node(id="a", node_type="music", depends_on=["x", "y"])
        graph._edges["a"] = {"x", "y"}
        errors = graph.validate()
        missing_errors = [e for e in errors if "unknown" in e.lower()]
        assert len(missing_errors) == 2  # both x and y
