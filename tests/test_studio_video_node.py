"""Tests for the H3-backed studio VideoNode (P4.1, issue #140).

All provider, download, ffmpeg, and ffprobe boundaries are injected.  The
suite therefore exercises H3 accounting and the NO-GO static visual path
without making a live request or depending on media binaries.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner

from music_cli.cli import main
from music_cli.studio import BudgetExceeded, BuildBudget, ProjectManifest, VideoNode
from music_cli.studio.nodes import VideoNode as NodesVideoNode
from music_cli.studio.nodes.base import NodeError, NodeLockedError
from music_cli.studio.nodes.video import DEFAULT_BUILD_CAP, _video_url
from music_cli.studio.trace import NODES_DIRNAME


class FakeH3Adapter:
    """Return deterministic media URLs and retain every H3 call."""

    def __init__(self, *results: Any) -> None:
        self.results = list(results) or [{"video_url": "memory://scene.mp4"}]
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def h3_generate(self, prompt: str, **params: Any) -> Any:
        self.calls.append((prompt, params))
        result = self.results.pop(0) if self.results else {"video_url": "memory://scene.mp4"}
        if isinstance(result, BaseException):
            raise result
        return result


async def _fake_download(_url: str, destination: Path) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"fake-mp4")
    return destination.stat().st_size


def _probe(path: Path) -> dict[str, Any]:
    return {"path": path, "duration_seconds": 4.0, "ok": path.exists()}


def _node(
    tmp_path: Path,
    adapter: FakeH3Adapter | None = None,
    **kwargs: Any,
) -> tuple[VideoNode, FakeH3Adapter]:
    adapter = adapter or FakeH3Adapter()
    node = VideoNode(
        adapter,
        proj_dir=tmp_path,
        downloader=_fake_download,
        probe=_probe,
        **kwargs,
    )
    return node, adapter


class TestBudget:
    async def test_default_cap_allows_one_call_and_blocks_the_next(self, tmp_path):
        node, adapter = _node(tmp_path)

        await node.generate("first scene", 4)
        node.unlock()
        with pytest.raises(BudgetExceeded) as exc:
            await node.generate("second scene", 4)

        assert len(adapter.calls) == 1
        assert node.budget.cap == DEFAULT_BUILD_CAP
        assert node.budget.spent == Decimal("1.00")
        assert exc.value.cap == Decimal("1.00")
        assert exc.value.projected == Decimal("2.00")
        assert "--confirm" in str(exc.value)
        assert not (tmp_path / NODES_DIRNAME / "scene-2.mp4").exists()

    async def test_exact_cap_boundary_is_allowed(self, tmp_path):
        budget = BuildBudget(cap=2, spent=0)
        node, adapter = _node(tmp_path, budget=budget)

        await node.generate("one", 2)
        node.unlock()
        await node.generate("two", 2)

        assert len(adapter.calls) == 2
        assert budget.spent == Decimal("2")

    async def test_manifest_per_build_cap_takes_precedence(self, tmp_path):
        manifest = ProjectManifest(
            {
                "project_id": "demo-project",
                "plan_id": "plan-1",
                "budget": {"cap": 10, "per_build_cap": 2.5, "spent": 1.5},
            }
        )
        node, adapter = _node(tmp_path, manifest=manifest, estimated_cost=1)

        await node.generate("within cap", 3)
        node.unlock()
        with pytest.raises(BudgetExceeded):
            await node.generate("over cap", 3)

        assert len(adapter.calls) == 1
        assert node.budget.cap == Decimal("2.5")
        assert node.budget.spent == Decimal("2.5")

    async def test_existing_spend_is_projected(self, tmp_path):
        node, adapter = _node(
            tmp_path,
            budget=BuildBudget(cap=1, spent=0.75),
            estimated_cost="0.25",
        )

        await node.generate("boundary", 1)

        assert len(adapter.calls) == 1
        assert node.budget.spent == Decimal("1.00")

    async def test_confirm_authorizes_overage_but_still_records_spend(self, tmp_path):
        budget = BuildBudget(cap=1, spent=1)
        node, adapter = _node(tmp_path, budget=budget, confirm=True)

        await node.generate("confirmed", 1)

        assert len(adapter.calls) == 1
        assert budget.spent == Decimal("2")
        assert budget.remaining == Decimal("-1")

    async def test_per_call_confirm_overrides_constructor_default(self, tmp_path):
        node, adapter = _node(tmp_path, budget=BuildBudget(cap=0))

        await node.generate("confirmed", 1, confirm=True)

        assert len(adapter.calls) == 1
        assert node.budget.spent == Decimal("1")

    async def test_blocked_projection_never_calls_h3(self, tmp_path):
        node, adapter = _node(tmp_path, budget=BuildBudget(cap=0))

        with pytest.raises(BudgetExceeded):
            await node.generate("blocked", 4)

        assert adapter.calls == []
        assert not (tmp_path / NODES_DIRNAME).exists()

    async def test_failed_h3_request_remains_accounted(self, tmp_path):
        adapter = FakeH3Adapter(RuntimeError("provider unavailable"))
        node, _ = _node(tmp_path, adapter=adapter)

        with pytest.raises(RuntimeError, match="provider unavailable"):
            await node.generate("failed", 4)
        with pytest.raises(BudgetExceeded):
            await node.generate("retry", 4)

        assert node.budget.spent == Decimal("1")

    async def test_nodes_sharing_a_manifest_share_one_build_budget(self, tmp_path):
        manifest = ProjectManifest(
            {
                "project_id": "demo-project",
                "plan_id": "plan-1",
                "budget": {"per_build_cap": 2},
            }
        )
        adapter = FakeH3Adapter()
        first, _ = _node(tmp_path / "first", adapter=adapter, manifest=manifest)
        second, _ = _node(tmp_path / "second", adapter=adapter, manifest=manifest)
        third, _ = _node(tmp_path / "third", adapter=adapter, manifest=manifest)

        await first.generate("one", 1)
        await second.generate("two", 1)
        with pytest.raises(BudgetExceeded):
            await third.generate("three", 1)

        assert first.budget is second.budget is third.budget
        assert first.budget.spent == Decimal("2")
        assert manifest.to_dict()["budget"]["spent"] == 2.0


class TestH3Generation:
    async def test_generate_calls_h3_writes_scene_and_probes(self, tmp_path):
        node, adapter = _node(tmp_path)

        output = await node.generate("rainy skyline", 7.5)

        assert output == tmp_path / NODES_DIRNAME / "scene-1.mp4"
        assert output.exists()
        assert adapter.calls == [("rainy skyline", {"duration": 7.5})]
        assert node.path == output
        with pytest.raises(NodeLockedError):
            await node.generate("locked", 7.5)

    def test_video_url_supports_documented_shapes(self):
        assert (
            _video_url({"video_url": "https://example.test/a.mp4"}) == "https://example.test/a.mp4"
        )
        assert _video_url({"media_urls": [{"url": "https://example.test/b.mp4"}]}) == (
            "https://example.test/b.mp4"
        )
        assert _video_url({"content": '{"url": "https://example.test/c.mp4"}'}) == (
            "https://example.test/c.mp4"
        )
        with pytest.raises(NodeError, match="no usable video URL"):
            _video_url({"text": "not a media response"})

    async def test_cancelled_download_removes_partial_output(self, tmp_path):
        async def cancelled_download(_url: str, destination: Path) -> int:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"partial")
            raise asyncio.CancelledError()

        node = VideoNode(
            FakeH3Adapter(),
            proj_dir=tmp_path,
            downloader=cancelled_download,
            probe=_probe,
        )

        with pytest.raises(asyncio.CancelledError):
            await node.generate("cancelled", 2)

        assert node.path is None
        assert not list((tmp_path / NODES_DIRNAME).glob("scene-*.mp4"))

    async def test_missing_video_url_is_an_error_after_budget_reservation(self, tmp_path):
        adapter = FakeH3Adapter({"text": "H3 returned prose"})
        node, _ = _node(tmp_path, adapter=adapter)

        with pytest.raises(NodeError, match="no usable video URL"):
            await node.generate("prose", 4)

        assert node.budget.spent == Decimal("1")
        assert not list((tmp_path / NODES_DIRNAME).glob("scene-*.mp4"))


class TestStaticFallback:
    @staticmethod
    def _runner(
        calls: list[tuple[list[str], Path]],
        *,
        fail_cover: bool = False,
        caption_contents: list[str] | None = None,
    ):
        def run(command: list[str], *, cwd: Path):
            calls.append((command, cwd))
            if caption_contents is not None:
                caption_path = cwd / f"caption-{Path(command[-1]).stem.split('-')[-1]}.txt"
                if caption_path.exists():
                    caption_contents.append(caption_path.read_text(encoding="utf-8"))
            if fail_cover and "-loop" in command:
                return SimpleNamespace(returncode=1, stderr="unsupported image", stdout="")
            Path(command[-1]).write_bytes(b"fallback-mp4")
            return SimpleNamespace(returncode=0, stderr="", stdout="")

        return run

    async def test_no_h3_uses_manifest_cover_art_and_does_not_spend(self, tmp_path):
        cover = tmp_path / "cover.png"
        cover.write_bytes(b"png")
        manifest = ProjectManifest(
            {
                "project_id": "demo-project",
                "plan_id": "plan-1",
                "plan": {
                    "plan_id": "plan-1",
                    "project_id": "demo-project",
                    "title": "Demo",
                    "objective": "Video",
                    "brief": "A demo",
                    "duration_seconds": 4,
                    "cover_art": str(cover),
                },
            }
        )
        calls: list[tuple[list[str], Path]] = []
        caption_contents: list[str] = []
        node, adapter = _node(
            tmp_path,
            manifest=manifest,
            no_h3=True,
            ffmpeg_runner=self._runner(calls, caption_contents=caption_contents),
        )

        output = await node.generate("caption text", 4)

        command, cwd = calls[0]
        assert output.exists()
        assert adapter.calls == []
        assert node.budget.spent == Decimal("0")
        assert cwd == tmp_path / NODES_DIRNAME
        assert "-loop" in command
        assert str(cover) in command
        assert "drawtext" in command[command.index("-vf") + 1]
        assert caption_contents == ["caption text"]
        assert not (tmp_path / NODES_DIRNAME / "caption-1.txt").exists()

    async def test_no_h3_without_cover_uses_generated_color_visual(self, tmp_path):
        calls: list[tuple[list[str], Path]] = []
        node, adapter = _node(
            tmp_path,
            no_h3=True,
            ffmpeg_runner=self._runner(calls),
        )

        output = await node.generate("generated caption", 3)

        command, _cwd = calls[0]
        assert output.exists()
        assert adapter.calls == []
        assert "-f" in command
        assert command[command.index("-f") + 1] == "lavfi"
        assert "color=c=black" in command[command.index("-i") + 1]
        assert node.budget.spent == Decimal("0")

    async def test_bad_cover_retries_with_generated_visual(self, tmp_path):
        cover = tmp_path / "bad-cover.png"
        cover.write_bytes(b"not-an-image")
        calls: list[tuple[list[str], Path]] = []
        node, _adapter = _node(
            tmp_path,
            no_h3=True,
            cover_art=cover,
            ffmpeg_runner=self._runner(calls, fail_cover=True),
        )

        output = await node.generate("caption", 2)

        assert output.exists()
        assert len(calls) == 2
        assert "-loop" in calls[0][0]
        assert "color=c=black" in calls[1][0][calls[1][0].index("-i") + 1]

    async def test_caption_text_is_not_interpolated_into_filtergraph(self, tmp_path):
        calls: list[tuple[list[str], Path]] = []
        caption_contents: list[str] = []
        caption = "$(touch hacked);: scary\\caption"
        node, _adapter = _node(
            tmp_path,
            no_h3=True,
            ffmpeg_runner=self._runner(calls, caption_contents=caption_contents),
        )

        await node.generate("prompt", 2, caption=caption)

        command, _cwd = calls[0]
        assert caption not in " ".join(command)
        assert caption_contents == [caption]
        assert not (tmp_path / NODES_DIRNAME / "caption-1.txt").exists()
        assert not (tmp_path / "hacked").exists()

    async def test_invalid_duration_has_no_side_effects(self, tmp_path):
        calls: list[tuple[list[str], Path]] = []
        node, adapter = _node(
            tmp_path,
            no_h3=True,
            ffmpeg_runner=self._runner(calls),
        )

        with pytest.raises(NodeError, match="duration"):
            await node.generate("invalid", 0)

        assert calls == []
        assert adapter.calls == []
        assert node.budget.spent == Decimal("0")

    async def test_probe_failure_removes_static_output(self, tmp_path):
        calls: list[tuple[list[str], Path]] = []

        def bad_probe(_path: Path) -> dict[str, Any]:
            return {"ok": False}

        node = VideoNode(
            FakeH3Adapter(),
            proj_dir=tmp_path,
            probe=bad_probe,
            no_h3=True,
            ffmpeg_runner=self._runner(calls),
        )

        with pytest.raises(NodeError, match="probe failed"):
            await node.generate("caption", 2)

        assert not list((tmp_path / NODES_DIRNAME).glob("scene-*.mp4"))
        assert node.path is None


class TestExports:
    def test_video_node_is_exported_from_studio_packages(self):
        assert NodesVideoNode is VideoNode
        assert ProjectManifest is not None

    def test_studio_build_exposes_h3_controls(self):
        result = CliRunner().invoke(main, ["studio", "build", "--help"])

        assert result.exit_code == 0
        assert "--confirm" in result.output
        assert "--no-h3" in result.output
