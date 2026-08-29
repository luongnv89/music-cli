"""Tests for music_cli.studio.director — P2.1 (#135).

A scripted fake adapter replays canned M3 replies (valid JSON, fenced
JSON, invalid output) so the retry/tracing behavior is exercised with no
network and no GMI deps.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from music_cli.studio.director import (
    MAX_PARSE_RETRIES,
    CritiqueReport,
    DirectorError,
    M3Director,
    extract_json,
)
from music_cli.studio.schemas import CreativePlan, PlanDiff

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
    "affected_nodes": ["node-1", "node-3"],
    "locked_nodes": ["node-2"],
    "regenerate_nodes": ["node-1", "node-3"],
}

VALID_CRITIQUE = {
    "ok": False,
    "issues": ["track 2 duration off by 3s"],
    "repairs": ["re-render track 2 at 27s"],
}


class FakeAdapter:
    """Replays scripted replies from async m3_plan/m3_critique methods."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.plan_prompts: list[str] = []
        self.critique_prompts: list[str] = []

    async def m3_plan(self, prompt: str, **_: object) -> dict[str, str]:
        self.plan_prompts.append(prompt)
        return {"text": self.replies[len(self.plan_prompts) - 1]}

    async def m3_critique(self, prompt: str, **_: object) -> dict[str, str]:
        self.critique_prompts.append(prompt)
        return {"text": self.replies[len(self.critique_prompts) - 1]}


def _director(*replies: str, tmp_path: Path) -> tuple[M3Director, FakeAdapter]:
    adapter = FakeAdapter(*replies)
    director = M3Director(adapter, trace_path=tmp_path / "trace.jsonl")
    return director, adapter


# ===========================================================================
# plan
# ===========================================================================


class TestPlan:
    async def test_returns_validated_creative_plan(self, tmp_path):
        director, adapter = _director(json.dumps(VALID_PLAN), tmp_path=tmp_path)
        plan = await director.plan("A noir rooftop chase")
        assert isinstance(plan, CreativePlan)
        assert plan.validate() == []
        assert plan.to_dict()["title"] == "Neon Rain"
        assert len(adapter.plan_prompts) == 1

    async def test_tolerates_markdown_fences(self, tmp_path):
        fenced = f"Here you go:\n```json\n{json.dumps(VALID_PLAN)}\n```"
        director, _ = _director(fenced, tmp_path=tmp_path)
        plan = await director.plan("brief")
        assert plan.to_dict()["plan_id"] == "plan-001"

    async def test_retries_on_invalid_json_with_corrective_prompt(self, tmp_path):
        bad = "not json at all"
        director, adapter = _director(bad, json.dumps(VALID_PLAN), tmp_path=tmp_path)
        plan = await director.plan("brief")
        assert plan.to_dict()["project_id"] == "neon-rain"
        assert len(adapter.plan_prompts) == 2
        corrective = adapter.plan_prompts[1]
        assert "Re-output the exact JSON" in corrective
        assert bad in corrective  # previous reply is embedded

    async def test_retries_on_schema_validation_failure(self, tmp_path):
        """Retries when model returns invalid JSON structure."""
        bad = json.dumps({"not": "valid"})  # Missing required fields
        director, adapter = _director(bad, json.dumps(VALID_PLAN), tmp_path=tmp_path)
        plan = await director.plan("brief")
        assert plan.validate() == []
        # Should have retried because first reply was invalid
        assert len(adapter.plan_prompts) >= 2

    async def test_raises_after_initial_plus_two_retries(self, tmp_path):
        director, adapter = _director("nope", "still nope", "nope again", tmp_path=tmp_path)
        with pytest.raises(DirectorError) as excinfo:
            await director.plan("brief")
        assert "3 attempts" in str(excinfo.value)
        assert len(adapter.plan_prompts) == 1 + MAX_PARSE_RETRIES


# ===========================================================================
# critique
# ===========================================================================


