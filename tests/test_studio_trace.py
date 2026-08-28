"""Tests for music_cli.studio.trace — the per-project decision log (#136).

Covers the append-only :class:`TraceWriter`, the ``dist/<project>/`` layout,
the plan.yaml round-trip, the table renderer, and the two ``mc studio`` CLI
commands (``plan`` / ``trace``).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from music_cli.cli import main
from music_cli.studio.trace import (
    NODES_DIRNAME,
    PLAN_FILENAME,
    PREMIERE_FILENAME,
    TRACE_FILENAME,
    TraceWriter,
    dump_plan_yaml,
    init_project_layout,
    load_plan_yaml,
    load_trace,
    project_dir,
    project_paths,
    render_trace_table,
    write_plan_yaml,
)

REQUIRED_FIELDS = ("ts", "step", "model", "node_id", "latency_ms", "payload_hash")


# ===========================================================================
# TraceWriter
# ===========================================================================


class TestTraceWriter:
    def test_context_manager_append_only(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        with TraceWriter(path) as trace:
            trace.append(step="plan", payload='{"title": "Neon Rain"}')
        # second write in a fresh handle still appends, never truncates
        with TraceWriter(path) as trace:
            trace.append(step="generate", node_id="scene-1")
        lines = path.read_text().splitlines()
        assert len(lines) == 2
        recs = [json.loads(line) for line in lines]
        assert recs[0]["step"] == "plan"
        assert recs[1]["step"] == "generate"

    def test_every_line_has_required_fields(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        with TraceWriter(path) as trace:
            trace.append(step="plan", node_id="root", latency_ms=12.5, payload="x")
            trace.append(step="assemble", node_id="mix-1", latency_ms=3.0)
        for line in path.read_text().splitlines():
            rec = json.loads(line)
            for field in REQUIRED_FIELDS:
                assert field in rec, f"missing {field}"

    def test_standalone_write_works_without_context(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        writer = TraceWriter(path)
        writer.append(step="probe", node_id="scene-2")
        writer.append(step="probe", node_id="scene-3")
        assert len(load_trace(path)) == 2

    def test_payload_hash_defaults_to_sha256_of_payload(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        writer = TraceWriter(path)
        writer.append(step="plan", payload='{"a": 1}')
        rec = load_trace(path)[0]
        expected = hashlib.sha256(b'{"a": 1}').hexdigest()
        assert rec["payload_hash"] == expected

    def test_extra_fields_pass_through(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        with TraceWriter(path) as trace:
            trace.append(step="plan", payload="x", ok=False, retries=2)
        rec = load_trace(path)[0]
        assert rec["ok"] is False
        assert rec["retries"] == 2

    def test_normalizes_none_node_id_and_latency_to_null_in_json(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        with TraceWriter(path) as trace:
            trace.append(step="plan", payload="x")
        text = path.read_text()
        # the keys exist even when the value is null
        assert '"node_id": null' in text
        assert '"latency_ms": null' in text


# ===========================================================================
# project layout
# ===========================================================================


class TestProjectLayout:
    def test_project_dir_is_dist_slash_project(self, tmp_path):
        assert project_dir("dist", "neon-rain") == Path("dist") / "neon-rain"

    def test_init_layout_matches_spec(self, tmp_path):
        proj = init_project_layout(tmp_path / "dist", "neon-rain")
        paths = project_paths(proj)
        assert proj.is_dir()
        assert (proj / NODES_DIRNAME).is_dir()
        assert paths[TRACE_FILENAME].exists()  # empty trace.jsonl created
        # plan.yaml and premiere.mp4 appear only after the build fills them
        for name in (PLAN_FILENAME, PREMIERE_FILENAME):
            assert (proj / name).exists() is False

    def test_layout_after_plan_written(self, tmp_path):
        proj = init_project_layout(tmp_path / "dist", "neon-rain")
        write_plan_yaml(proj / PLAN_FILENAME, {"title": "Neon Rain", "duration_seconds": 60})
        (proj / PREMIERE_FILENAME).write_bytes(b"MP4")
        paths = project_paths(proj)
        for name in (PLAN_FILENAME, TRACE_FILENAME, NODES_DIRNAME, PREMIERE_FILENAME):
            assert paths[name].exists(), f"missing {name}"


# ===========================================================================
# plan.yaml round trip
# ===========================================================================


class TestPlanYaml:
    def test_scalar_dump(self):
        text = dump_plan_yaml({"plan_id": "plan-001", "title": "Neon Rain", "duration_seconds": 60})
        assert "plan_id: plan-001" in text
        assert "duration_seconds: 60" in text

    def test_full_dump_load_round_trip(self, tmp_path):
        plan = {
            "project_id": "neon-rain",
            "title": "Neon Rain",
            "objective": "Ship a 60s premiere",
            "brief": "A noir rooftop chase",
            "duration_seconds": 60,
            "arc": ["intro", "build", "climax"],
            "scenes": [
                {"id": "scene-1", "label": "Rooftop"},
                {"id": "scene-2", "label": "Rain"},
            ],
            "locked_assets": [],
        }
        path = tmp_path / "plan.yaml"
        write_plan_yaml(path, plan)
        loaded = load_plan_yaml(path)
        assert loaded["title"] == "Neon Rain"
        assert loaded["duration_seconds"] == 60
        assert loaded["arc"] == ["intro", "build", "climax"]
        assert loaded["scenes"] == [
            {"id": "scene-1", "label": "Rooftop"},
            {"id": "scene-2", "label": "Rain"},
        ]
        assert loaded["locked_assets"] == []


# ===========================================================================
# trace reading / table rendering
# ===========================================================================


class TestTraceRendering:
    def test_load_trace_returns_records(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        path.write_text(
            '{"ts": "2026-01-01T00:00:00+00:00", "step": "plan"}\n'
            "\n"
            '{"ts": "2026-01-01T00:00:01+00:00", "step": "generate"}\n'
        )
        assert [r["step"] for r in load_trace(path)] == ["plan", "generate"]

    def test_load_trace_rejects_bad_line(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        path.write_text("not json\n")
        with pytest.raises(ValueError, match="trace.jsonl line 1"):
            load_trace(path)

    def test_render_table_contains_headers_and_row(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        with TraceWriter(path) as trace:
            trace.append(step="plan", node_id="root", latency_ms=10.0, payload="x")
        table = render_trace_table(load_trace(path))
        assert "step" in table
        assert "payload_hash" in table
        assert "plan" in table
        assert "root" in table


# ===========================================================================
# mc studio CLI
# ===========================================================================


class TestStudioCli:
    def _build_project(self, tmp_path, name="neon-rain"):
        proj = init_project_layout(tmp_path / "dist", name)
        write_plan_yaml(proj / PLAN_FILENAME, {"title": "Neon Rain", "duration_seconds": 60})
        with TraceWriter(proj / TRACE_FILENAME) as trace:
            trace.append(step="plan", node_id="root", latency_ms=8.0, payload="{}")
        return proj

    def test_plan_pretty_prints(self, tmp_path):
        self._build_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            main, ["studio", "plan", "neon-rain", "--dist-dir", str(tmp_path / "dist")]
        )
        assert result.exit_code == 0, result.output
        assert "Neon Rain" in result.output
        assert "duration_seconds: 60" in result.output

    def test_plan_missing_project_errors(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            main, ["studio", "plan", "missing", "--dist-dir", str(tmp_path / "dist")]
        )
        assert result.exit_code != 0
        assert "no build project 'missing'" in result.output

    def test_plan_missing_plan_file_errors(self, tmp_path):
        init_project_layout(tmp_path / "dist", "empty-proj")
        runner = CliRunner()
        result = runner.invoke(
            main, ["studio", "plan", "empty-proj", "--dist-dir", str(tmp_path / "dist")]
        )
        assert result.exit_code != 0
        assert "no plan at" in result.output

    def test_trace_renders_table(self, tmp_path):
        self._build_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            main, ["studio", "trace", "neon-rain", "--dist-dir", str(tmp_path / "dist")]
        )
        assert result.exit_code == 0, result.output
        assert "step" in result.output
        assert "plan" in result.output
        assert "payload_hash" in result.output
