"""Preflight checks for the audio-only studio build."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .nodes.ffmpeg import DEFAULT_FFMPEG, DEFAULT_FFPROBE, resolve_binary
from .trace import DEFAULT_DIST_DIR

CheckStatus = Literal["OK", "WARN", "FAIL"]


@dataclass(frozen=True)
class CheckResult:
    """One doctor check result suitable for CLI rendering."""

    name: str
    status: CheckStatus
    message: str
    fix: str = ""


def check_ffmpeg() -> CheckResult:
    """Check that the audio encoder is available."""
    try:
        binary = resolve_binary(DEFAULT_FFMPEG)
    except Exception as exc:
        return CheckResult(
            "ffmpeg",
            "FAIL",
            str(exc),
            "Install FFmpeg and ensure it is on PATH.",
        )
    return CheckResult("ffmpeg", "OK", f"installed at {binary}")


def check_ffprobe() -> CheckResult:
    """Check that audio metadata probing is available."""
    try:
        binary = resolve_binary(DEFAULT_FFPROBE)
    except Exception as exc:
        return CheckResult(
            "ffprobe",
            "FAIL",
            str(exc),
            "Install FFmpeg (which includes ffprobe) and ensure it is on PATH.",
        )
    return CheckResult("ffprobe", "OK", f"installed at {binary}")


def check_gmi_key() -> CheckResult:
    """Check for a configured GMI credential without exposing its value."""
    try:
        from ..cloud.secrets import get_api_key

        api_key = get_api_key("gmi")
    except Exception as exc:
        return CheckResult(
            "gmi key",
            "FAIL",
            f"could not read the OS keyring: {exc}",
            "Install the gmi extra and run: mc cloud key set gmi",
        )
    if not api_key:
        return CheckResult(
            "gmi key",
            "FAIL",
            "no GMI Cloud API key is stored",
            "Run: mc cloud key set gmi",
        )
    return CheckResult("gmi key", "OK", "stored in the OS keyring")


def check_dist_dir(dist_dir: str | Path = DEFAULT_DIST_DIR) -> CheckResult:
    """Check that the build output directory exists or can be created."""
    path = Path(dist_dir)
    if path.exists():
        if not path.is_dir():
            return CheckResult(
                "dist directory",
                "FAIL",
                f"{path} exists but is not a directory",
                "Choose a directory with --dist-dir or move the conflicting file.",
            )
        if not os.access(path, os.W_OK):
            return CheckResult(
                "dist directory",
                "FAIL",
                f"{path} is not writable",
                "Choose a writable directory with --dist-dir.",
            )
        return CheckResult("dist directory", "OK", f"writable: {path}")

    parent = path.parent if path.parent != Path() else Path()
    if parent.exists() and os.access(parent, os.W_OK):
        return CheckResult(
            "dist directory",
            "WARN",
            f"{path} does not exist yet; the build will create it",
            f"Create it with: mkdir -p {path}",
        )
    return CheckResult(
        "dist directory",
        "FAIL",
        f"{path} cannot be created from {parent}",
        "Choose a writable directory with --dist-dir.",
    )


def run_doctor(dist_dir: str | Path = DEFAULT_DIST_DIR) -> list[CheckResult]:
    """Run all checks required before an audio-only build."""
    return [check_ffmpeg(), check_ffprobe(), check_gmi_key(), check_dist_dir(dist_dir)]


__all__ = [
    "CheckResult",
    "CheckStatus",
    "check_dist_dir",
    "check_ffmpeg",
    "check_ffprobe",
    "check_gmi_key",
    "run_doctor",
]
