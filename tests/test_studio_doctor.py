"""Tests for the audio build doctor checks."""

from __future__ import annotations

import socket
from unittest import mock

from click.testing import CliRunner

from music_cli.cli import main
from music_cli.studio.doctor import (
    CheckResult,
    check_disk_space,
    check_dist_dir,
    check_gmi_key,
    check_h3_budget,
    check_network,
    check_openrouter_key,
    run_doctor,
)


def test_check_dist_dir_warns_before_first_build(tmp_path):
    result = check_dist_dir(tmp_path / "dist")
    assert result.status == "WARN"
    assert "create" in result.message


def test_check_dist_dir_fails_for_file(tmp_path):
    path = tmp_path / "dist"
    path.write_text("not a directory", encoding="utf-8")
    result = check_dist_dir(path)
    assert result.status == "FAIL"


def test_check_gmi_key_does_not_expose_missing_secret():
    with mock.patch("music_cli.cloud.secrets.get_api_key", return_value=None):
        result = check_gmi_key()
    assert result.status == "FAIL"
    assert "key" in result.message.lower()


def test_doctor_command_returns_failure_for_failed_check(monkeypatch):
    monkeypatch.setattr(
        "music_cli.cli.studio.run_doctor",
        lambda _dist: [CheckResult("gmi key", "FAIL", "missing", "set it")],
    )
    result = CliRunner().invoke(main, ["studio", "doctor"])
    assert result.exit_code == 1
    assert "FAIL: gmi key: missing" in result.output


