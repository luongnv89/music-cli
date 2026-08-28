"""Tests for the audio build doctor checks."""

from __future__ import annotations

from unittest import mock

from click.testing import CliRunner

from music_cli.cli import main
from music_cli.studio.doctor import CheckResult, check_dist_dir, check_gmi_key


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