class TestCritique:
    async def test_returns_report_with_ok_issues_repairs(self, tmp_path):
        director, adapter = _director(json.dumps(VALID_CRITIQUE), tmp_path=tmp_path)
        report = await director.critique(VALID_PLAN, {"duration": 63.2})
        assert isinstance(report, CritiqueReport)
        assert report.ok is False
        assert report.issues and report.repairs
        assert len(adapter.critique_prompts) == 1
        prompt = adapter.critique_prompts[0]
        assert "Neon Rain" in prompt and "63.2" in prompt

    async def test_missing_issue_lists_default_to_empty(self, tmp_path):
        director, _ = _director(json.dumps({"ok": True, "summary": "clean"}), tmp_path=tmp_path)
        report = await director.critique(VALID_PLAN, {})
        assert report.ok is True
        assert report.issues == [] and report.repairs == []

    async def test_retries_on_invalid_critique(self, tmp_path):
        director, adapter = _director(
            '{"ok": "yes"}', json.dumps(VALID_CRITIQUE), tmp_path=tmp_path
        )
        report = await director.critique(VALID_PLAN, {})
        assert report.ok is False
        assert "ok" in adapter.critique_prompts[1]

    def test_critique_report_validation(self):
        assert CritiqueReport.validate(VALID_CRITIQUE) == []
        errs = CritiqueReport.validate({"ok": "yes"})
        assert any("ok" in e for e in errs)
        with pytest.raises(ValueError):
            CritiqueReport.model_validate({"ok": "yes", "unexpected": 1})


# ===========================================================================
# revise
# ===========================================================================


class TestRevise:
    async def test_returns_plan_diff_with_locked_and_regenerate(self, tmp_path):
        director, _ = _director(json.dumps(VALID_DIFF), tmp_path=tmp_path)
        diff = await director.revise(VALID_PLAN, "swap rain motif for thunder")
        assert isinstance(diff, PlanDiff)
        assert diff.validate() == []
        data = diff.to_dict()
        assert data["locked_nodes"] == ["node-2"]
        assert data["regenerate_nodes"] == ["node-1", "node-3"]

    async def test_retries_then_succeeds(self, tmp_path):
        bad = json.dumps({"from_plan_id": "a"})  # missing required fields
        director, adapter = _director(bad, json.dumps(VALID_DIFF), tmp_path=tmp_path)
        diff = await director.revise(VALID_PLAN, "tighten the middle")
        assert diff.validate() == []
        assert "Re-output the exact JSON" in adapter.plan_prompts[1]

    async def test_plan_diff_schema_accepts_locked_and_regenerate(self):
        assert PlanDiff.validate(VALID_DIFF) == []
        bad = {**VALID_DIFF, "locked_nodes": [42]}
        assert any("locked_nodes[0]" in e for e in PlanDiff.validate(bad))


# ===========================================================================
# trace
# ===========================================================================


class TestTrace:
    async def test_every_call_appends_required_fields(self, tmp_path):
        trace = tmp_path / "nested" / "trace.jsonl"
        director = M3Director(FakeAdapter(json.dumps(VALID_PLAN)), trace_path=trace)
        await director.plan("brief")
        lines = [json.loads(line) for line in trace.read_text().splitlines()]
        assert len(lines) == 1
        rec = lines[0]
        for field in ("step", "model", "ts", "input_hash", "output_hash", "latency_ms"):
            assert field in rec, f"missing {field}"
        assert rec["step"] == "plan"
        assert rec["model"] == "MiniMax-M3"
        assert rec["retries"] == 0
        assert rec["ok"] is True

    async def test_retry_count_and_hash_recorded(self, tmp_path):
        trace = tmp_path / "trace.jsonl"
        director, _ = _director("garbage", json.dumps(VALID_PLAN), tmp_path=tmp_path)
        await director.plan("brief")
        recs = [json.loads(line) for line in trace.read_text().splitlines()]
        assert recs[-1]["retries"] == 1
        assert recs[-1]["input_hash"] != recs[-1]["output_hash"]

    async def test_trace_disabled_with_none(self, tmp_path):
        director = M3Director(FakeAdapter(json.dumps(VALID_PLAN)), trace_path=None)
        await director.plan("brief")
        assert list(tmp_path.iterdir()) == []

    async def test_failed_call_traced_with_ok_false(self, tmp_path):
        trace = tmp_path / "trace.jsonl"
        director, _ = _director("x", "y", "z", tmp_path=tmp_path)
        with pytest.raises(DirectorError):
            await director.plan("brief")
        recs = [json.loads(line) for line in trace.read_text().splitlines()]
        assert recs[0]["ok"] is False
        assert recs[0]["retries"] == MAX_PARSE_RETRIES


# ===========================================================================
# extract_json
# ===========================================================================


class TestExtractJson:
    def test_plain_object(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_fenced_with_prose(self):
        assert extract_json('Sure!\n```json\n{"a": [1]}\n```\ndone') == {"a": [1]}

    def test_nested_braces(self):
        assert extract_json('x {"a": {"b": 2}} y') == {"a": {"b": 2}}

    def test_no_object_raises(self):
        with pytest.raises(ValueError):
            extract_json("[] just an array")
        with pytest.raises(ValueError):
            extract_json("no json here")

    def test_non_text_raises(self):
        with pytest.raises(ValueError):
            extract_json(None)  # type: ignore[arg-type]