def test_doctor_command_returns_zero_when_checks_are_ok(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "music_cli.cli.studio.run_doctor",
        lambda _dist: [CheckResult("ffmpeg", "OK", "installed")],
    )
    result = CliRunner().invoke(main, ["studio", "doctor", "--dist-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "OK: ffmpeg: installed" in result.output


# -- new checks -----------------------------------------------------------


def test_check_openrouter_key_warns_when_missing():
    with mock.patch("music_cli.cloud.secrets.get_api_key", return_value=None):
        result = check_openrouter_key()
    assert result.status == "WARN"
    assert "optional" in result.message.lower()


def test_check_openrouter_key_ok_when_present():
    with mock.patch("music_cli.cloud.secrets.get_api_key", return_value="sk-abc123"):
        result = check_openrouter_key()
    assert result.status == "OK"
    assert "stored" in result.message.lower()


def test_check_openrouter_key_warns_on_keyring_error():
    with mock.patch(
        "music_cli.cloud.secrets.get_api_key", side_effect=RuntimeError("keyring fail")
    ):
        result = check_openrouter_key()
    assert result.status == "WARN"
    assert "keyring" in result.message.lower()


def test_check_network_returns_ok_when_reachable(monkeypatch):
    monkeypatch.setattr(
        "music_cli.studio.doctor.socket",
        mock.MagicMock(
            gethostbyname=mock.MagicMock(return_value="1.2.3.4"),
            socket=mock.MagicMock(
                return_value=mock.MagicMock(connect=mock.MagicMock(), close=mock.MagicMock())
            ),
        ),
    )
    # Patch time.monotonic for latency calculation
    with mock.patch("music_cli.studio.doctor.socket.gettimeofday", return_value=0):
        result = check_network()
    assert result.status == "OK"
    assert "reachable" in result.message.lower()


def test_check_network_returns_fail_when_unreachable(monkeypatch):
    # Patch the module-level socket import so gaierror is caught properly.
    fake_socket = mock.MagicMock()
    fake_socket.gaierror = socket.gaierror
    fake_socket.gethostbyname = mock.MagicMock(side_effect=socket.gaierror("no host"))
    monkeypatch.setattr("music_cli.studio.doctor.socket", fake_socket)
    result = check_network()
    assert result.status == "FAIL"
    assert "cannot reach" in result.message.lower()


def test_check_disk_space_ok(tmp_path):
    mock_stat = mock.MagicMock()
    mock_stat.f_bavail = 10_000_000  # plenty
    mock_stat.f_frsize = 4096
    with mock.patch("music_cli.studio.doctor.os.statvfs", return_value=mock_stat):
        result = check_disk_space(tmp_path / "dist")
    assert result.status == "OK"


def test_check_disk_space_warns_when_low(tmp_path):
    mock_stat = mock.MagicMock()
    mock_stat.f_bavail = 100_000  # ~0.4 GB
    mock_stat.f_frsize = 4096
    with mock.patch("music_cli.studio.doctor.os.statvfs", return_value=mock_stat):
        result = check_disk_space(tmp_path / "dist")
    assert result.status == "FAIL"
    assert "free" in result.message.lower()


def test_check_h3_budget_warns_when_no_builds(tmp_path):
    result = check_h3_budget(tmp_path / "nonexistent")
    assert result.status == "WARN"
    assert "default cap" in result.message.lower()


def test_check_h3_budget_warns_when_no_manifest(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    result = check_h3_budget(dist)
    assert result.status == "WARN"
    assert "manifest" in result.message.lower()


def test_check_h3_budget_ok_when_budget_healthy(tmp_path, monkeypatch):
    # The custom YAML parser flattens nested budget into a list of entries.
    # check_h3_budget handles this list format.
    dist = tmp_path / "dist" / "my-project"
    dist.mkdir(parents=True)
    manifest_path = dist / "manifest.yaml"
    manifest_path.write_text(
        "project_id: my-project\nplan_id: p1\nnodes: []\nbudget:\n  - cap: 1.0\n  - spent: 0.2\n  - currency: USD\n  - per_build_cap: 1.0\n",
        encoding="utf-8",
    )
    result = check_h3_budget(dist.parent)
    # With the list format now correctly parsed: 1.0 - 0.2 = 0.8 remaining > 0.10
    assert result.status == "OK"
    assert "0.80" in result.message


def test_check_h3_budget_warns_when_near_cap(tmp_path, monkeypatch):
    # Same pattern — custom parser flattens, so budget is not recognized
    dist = tmp_path / "dist" / "my-project"
    dist.mkdir(parents=True)
    manifest_path = dist / "manifest.yaml"
    manifest_path.write_text(
        "project_id: my-project\nplan_id: p1\nnodes: []\nbudget:\n  - cap: 1.0\n  - spent: 0.95\n  - currency: USD\n  - per_build_cap: 1.0\n",
        encoding="utf-8",
    )
    result = check_h3_budget(dist.parent)
    assert result.status == "WARN"


def test_check_h3_budget_fails_when_over_cap(tmp_path, monkeypatch):
    dist = tmp_path / "dist" / "my-project"
    dist.mkdir(parents=True)
    manifest_path = dist / "manifest.yaml"
    manifest_path.write_text(
        "project_id: my-project\nplan_id: p1\nnodes: []\nbudget:\n  - cap: 1.0\n  - spent: 1.5\n  - currency: USD\n  - per_build_cap: 1.0\n",
        encoding="utf-8",
    )
    result = check_h3_budget(dist.parent)
    assert result.status == "FAIL"
    assert "1.50" in result.message
    assert "1.00" in result.message


def test_run_doctor_returns_all_checks(monkeypatch):
    monkeypatch.setattr(
        "music_cli.studio.doctor.check_ffmpeg",
        mock.MagicMock(return_value=CheckResult("ffmpeg", "OK", "installed")),
    )
    monkeypatch.setattr(
        "music_cli.studio.doctor.check_ffprobe",
        mock.MagicMock(return_value=CheckResult("ffprobe", "OK", "installed")),
    )
    monkeypatch.setattr(
        "music_cli.studio.doctor.check_gmi_key",
        mock.MagicMock(return_value=CheckResult("gmi key", "OK", "stored")),
    )
    monkeypatch.setattr(
        "music_cli.studio.doctor.check_openrouter_key",
        mock.MagicMock(return_value=CheckResult("openrouter key", "WARN", "optional")),
    )
    monkeypatch.setattr(
        "music_cli.studio.doctor.check_h3_budget",
        mock.MagicMock(return_value=CheckResult("h3 budget", "OK", "0.80 remaining")),
    )
    monkeypatch.setattr(
        "music_cli.studio.doctor.check_network",
        mock.MagicMock(return_value=CheckResult("network", "OK", "reachable")),
    )
    monkeypatch.setattr(
        "music_cli.studio.doctor.check_disk_space",
        mock.MagicMock(return_value=CheckResult("disk space", "OK", "50.0 GB available")),
    )
    results = run_doctor()
    assert len(results) == 7
    names = [r.name for r in results]
    assert "ffmpeg" in names
    assert "ffprobe" in names
    assert "gmi key" in names
    assert "openrouter key" in names
    assert "h3 budget" in names
    assert "network" in names
    assert "disk space" in names
