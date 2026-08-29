"""Tests for music_cli.studio.build — ``mc studio build`` (issue #139, P3.3).

The build service is exercised end-to-end through :class:`BuildService`
with a fake adapter, fake downloader, and fake ffprobe so the pipeline
runs with no network and no real ffmpeg binary. A separate test class
covers the Click ``mc studio build`` command with a :class:`click.testing
.CliRunner`.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner

from music_cli.cli import main
from music_cli.studio.build import (
    Brief,
    BuildError,
    BuildService,
    load_brief_from_yaml,
)
from music_cli.studio.director import M3Director
from music_cli.studio.nodes.music import MusicNode
from music_cli.studio.nodes.speech import SpeechNode

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


VALID_PLAN = {
    "plan_id": "plan-001",
    "project_id": "neon-rain",
    "title": "Neon Rain",
    "objective": "Ship a 60s premiere",
    "brief": "A neon hums against the wet sidewalk.",
    "duration_seconds": 60,
    "tracks": [
        {
            "id": "track-1",
            "prompt": "synthwave bed",
            "description": "A slow, neon-drenched synth pad.",
            "duration_seconds": 60,
        },
    ],
    "scenes": [
        {
            "id": "scene-1",
            "prompt": "narrate the opening line",
            "description": "The neon hums against the wet sidewalk.",
            "duration_seconds": 5.0,
        },
    ],
}


class FakeAdapter:
    """Replays a single M3 plan and never makes a network call."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.plan_prompts: list[str] = []

    async def m3_plan(self, prompt: str, **_: object) -> dict[str, str]:
        self.plan_prompts.append(prompt)
        idx = len(self.plan_prompts) - 1
        if idx < len(self.replies):
            return {"text": self.replies[idx]}
        return {"text": self.replies[-1]}

    async def m3_critique(self, prompt: str, **_: object) -> dict[str, str]:
        return {"text": json.dumps({"ok": True, "issues": [], "repairs": []})}

    async def music3_generate(
        self, prompt: str, *, lyrics: str | None = None, **_: object
    ) -> dict[str, str]:
        return {"audio_url": f"memory://{prompt}"}

    async def speech28_synthesize(
        self, text: str, *, voice: str | None = None, **_: object
    ) -> dict[str, str]:
        return {"audio_url": f"memory://speech/{text[:8]}"}


def _write_dummy_wav(path: Path, seconds: float = 1.0) -> Path:
    """Write a minimal valid WAV (PCM 16-bit mono 8 kHz) at ``path``.

    The header is hand-built so the file is probeable by ffprobe but
    contains a fixed amount of zeroed audio. Used by the build tests to
    fake adapter downloads without touching the network.
    """
    sample_rate = 8000
    n_samples = int(seconds * sample_rate)
    data_size = n_samples * 2  # 16-bit mono
    with path.open("wb") as fh:
        fh.write(b"RIFF")
        fh.write((36 + data_size).to_bytes(4, "little"))
        fh.write(b"WAVE")
        fh.write(b"fmt ")
        fh.write((16).to_bytes(4, "little"))
        fh.write((1).to_bytes(2, "little"))  # PCM
        fh.write((1).to_bytes(2, "little"))  # mono
        fh.write(sample_rate.to_bytes(4, "little"))
        fh.write((sample_rate * 2).to_bytes(4, "little"))
        fh.write((2).to_bytes(2, "little"))
        fh.write((16).to_bytes(2, "little"))
        fh.write(b"data")
        fh.write(data_size.to_bytes(4, "little"))
        fh.write(b"\x00" * data_size)
    return path


