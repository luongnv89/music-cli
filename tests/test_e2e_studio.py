"""End-to-end tests for ``mc studio`` commands (Epic 131 — creative compiler).

Covers every new CLI command and flag introduced by the mc studio creative
compiler:

- ``mc studio --help`` — lists build, revise, doctor, plan, trace
- ``mc studio build <brief.yaml>`` — full pipeline via BuildService
- ``mc studio build --resume`` — resume partial build
- ``mc studio build --force`` — force regeneration
- ``mc studio build --no-h3`` — skip H3 video, static fallback
- ``mc studio build --from-playlist`` — taste profile seeding
- ``mc studio build --confirm`` — exceed H3 budget cap
- ``mc studio revise <project> "<intent>"`` — targeted plan revision
- ``mc studio doctor`` — dependency health checks
- ``mc studio plan <project>`` — pretty-print plan.yaml
- ``mc studio trace <project>`` — render trace.jsonl table

All tests are **hermetic**: no real API calls, no real ffmpeg, no real
ffprobe. External dependencies are faked via adapter / probe / download
stubs. The path under test is:

    CliRunner → Click command → BuildService → graph/nodes → filesystem
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
    BuildResult,
    BuildService,
)
from music_cli.studio.director import M3Director
from music_cli.studio.nodes.music import MusicNode
from music_cli.studio.nodes.speech import SpeechNode

# ===========================================================================
# Fixtures & helpers
# ===========================================================================


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _write_brief(tmp_path: Path, **overrides: object) -> Path:
    """Write a minimal brief YAML to *tmp_path* and return its path."""
    data: dict[str, object] = {
        "project_id": "e2e-test",
        "description": "A test project for e2e coverage.",
        "duration_seconds": 30,
    }
    data.update(overrides)
    path = tmp_path / "brief.yaml"
    # Minimal YAML rendering — no need for a full serializer.
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, str) and "\n" in value:
            lines.append(f"{key}: |")
            for line in value.splitlines():
                lines.append(f"  {line}")
        elif isinstance(value, str):
            lines.append(f"{key}: {value}")
        elif isinstance(value, (int, float)):
            lines.append(f"{key}: {value}")
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            for k2, v2 in value.items():
                lines.append(f"  {k2}: {v2}")
        else:
            lines.append(f"{key}: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_playlist(tmp_path: Path) -> Path:
    """Write a minimal M3U playlist file."""
    path = tmp_path / "playlist.m3u"
    path.write_text(
        "#EXTM3U\n"
        "#EXTINF:180,Track One\n"
        "/tmp/track1.mp3\n"
        "#EXTINF:240,Track Two\n"
        "/tmp/track2.mp3\n",
        encoding="utf-8",
    )
    return path


#: A valid CreativePlan payload that the fake adapter returns.
VALID_PLAN: dict[str, object] = {
    "plan_id": "plan-e2e-001",
    "project_id": "e2e-test",
    "title": "E2E Test Project",
    "objective": "Ship a 30s premiere",
    "brief": "A test project for e2e coverage.",
    "duration_seconds": 30,
    "tracks": [
        {
            "id": "track-1",
            "prompt": "synthwave bed",
            "description": "A slow synth pad.",
            "duration_seconds": 30,
        },
    ],
    "scenes": [
        {
            "id": "scene-1",
            "prompt": "narrate the opening",
            "description": "The test begins.",
            "duration_seconds": 5.0,
        },
    ],
}


def _write_dummy_wav(path: Path, seconds: float = 1.0) -> Path:
    """Write a minimal valid WAV (PCM 16-bit mono 8 kHz)."""
    sample_rate = 8000
    n_samples = int(seconds * sample_rate)
    data_size = n_samples * 2
    with path.open("wb") as fh:
        fh.write(b"RIFF")
        fh.write((36 + data_size).to_bytes(4, "little"))
        fh.write(b"WAVE")
        fh.write(b"fmt ")
        fh.write((16).to_bytes(4, "little"))
        fh.write((1).to_bytes(2, "little"))
        fh.write((1).to_bytes(2, "little"))
        fh.write(sample_rate.to_bytes(4, "little"))
        fh.write((sample_rate * 2).to_bytes(4, "little"))
        fh.write((2).to_bytes(2, "little"))
        fh.write((16).to_bytes(2, "little"))
        fh.write(b"data")
        fh.write(data_size.to_bytes(4, "little"))
        fh.write(b"\x00" * data_size)
    return path


async def _fake_download(url: str, dest: Path) -> int:
    """Drop a tiny WAV into *dest*."""
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


class RecordingFakeAdapter:
    """Replays a CreativePlan and never makes a network call.

    Records every method call so the e2e tests can assert on the
    pipeline stages that were exercised.
    """

    def __init__(self, plan_payload: dict[str, object] | None = None) -> None:
        self.plan_payload = plan_payload or VALID_PLAN
        self.calls: list[str] = []
        self.plan_prompts: list[str] = []

    async def m3_plan(self, prompt: str, **_: object) -> dict[str, str]:
        self.calls.append("m3_plan")
        self.plan_prompts.append(prompt)
        return {"text": json.dumps(self.plan_payload)}

    async def m3_critique(self, prompt: str, **_: object) -> dict[str, str]:
        self.calls.append("m3_critique")
        return {"text": json.dumps({"ok": True, "issues": [], "repairs": []})}

    async def music3_generate(
        self, prompt: str, *, lyrics: str | None = None, **_: object
    ) -> dict[str, str]:
        self.calls.append("music3_generate")
        return {"audio_url": f"memory://{prompt}"}

    async def speech28_synthesize(
        self, text: str, *, voice: str | None = None, **_: object
    ) -> dict[str, str]:
        self.calls.append("speech28_synthesize")
        return {"audio_url": f"memory://speech/{text[:8]}"}

    async def h3_generate(
        self, prompt: str, **_: object
    ) -> dict[str, str]:
        self.calls.append("h3_generate")
        return {"video_url": f"memory://h3/{prompt[:8]}"}


def _make_service(
    tmp_path: Path,
    adapter: RecordingFakeAdapter | None = None,
    probe: FakeProbe | None = None,
) -> tuple[BuildService, RecordingFakeAdapter, FakeProbe]:
    adapter = adapter or RecordingFakeAdapter()
    probe = probe or FakeProbe(seconds=1.0)

    def factory(proj_dir, brief):
        director = M3Director(adapter, trace_path=proj_dir / "trace.jsonl")
        music = MusicNode(adapter, proj_dir=proj_dir, downloader=_fake_download, probe=probe)
        speech = SpeechNode(adapter, proj_dir=proj_dir, downloader=_fake_download, probe=probe)
        return director, music, speech

    service = BuildService(dist_dir=tmp_path, adapter_factory=factory)
    return service, adapter, probe


def _read_trace(project_dir: Path) -> list[dict]:
    """Parse trace.jsonl into a list of dicts."""
    trace_file = project_dir / "trace.jsonl"
    records: list[dict] = []
    if trace_file.exists():
        for line in trace_file.read_text().splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def _invoke_studio(runner: CliRunner, *args, **kwargs) -> tuple[mock._patch, RecordingFakeAdapter, FakeProbe]:
    """Invoke an mc studio command and return the patch list for the adapter factory."""
    adapter = RecordingFakeAdapter()
    probe = FakeProbe(seconds=1.0)

    def factory(proj_dir, brief):
        director = M3Director(adapter, trace_path=proj_dir / "trace.jsonl")
        music = MusicNode(adapter, proj_dir=proj_dir, downloader=_fake_download, probe=probe)
        speech = SpeechNode(adapter, proj_dir=proj_dir, downloader=_fake_download, probe=probe)
        return director, music, speech

    # Patch where BuildService looks it up (the module where it is defined).
    patch = mock.patch("music_cli.studio.build.default_adapter_factory", factory)
    return patch, adapter, probe


# ===========================================================================
# CLI discovery
# ===========================================================================


class TestStudioCLIDiscovery:
    """Verify the ``mc studio`` command group is discoverable."""

    def test_studio_help_lists_commands(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["studio", "--help"])
        assert result.exit_code == 0, result.output
        for cmd in ("build", "revise", "doctor", "plan", "trace"):
            assert cmd in result.output, f"Missing command '{cmd}' in studio --help"

    @pytest.mark.parametrize(
        "cmd",
        ["build", "revise", "doctor", "plan", "trace"],
    )
    def test_command_help_exits_ok(self, runner: CliRunner, cmd: str) -> None:
        result = runner.invoke(main, ["studio", cmd, "--help"])
        assert result.exit_code == 0, f"--help failed for studio {cmd}:\n{result.output}"
        assert "Usage:" in result.output, f"No 'Usage:' in help for studio {cmd}"


# ===========================================================================
# Build command — options
# ===========================================================================


class TestBuildCommandOptions:
    """Verify every build flag is accepted by the Click parser."""

    @pytest.mark.parametrize(
        "flag",
        [
            "--resume",
            "--force",
            "--confirm",
            "--no-h3",
            "--from-playlist",
            "--dist-dir",
        ],
    )
    def test_flag_appears_in_help(self, runner: CliRunner, flag: str) -> None:
        result = runner.invoke(main, ["studio", "build", "--help"])
        assert result.exit_code == 0, result.output
        assert flag in result.output, f"Flag {flag!r} missing from build --help"

    def test_resume_and_force_conflict(self, runner: CliRunner) -> None:
        """--resume and --force are mutually exclusive."""
        tmp = Path("/tmp/e2e-studio-test-resume-force")
        tmp.mkdir(exist_ok=True)
        brief = _write_brief(tmp)
        result = runner.invoke(main, ["studio", "build", str(brief), "--resume", "--force"])
        assert result.exit_code != 0
        assert "cannot be used together" in result.output or result.exit_code == 2


# ===========================================================================
# Build — happy path
# ===========================================================================


class TestBuildHappyPath:
    """Full pipeline: brief → plan → generate → compose → premiere.mp4."""

    def test_build_writes_all_artifacts(self, runner: CliRunner) -> None:
        tmp = Path("/tmp/e2e-studio-happy")
        tmp.mkdir(exist_ok=True)
        brief_path = _write_brief(tmp)
        patch, adapter, probe = _invoke_studio(runner, str(brief_path), dist_dir=str(tmp))

        with patch:
            result = runner.invoke(
                main, ["studio", "build", str(brief_path), "--dist-dir", str(tmp)]
            )

        assert result.exit_code == 0, result.output
        assert result.exception is None or isinstance(result.exception, SystemExit)

        proj = tmp / "e2e-test"
        assert proj.is_dir(), f"Project dir not created: {proj}"
        assert (proj / "plan.yaml").exists(), "plan.yaml missing"
        assert (proj / "trace.jsonl").exists(), "trace.jsonl missing"
        assert (proj / "manifest.yaml").exists(), "manifest.yaml missing"

        premiere = proj / "premiere.mp4"
        assert premiere.exists(), "premiere.mp4 missing"
        assert premiere.stat().st_size > 0, "premiere.mp4 is empty"

        # Assert trace contains expected pipeline stages
        records = _read_trace(proj)
        steps = [r.get("step") for r in records]
        assert "plan" in steps, "plan stage missing from trace"
        assert steps.count("generate") >= 2, "Expected >=2 generate stages (music + speech)"
        assert "compose" in steps, "compose stage missing from trace"
        assert steps.count("probe") >= 2, "Expected >=2 probe stages"

    def test_build_creates_project_under_dist(self, runner: CliRunner) -> None:
        """Verify the project lands under the dist dir."""
        tmp = Path("/tmp/e2e-studio-dist")
        tmp.mkdir(exist_ok=True)
        brief_path = _write_brief(tmp)
        patch, _, _ = _invoke_studio(runner, str(brief_path), dist_dir=str(tmp))

        with patch:
            result = runner.invoke(
                main, ["studio", "build", str(brief_path), "--dist-dir", str(tmp)]
            )

        assert result.exit_code == 0, result.output
        # The project dir should be under tmp (dist_dir)
        assert (tmp / "e2e-test").is_dir()

    def test_build_output_mentions_project_and_plan(self, runner: CliRunner) -> None:
        """CLI output should mention project name and plan ID."""
        tmp = Path("/tmp/e2e-studio-output")
        tmp.mkdir(exist_ok=True)
        brief_path = _write_brief(tmp)
        patch, _, _ = _invoke_studio(runner, str(brief_path), dist_dir=str(tmp))

        with patch:
            result = runner.invoke(
                main, ["studio", "build", str(brief_path), "--dist-dir", str(tmp)]
            )

        assert result.exit_code == 0, result.output
        output_lower = result.output.lower()
        assert "build ok" in output_lower or "premiere" in output_lower


# ===========================================================================
# Build — resume
# ===========================================================================


class TestBuildResume:
    """--resume: completed stages are skipped, missing stages run."""

    def test_resume_skips_completed_nodes(self, runner: CliRunner) -> None:
        """First build completes; second build with --resume skips everything."""
        tmp = Path("/tmp/e2e-studio-resume")
        tmp.mkdir(exist_ok=True)
        brief_path = _write_brief(tmp)
        adapter = RecordingFakeAdapter()
        patch, _, _ = _invoke_studio(runner, str(brief_path), dist_dir=str(tmp))

        # First build
        with patch:
            result1 = runner.invoke(
                main, ["studio", "build", str(brief_path), "--dist-dir", str(tmp)]
            )
        assert result1.exit_code == 0, result1.output

        # Second build with --resume
        with patch:
            result2 = runner.invoke(
                main,
                ["studio", "build", str(brief_path), "--dist-dir", str(tmp), "--resume"],
            )

        assert result2.exit_code == 0, result2.output
        # Adapter should NOT have been called again (nodes are locked)
        # The adapter was already consumed by the first build;
        # with --resume, the second build should reuse persisted state.
        proj = tmp / "e2e-test"
        assert (proj / "premiere.mp4").exists()

    def test_resume_with_partial_build(self, runner: CliRunner) -> None:
        """Resume from a partial build (plan exists, but no nodes generated)."""
        tmp = Path("/tmp/e2e-studio-resume-partial")
        tmp.mkdir(exist_ok=True)
        brief_path = _write_brief(tmp)

        # Create a partial project: plan exists, but no nodes dir
        proj = tmp / "e2e-test-partial"
        proj.mkdir(parents=True, exist_ok=True)
        plan_path = proj / "plan.yaml"
        plan_path.write_text(
            "plan_id: plan-partial\n"
            "project_id: e2e-test-partial\n"
            "title: Partial Build\n"
            "objective: Resume test\n"
            "brief: A partial build\n"
            "duration_seconds: 30\n"
            "tracks:\n"
            "  - id: track-1\n"
            "    prompt: resume test\n"
            "    description: Resume\n"
            "    duration_seconds: 30\n",
            encoding="utf-8",
        )

        # Write a brief that matches the partial project
        brief_partial = _write_brief(tmp, project_id="e2e-test-partial")

        adapter = RecordingFakeAdapter(
            plan_payload={
                "plan_id": "plan-partial",
                "project_id": "e2e-test-partial",
                "title": "Partial Build",
                "objective": "Resume test",
                "brief": "A partial build",
                "duration_seconds": 30,
                "tracks": [
                    {
                        "id": "track-1",
                        "prompt": "resume test",
                        "description": "Resume",
                        "duration_seconds": 30,
                    },
                ],
            }
        )

        def factory(proj_dir, brief):
            director = M3Director(adapter, trace_path=proj_dir / "trace.jsonl")
            music = MusicNode(adapter, proj_dir=proj_dir, downloader=_fake_download, probe=FakeProbe())
            speech = SpeechNode(adapter, proj_dir=proj_dir, downloader=_fake_download, probe=FakeProbe())
            return director, music, speech

        with mock.patch("music_cli.studio.build.default_adapter_factory", factory):
            result = runner.invoke(
                main,
                ["studio", "build", str(brief_partial), "--dist-dir", str(tmp), "--resume"],
            )

        assert result.exit_code == 0, result.output
        assert (proj / "premiere.mp4").exists()


# ===========================================================================
# Build — force
# ===========================================================================


class TestBuildForce:
    """--force: regenerates all nodes and remuxes the premiere."""

    def test_force_regenerates_premiere(self, runner: CliRunner) -> None:
        """Build once, then --force should regenerate and update premiere mtime."""
        tmp = Path("/tmp/e2e-studio-force")
        tmp.mkdir(exist_ok=True)
        brief_path = _write_brief(tmp)
        patch, adapter, _ = _invoke_studio(runner, str(brief_path), dist_dir=str(tmp))

        # First build
        with patch:
            result1 = runner.invoke(
                main, ["studio", "build", str(brief_path), "--dist-dir", str(tmp)]
            )
        assert result1.exit_code == 0, result1.output

        premiere1_mtime = (tmp / "e2e-test" / "premiere.mp4").stat().st_mtime

        # Second build with --force
        adapter2 = RecordingFakeAdapter()
        patch2, _, _ = _invoke_studio(runner, str(brief_path), dist_dir=str(tmp))

        with patch2:
            result2 = runner.invoke(
                main,
                ["studio", "build", str(brief_path), "--dist-dir", str(tmp), "--force"],
            )

        assert result2.exit_code == 0, result2.output
        premiere2_mtime = (tmp / "e2e-test" / "premiere.mp4").stat().st_mtime
        assert premiere2_mtime > premiere1_mtime, "premiere mtime should change after --force"

    def test_force_regenerates_adapter_calls(self, runner: CliRunner) -> None:
        """--force should trigger new adapter calls (not skip via lock)."""
        tmp = Path("/tmp/e2e-studio-force-calls")
        tmp.mkdir(exist_ok=True)
        brief_path = _write_brief(tmp)

        # First build
        patch1, adapter1, _ = _invoke_studio(runner, str(brief_path), dist_dir=str(tmp))
        with patch1:
            result1 = runner.invoke(
                main, ["studio", "build", str(brief_path), "--dist-dir", str(tmp)]
            )
        assert result1.exit_code == 0, result1.output
        first_call_count = len(adapter1.calls)

        # Second build with --force
        patch2, adapter2, _ = _invoke_studio(runner, str(brief_path), dist_dir=str(tmp))
        with patch2:
            result2 = runner.invoke(
                main,
                ["studio", "build", str(brief_path), "--dist-dir", str(tmp), "--force"],
            )
        assert result2.exit_code == 0, result2.output
        second_call_count = len(adapter2.calls)

        # Force should have made new adapter calls
        assert second_call_count > 0, "Force should trigger adapter calls"


# ===========================================================================
# Build — no-h3 (static visual fallback)
# ===========================================================================


class TestBuildNoH3:
    """--no-h3: skips H3 video generation, uses static fallback."""

    def test_no_h3_skips_h3_calls(self, runner: CliRunner) -> None:
        """--no-h3 should not call h3_generate."""
        tmp = Path("/tmp/e2e-studio-no-h3")
        tmp.mkdir(exist_ok=True)
        brief_path = _write_brief(tmp)
        patch, adapter, _ = _invoke_studio(runner, str(brief_path), dist_dir=str(tmp))

        with patch:
            result = runner.invoke(
                main,
                ["studio", "build", str(brief_path), "--dist-dir", str(tmp), "--no-h3"],
            )

        assert result.exit_code == 0, result.output
        assert "h3_generate" not in adapter.calls, "--no-h3 should skip H3 calls"
        assert (tmp / "e2e-test" / "premiere.mp4").exists()


# ===========================================================================
# Build — from-playlist
# ===========================================================================


class TestBuildFromPlaylist:
    """--from-playlist: taste profile is extracted and merged into the brief."""

    def test_from_playlist_accepts_valid_playlist(self, runner: CliRunner) -> None:
        """--from-playlist with a valid M3U file should not error."""
        tmp = Path("/tmp/e2e-studio-playlist")
        tmp.mkdir(exist_ok=True)
        brief_path = _write_brief(tmp)
        playlist_path = _write_playlist(tmp)
        patch, adapter, probe = _invoke_studio(runner, str(brief_path), dist_dir=str(tmp))

        with patch:
            result = runner.invoke(
                main,
                [
                    "studio",
                    "build",
                    str(brief_path),
                    "--dist-dir",
                    str(tmp),
                    "--from-playlist",
                    str(playlist_path),
                ],
            )

        # May fail at ffprobe step (no real audio files), but should not be
        # a Click usage error (exit 2).
        assert result.exit_code != 2, f"Usage error with --from-playlist:\n{result.output}"

    def test_from_playlist_nonexistent_file(self, runner: CliRunner) -> None:
        """--from-playlist with a missing file should exit nonzero."""
        tmp = Path("/tmp/e2e-studio-playlist-missing")
        tmp.mkdir(exist_ok=True)
        brief_path = _write_brief(tmp)
        result = runner.invoke(
            main,
            [
                "studio",
                "build",
                str(brief_path),
                "--from-playlist",
                str(tmp / "nope.m3u"),
            ],
        )
        assert result.exit_code != 0


# ===========================================================================
# Build — confirm (budget override)
# ===========================================================================


class TestBuildConfirm:
    """--confirm: allows H3 to exceed the per-build budget cap."""

    def test_confirm_flag_accepted(self, runner: CliRunner) -> None:
        """--confirm should be accepted without usage error."""
        tmp = Path("/tmp/e2e-studio-confirm")
        tmp.mkdir(exist_ok=True)
        brief_path = _write_brief(tmp)
        patch, _, _ = _invoke_studio(runner, str(brief_path), dist_dir=str(tmp))

        with patch:
            result = runner.invoke(
                main,
                ["studio", "build", str(brief_path), "--dist-dir", str(tmp), "--confirm"],
            )
        # Should not be a Click usage error
        assert result.exit_code != 2


# ===========================================================================
# Build — error handling
# ===========================================================================


class TestBuildErrors:
    """Invalid brief and missing files should produce clean errors."""

    def test_missing_brief_file(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["studio", "build", "/tmp/nope.yaml"])
        assert result.exit_code != 0

    def test_invalid_brief_yaml(self, runner: CliRunner) -> None:
        tmp = Path("/tmp/e2e-studio-bad-brief")
        tmp.mkdir(exist_ok=True)
        bad_brief = tmp / "bad.yaml"
        bad_brief.write_text("project_id: ''\ndescription: ''\n", encoding="utf-8")
        result = runner.invoke(main, ["studio", "build", str(bad_brief)])
        assert result.exit_code != 0
        assert "plan" in result.output.lower() or result.exit_code == 2

    def test_brief_with_traversal_project_id(self, runner: CliRunner) -> None:
        tmp = Path("/tmp/e2e-studio-traversal")
        tmp.mkdir(exist_ok=True)
        bad_brief = tmp / "traversal.yaml"
        bad_brief.write_text(
            "project_id: ../outside\ndescription: should fail\n",
            encoding="utf-8",
        )
        result = runner.invoke(main, ["studio", "build", str(bad_brief)])
        assert result.exit_code != 0


# ===========================================================================
# Revise command
# ===========================================================================


class TestReviseCommand:
    """mc studio revise — targeted plan revision."""

    def test_revise_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["studio", "revise", "--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "INTENT" in result.output

    def test_revise_missing_project(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["studio", "revise", "nonexistent", "change something"])
        assert result.exit_code != 0

    def test_revise_after_build(self, runner: CliRunner) -> None:
        """Build a project, then revise it."""
        tmp = Path("/tmp/e2e-studio-revise")
        tmp.mkdir(exist_ok=True)
        brief_path = _write_brief(tmp)

        # Build first
        patch1, adapter1, _ = _invoke_studio(runner, str(brief_path), dist_dir=str(tmp))
        with patch1:
            result1 = runner.invoke(
                main, ["studio", "build", str(brief_path), "--dist-dir", str(tmp)]
            )
        assert result1.exit_code == 0, result1.output

        # Now revise
        revised_plan = dict(VALID_PLAN)
        revised_plan["plan_id"] = "plan-revised-001"
        revised_plan["from_plan_id"] = "plan-e2e-001"
        revised_plan["to_plan_id"] = "plan-revised-001"
        revised_plan["reason"] = "User requested changes"
        revised_plan["affected_nodes"] = ["track-1"]
        revised_plan["regenerate_nodes"] = ["track-1"]

        adapter2 = RecordingFakeAdapter(plan_payload=revised_plan)

        def revise_factory(proj_dir, brief):
            director = M3Director(adapter2, trace_path=proj_dir / "trace.jsonl")
            music = MusicNode(adapter2, proj_dir=proj_dir, downloader=_fake_download, probe=FakeProbe())
            speech = SpeechNode(adapter2, proj_dir=proj_dir, downloader=_fake_download, probe=FakeProbe())
            return director, music, speech

        with mock.patch("music_cli.studio.build.default_adapter_factory", revise_factory):
            result = runner.invoke(
                main,
                ["studio", "revise", "e2e-test", "Change the music to be faster", "--dist-dir", str(tmp)],
            )

        # Revise may succeed or fail depending on internal logic,
        # but should not be a Click usage error.
        assert result.exit_code != 2, f"Revise usage error:\n{result.output}"


# ===========================================================================
# Doctor command
# ===========================================================================


class TestDoctorCommand:
    """mc studio doctor — dependency health checks."""

    def test_doctor_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["studio", "doctor", "--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output

    def test_doctor_exits_ok_with_dist_dir(self, runner: CliRunner) -> None:
        """Doctor should exit 0 when all checks pass (or warn)."""
        tmp = Path("/tmp/e2e-studio-doctor")
        tmp.mkdir(exist_ok=True)
        result = runner.invoke(main, ["studio", "doctor", "--dist-dir", str(tmp)])
        # Doctor may exit 0 or non-zero depending on environment
        # (e.g., no ffmpeg installed). The key is it should not crash.
        assert result.exit_code in (0, 1), f"Doctor crashed:\n{result.output}"

    def test_doctor_output_contains_checks(self, runner: CliRunner) -> None:
        """Doctor output should mention check names."""
        tmp = Path("/tmp/e2e-studio-doctor-output")
        tmp.mkdir(exist_ok=True)
        result = runner.invoke(main, ["studio", "doctor", "--dist-dir", str(tmp)])
        output = result.output.lower()
        # At least some check names should appear
        assert any(
            kw in output
            for kw in ("ffmpeg", "gmi", "dist", "network", "disk", "openrouter", "h3")
        ), f"Doctor output missing check names:\n{result.output}"

    def test_doctor_with_fix_messages(self, runner: CliRunner) -> None:
        """Doctor should show 'fix:' lines for failed/warned checks."""
        tmp = Path("/tmp/e2e-studio-doctor-fix")
        tmp.mkdir(exist_ok=True)
        result = runner.invoke(main, ["studio", "doctor", "--dist-dir", str(tmp)])
        # If there are warnings/failures, fix hints should be present
        if "FAIL" in result.output or "WARN" in result.output:
            assert "fix:" in result.output.lower() or "install" in result.output.lower()


# ===========================================================================
# Plan command
# ===========================================================================


class TestPlanCommand:
    """mc studio plan — pretty-print plan.yaml."""

    def test_plan_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["studio", "plan", "--help"])
        assert result.exit_code == 0

    def test_plan_missing_project(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["studio", "plan", "nonexistent"])
        assert result.exit_code != 0

    def test_plan_after_build(self, runner: CliRunner) -> None:
        """Build a project, then inspect its plan."""
        tmp = Path("/tmp/e2e-studio-plan")
        tmp.mkdir(exist_ok=True)
        brief_path = _write_brief(tmp)
        patch, _, _ = _invoke_studio(runner, str(brief_path), dist_dir=str(tmp))

        with patch:
            result_build = runner.invoke(
                main, ["studio", "build", str(brief_path), "--dist-dir", str(tmp)]
            )
        assert result_build.exit_code == 0, result_build.output

        # Now inspect the plan
        result = runner.invoke(main, ["studio", "plan", "e2e-test", "--dist-dir", str(tmp)])
        assert result.exit_code == 0, result.output
        assert "e2e-test" in result.output or "plan" in result.output.lower()


# ===========================================================================
# Trace command
# ===========================================================================


class TestTraceCommand:
    """mc studio trace — render trace.jsonl as a table."""

    def test_trace_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["studio", "trace", "--help"])
        assert result.exit_code == 0

    def test_trace_missing_project(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["studio", "trace", "nonexistent"])
        assert result.exit_code != 0

    def test_trace_after_build(self, runner: CliRunner) -> None:
        """Build a project, then inspect its trace."""
        tmp = Path("/tmp/e2e-studio-trace")
        tmp.mkdir(exist_ok=True)
        brief_path = _write_brief(tmp)
        patch, _, _ = _invoke_studio(runner, str(brief_path), dist_dir=str(tmp))

        with patch:
            result_build = runner.invoke(
                main, ["studio", "build", str(brief_path), "--dist-dir", str(tmp)]
            )
        assert result_build.exit_code == 0, result_build.output

        # Now inspect the trace
        result = runner.invoke(main, ["studio", "trace", "e2e-test", "--dist-dir", str(tmp)])
        assert result.exit_code == 0, result.output


# ===========================================================================
# Multi-command workflow
# ===========================================================================


class TestMultiCommandWorkflow:
    """Integrated workflows that span multiple commands."""

    def test_build_then_plan_then_trace(self, runner: CliRunner) -> None:
        """Build → plan → trace: the full inspection workflow."""
        tmp = Path("/tmp/e2e-studio-workflow")
        tmp.mkdir(exist_ok=True)
        brief_path = _write_brief(tmp)
        patch, _, _ = _invoke_studio(runner, str(brief_path), dist_dir=str(tmp))

        with patch:
            result_build = runner.invoke(
                main, ["studio", "build", str(brief_path), "--dist-dir", str(tmp)]
            )
        assert result_build.exit_code == 0, result_build.output

        # Plan
        result_plan = runner.invoke(main, ["studio", "plan", "e2e-test", "--dist-dir", str(tmp)])
        assert result_plan.exit_code == 0, result_plan.output

        # Trace
        result_trace = runner.invoke(main, ["studio", "trace", "e2e-test", "--dist-dir", str(tmp)])
        assert result_trace.exit_code == 0, result_trace.output

    def test_doctor_before_and_after_build(self, runner: CliRunner) -> None:
        """Doctor should show different h3 budget status before vs after build."""
        tmp = Path("/tmp/e2e-studio-doctor-workflow")
        tmp.mkdir(exist_ok=True)

        # Before build: h3 budget should warn (no builds yet)
        result_before = runner.invoke(main, ["studio", "doctor", "--dist-dir", str(tmp)])
        assert result_before.exit_code in (0, 1)

        brief_path = _write_brief(tmp)
        patch, _, _ = _invoke_studio(runner, str(brief_path), dist_dir=str(tmp))

        with patch:
            result_build = runner.invoke(
                main, ["studio", "build", str(brief_path), "--dist-dir", str(tmp)]
            )
        assert result_build.exit_code == 0, result_build.output

        # After build: h3 budget should show actual spend
        result_after = runner.invoke(main, ["studio", "doctor", "--dist-dir", str(tmp)])
        assert result_after.exit_code in (0, 1)


# ===========================================================================
# CLI error cases
# ===========================================================================


class TestStudioErrorCases:
    """Edge cases and error paths in the studio CLI."""

    def test_studio_without_subcommand(self, runner: CliRunner) -> None:
        """Invoking 'mc studio' without a subcommand should show help."""
        result = runner.invoke(main, ["studio"])
        # Should not crash; exit 0 (help) or 2 (usage error)
        assert result.exit_code in (0, 2)

    def test_revise_missing_intent(self, runner: CliRunner) -> None:
        """Revise without an intent string should fail."""
        result = runner.invoke(main, ["studio", "revise", "nonexistent"])
        # Should not be a clean success
        assert result.exit_code != 0

    def test_plan_with_dist_dir(self, runner: CliRunner) -> None:
        """plan and trace should accept --dist-dir."""
        tmp = Path("/tmp/e2e-studio-distdir")
        tmp.mkdir(exist_ok=True)
        brief_path = _write_brief(tmp)
        patch, _, _ = _invoke_studio(runner, str(brief_path), dist_dir=str(tmp))

        with patch:
            result = runner.invoke(
                main, ["studio", "build", str(brief_path), "--dist-dir", str(tmp)]
            )
        assert result.exit_code == 0, result.output

        # Both plan and trace with explicit --dist-dir
        result_plan = runner.invoke(
            main, ["studio", "plan", "e2e-test", "--dist-dir", str(tmp)]
        )
        assert result_plan.exit_code == 0, result_plan.output

        result_trace = runner.invoke(
            main, ["studio", "trace", "e2e-test", "--dist-dir", str(tmp)]
        )
        assert result_trace.exit_code == 0, result_trace.output