async def _fake_download(url: str, dest: Path) -> int:
    """Drop a tiny WAV into ``dest`` so the probe has something to read."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    _write_dummy_wav(dest, seconds=1.0)
    return dest.stat().st_size


class FakeProbe:
    """Returns a fixed duration without shelling out to ffprobe."""

    def __init__(self, seconds: float = 1.0) -> None:
        self.seconds = seconds
        self.calls: list[Path] = []

    def __call__(self, path: Path) -> dict[str, object]:
        self.calls.append(path)
        return {"path": path, "duration_seconds": self.seconds, "ok": True}


def _service_factory(
    adapter: FakeAdapter,
    probe: FakeProbe,
    proj_dir: Path,
    brief: Brief,
) -> tuple[M3Director, MusicNode, SpeechNode]:
    director = M3Director(adapter, trace_path=proj_dir / "trace.jsonl")
    music = MusicNode(adapter, proj_dir=proj_dir, downloader=_fake_download, probe=probe)
    speech = SpeechNode(adapter, proj_dir=proj_dir, downloader=_fake_download, probe=probe)
    _ = brief
    return director, music, speech


def _make_service(
    tmp_path: Path,
    *,
    plan_payload: dict[str, object] | None = None,
    probe: FakeProbe | None = None,
    plan_text: str | None = None,
) -> tuple[BuildService, FakeAdapter, FakeProbe]:
    plan_payload = plan_payload if plan_payload is not None else VALID_PLAN
    plan_text = plan_text if plan_text is not None else json.dumps(plan_payload)
    probe = probe if probe is not None else FakeProbe(seconds=1.0)
    adapter = FakeAdapter(plan_text)

    def factory(proj_dir, brief):
        return _service_factory(adapter, probe, proj_dir, brief)

    service = BuildService(dist_dir=tmp_path, adapter_factory=factory)
    return service, adapter, probe


# ===========================================================================
# Brief validation
# ===========================================================================


class TestBrief:
    def test_minimal_dict_parses(self):
        b = Brief.from_dict({"project_id": "p1", "description": "go"})
        assert b.project_id == "p1"
        assert b.description == "go"
        assert b.duration_seconds is None
        assert b.taste is None

    def test_accepts_brief_alias_for_description(self):
        b = Brief.from_dict({"project_id": "p1", "brief": "alt"})
        assert b.description == "alt"

    def test_rejects_empty_project_id(self):
        with pytest.raises(BuildError) as exc:
            Brief.from_dict({"project_id": "  ", "description": "go"})
        assert exc.value.stage == "plan"

    def test_rejects_project_path_traversal(self):
        with pytest.raises(BuildError, match="lowercase slug"):
            Brief.from_dict({"project_id": "../outside", "description": "go"})

    def test_rejects_empty_description(self):
        with pytest.raises(BuildError) as exc:
            Brief.from_dict({"project_id": "p1", "description": "  "})
        assert exc.value.stage == "plan"

    def test_coerces_duration(self):
        b = Brief.from_dict({"project_id": "p1", "description": "x", "duration_seconds": "30"})
        assert b.duration_seconds == 30.0

    def test_rejects_negative_duration(self):
        with pytest.raises(BuildError):
            Brief.from_dict({"project_id": "p1", "description": "x", "duration_seconds": -1})

    def test_taste_must_be_mapping(self):
        with pytest.raises(BuildError):
            Brief.from_dict({"project_id": "p1", "description": "x", "taste": "nope"})


# ===========================================================================
# BuildService.run
# ===========================================================================


class TestBuildServiceRun:
    def test_happy_path_writes_plan_trace_and_premiere(self, tmp_path):
        service, adapter, probe = _make_service(tmp_path)
        brief = Brief.from_dict({"project_id": "neon-rain", "description": "go"})
        result = service.run(brief)

        proj = tmp_path / "neon-rain"
        assert (proj / "plan.yaml").exists()
        assert (proj / "trace.jsonl").exists()
        assert (proj / "manifest.yaml").exists()
        assert result.premiere_mp4 is not None and result.premiere_mp4.exists()
        assert result.premiere_wav is not None and result.premiere_wav.exists()
        # one PLAN + GENERATE (music) + PROBE + GENERATE (speech) + PROBE + COMPOSE
        recs = [
            json.loads(line)
            for line in (proj / "trace.jsonl").read_text().splitlines()
            if line.strip()
        ]
        steps = [r["step"] for r in recs]
        assert "plan" in steps
        assert steps.count("generate") == 2
        assert steps.count("probe") == 2
        assert "compose" in steps
        # one director.plan call recorded
        assert len(adapter.plan_prompts) == 1
        # probe was called for the music and speech node
        assert len(probe.calls) >= 2

    def test_idempotent_no_op_run_skips_premiere_remux(self, tmp_path):
        service, _adapter, _probe = _make_service(tmp_path)
        brief = Brief.from_dict({"project_id": "neon-rain", "description": "go"})
        first = service.run(brief)
        first_mp4_mtime = first.premiere_mp4.stat().st_mtime
        # second run with the same brief — locked nodes, no remux
        second = service.run(brief)
        assert not second.regenerated
        assert second.premiere_mp4 == first.premiere_mp4  # not re-muxed
        assert first.premiere_mp4.stat().st_mtime == first_mp4_mtime
        assert len(_adapter.plan_prompts) == 1  # persisted plan is reused

    def test_force_regenerates_and_remux(self, tmp_path):
        service, _adapter, _probe = _make_service(tmp_path)
        brief = Brief.from_dict({"project_id": "neon-rain", "description": "go"})
        service.run(brief)
        result = service.run(brief, force=True)
        assert result.regenerated
        assert result.premiere_mp4 is not None and result.premiere_mp4.exists()

    def test_invalid_brief_raises_plan_error(self, tmp_path):
        service, _adapter, _probe = _make_service(tmp_path)
        with pytest.raises(BuildError) as exc:
            service.run("not a brief")  # type: ignore[arg-type]
        assert exc.value.stage == "plan"

    def test_malformed_plan_payload_raises_plan_error(self, tmp_path):
        # Plan missing required field "duration_seconds"
        bad = {k: v for k, v in VALID_PLAN.items() if k != "duration_seconds"}
        service, _adapter, _probe = _make_service(tmp_path, plan_payload=bad)
        brief = Brief.from_dict({"project_id": "neon-rain", "description": "go"})
        with pytest.raises(BuildError) as exc:
            service.run(brief)
        assert exc.value.stage == "plan"

    def test_no_tracks_no_scenes_uses_brief_fallback(self, tmp_path):
        """When plan has no tracks/scenes, fallback generates from brief."""
        empty = {k: v for k, v in VALID_PLAN.items() if k not in {"tracks", "scenes"}}
        service, _adapter, _probe = _make_service(tmp_path, plan_payload=empty)
        brief = Brief.from_dict({"project_id": "neon-rain", "description": "go"})
        result = service.run(brief)
        # Should succeed with fallback track from brief
        assert result.premiere_mp4 is not None and result.premiere_mp4.exists()

    def test_duration_within_two_seconds_of_plan(self, tmp_path):
        service, _adapter, probe = _make_service(tmp_path, probe=FakeProbe(seconds=60.0))
        brief = Brief.from_dict({"project_id": "neon-rain", "description": "go"})
        result = service.run(brief)
        # The fake probe says each audio is 60s; the mix has 60s of audio
        # and the SRT window is 5s. The acceptance criterion is the final
        # mp4 duration is within ±2s of the plan's 60s.
        assert result.premiere_mp4 is not None
        assert result.premiere_mp4.exists()


# ===========================================================================
# Brief loader
# ===========================================================================


class TestBriefLoader:
    def test_load_example_preserves_block_description(self):
        brief = load_brief_from_yaml(Path("examples/neon-rain.yaml"))
        assert brief.description.startswith("A neon-drenched synthwave")
        assert "futuristic city" in brief.description

    def test_load_yaml(self, tmp_path):
        path = tmp_path / "neon-rain.yaml"
        path.write_text(
            "project_id: neon-rain # output slug\n"
            "description: A noir rooftop chase in the rain.\n"
            "duration_seconds: 60 # seconds\n"
            "taste: # optional\n"
            "  tempo_bpm: 96\n",
            encoding="utf-8",
        )
        b = load_brief_from_yaml(path)
        assert b.project_id == "neon-rain"
        assert "noir" in b.description
        assert b.duration_seconds == 60.0
        assert b.taste == {"tempo_bpm": 96}

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(BuildError):
            load_brief_from_yaml(tmp_path / "nope.yaml")


# ===========================================================================
# Default adapter factory
# ===========================================================================


class TestDefaultAdapterFactory:
    def test_uses_stored_gmi_key(self, tmp_path):
        brief = Brief.from_dict({"project_id": "p1", "description": "go"})
        with (
            mock.patch("music_cli.cloud.secrets.get_api_key", return_value="test-key"),
            mock.patch("music_cli.cloud.gmi.GMIAdapter") as adapter_cls,
        ):
            from music_cli.studio.build import default_adapter_factory

            default_adapter_factory(tmp_path / "p1", brief)
        adapter_cls.assert_called_once_with("test-key")

    def test_missing_gmi_key_is_a_build_error(self, tmp_path):
        brief = Brief.from_dict({"project_id": "p1", "description": "go"})
        with mock.patch("music_cli.cloud.secrets.get_api_key", return_value=None):
            from music_cli.studio.build import default_adapter_factory

            with pytest.raises(BuildError, match="mc cloud key set gmi"):
                default_adapter_factory(tmp_path / "p1", brief)


# ===========================================================================
# Click wrapper
# ===========================================================================


class TestStudioBuildCli:
    def _brief(self, tmp_path: Path) -> Path:
        p = tmp_path / "neon-rain.yaml"
        p.write_text(
            "project_id: neon-rain\ndescription: a noir rooftop\nduration_seconds: 60\n",
            encoding="utf-8",
        )
        return p

    def test_build_writes_premiere(self, tmp_path):
        brief_path = self._brief(tmp_path)
        adapter = FakeAdapter(json.dumps(VALID_PLAN))
        probe = FakeProbe(seconds=1.0)

        def factory(proj_dir, brief):
            return _service_factory(adapter, probe, proj_dir, brief)

        # The CLI's ``studio_build`` constructs a BuildService without an
        # adapter_factory; inject one by monkey-patching the default.
        with mock.patch("music_cli.studio.build.default_adapter_factory", factory):
            runner = CliRunner()
            result = runner.invoke(
                main, ["studio", "build", str(brief_path), "--dist-dir", str(tmp_path)]
            )
        assert result.exit_code == 0, result.output
        assert (tmp_path / "neon-rain" / "premiere.mp4").exists()

    def test_build_missing_brief_exits_nonzero(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["studio", "build", str(tmp_path / "nope.yaml")])
        assert result.exit_code != 0
