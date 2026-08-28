"""Preflight checks for the audio-only studio build."""

from __future__ import annotations

import os
import socket
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from .nodes.ffmpeg import DEFAULT_FFMPEG, DEFAULT_FFPROBE, resolve_binary
from .trace import DEFAULT_DIST_DIR

CheckStatus = Literal["OK", "WARN", "FAIL"]


def _check_network(host: str, port: int = 443, timeout: float = 3.0) -> tuple[bool, float]:
    """Ping *host*:*port* and return ``(success, latency_ms)``."""
    try:
        start = socket.gethostbyname(host)
    except socket.gaierror:
        return False, 0.0
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        _gettimeofday = getattr(socket, "gettimeofday", None)
        if _gettimeofday:
            t0 = _gettimeofday()
            sock.connect((start, port))
            t1 = _gettimeofday()
            latency_ms = (t1 - t0) / 1000
        else:
            t0 = time.monotonic()
            sock.connect((start, port))
            t1 = time.monotonic()
            latency_ms = (t1 - t0) * 1000
        return True, latency_ms
    except Exception:
        return False, 0.0
    finally:
        sock.close()


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
    """Check for a configured GMI credential without exposing its value.

    When the ``gmi`` extra (``keyring``) is not installed the check reports
    ``WARN`` rather than ``FAIL`` so that a base install of music-cli still
    passes the doctor with a clean exit code.
    """
    try:
        from ..cloud.secrets import get_api_key

        api_key = get_api_key("gmi")
    except Exception as exc:
        return CheckResult(
            "gmi key",
            "WARN",
            f"gmi extra not installed ({exc}); install with pip install 'coder-music-cli[gmi]'",
            "Install the gmi extra and run: mc cloud key set gmi",
        )
    if not api_key:
        return CheckResult(
            "gmi key",
            "WARN",
            "no GMI Cloud API key is stored (optional for doctor; required for cloud builds)",
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


def check_openrouter_key() -> CheckResult:
    """Check for an optional OpenRouter API key.

    OpenRouter is used as a fallback provider for text-model requests.
    The build can proceed without it, so this check reports ``WARN`` when
    the key is absent rather than ``FAIL``.
    """
    try:
        from ..cloud.secrets import get_api_key

        api_key = get_api_key("openrouter")
    except Exception as exc:
        return CheckResult(
            "openrouter key",
            "WARN",
            f"could not read the OS keyring: {exc}",
            "Install the gmi extra and run: mc cloud key set openrouter",
        )
    if not api_key:
        return CheckResult(
            "openrouter key",
            "WARN",
            "no OpenRouter key is stored (optional)",
            "Run: mc cloud key set openrouter",
        )
    return CheckResult("openrouter key", "OK", "stored in the OS keyring")


def check_h3_budget(dist_dir: str | Path = DEFAULT_DIST_DIR) -> CheckResult:
    """Check the H3 build budget from the latest manifest.

    Reads the ``budget`` block from the most recently written manifest
    under *dist_dir*.  When no manifest exists the build has not run yet,
    so we report ``WARN`` with the default per-build cap.
    """
    dist = Path(dist_dir)
    if not dist.is_dir():
        return CheckResult(
            "h3 budget",
            "WARN",
            "no build has run yet; default cap applies",
            "Run a build to see actual spend; cap defaults to $1.00 per build.",
        )

    try:
        from ..studio.schemas import ProjectManifest
    except ImportError:
        return CheckResult(
            "h3 budget",
            "WARN",
            "budget schema unavailable; skipping check",
            "",
        )

    # Walk dist/ for the latest manifest (by mtime).
    candidates: list[tuple[float, Path]] = []
    for child in dist.iterdir():
        if child.is_dir():
            manifest_path = child / "manifest.yaml"
            if manifest_path.exists():
                try:
                    candidates.append((manifest_path.stat().st_mtime, manifest_path))
                except OSError:
                    pass
    if not candidates:
        return CheckResult(
            "h3 budget",
            "WARN",
            "no build manifest found; default cap applies",
            "Run a build to see actual spend; cap defaults to $1.00 per build.",
        )

    _, latest = max(candidates, key=lambda c: c[0])
    try:
        from ..studio.trace import load_plan_yaml

        data = load_plan_yaml(latest)
        if isinstance(data, dict):
            manifest = ProjectManifest(data)
        else:
            return CheckResult(
                "h3 budget",
                "WARN",
                "manifest could not be parsed; default cap applies",
                "",
            )
    except Exception:
        return CheckResult(
            "h3 budget",
            "WARN",
            "could not read manifest; default cap applies",
            "",
        )

    manifest_dict = manifest.to_dict() if hasattr(manifest, "to_dict") else manifest
    budget_data = manifest_dict.get("budget")
    if not budget_data:
        return CheckResult(
            "h3 budget",
            "WARN",
            "no budget block in manifest; default cap applies",
            "Run a build to see actual spend; cap defaults to $1.00 per build.",
        )

    # The custom YAML parser may flatten nested budget into a list of
    # {key, value} pairs; handle both dict and list forms.
    if isinstance(budget_data, dict):
        cap_val = budget_data.get("cap", budget_data.get("per_build_cap", 1.0))
        spent_val = budget_data.get("spent", 0)
        currency = budget_data.get("currency", "USD")
    elif isinstance(budget_data, list):
        cap_val = 1.0
        spent_val = 0
        currency = "USD"
        for entry in budget_data:
            if isinstance(entry, dict):
                if "cap" in entry:
                    cap_val = entry["cap"]
                if "per_build_cap" in entry:
                    cap_val = entry["per_build_cap"]
                if "spent" in entry:
                    spent_val = entry["spent"]
                if "currency" in entry:
                    currency = entry["currency"]
    else:
        return CheckResult(
            "h3 budget",
            "WARN",
            "budget block has unexpected format; default cap applies",
            "Run a build to see actual spend; cap defaults to $1.00 per build.",
        )

    cap = Decimal(str(cap_val))
    spent = Decimal(str(spent_val))
    remaining = cap - spent

    if remaining < 0:
        return CheckResult(
            "h3 budget",
            "FAIL",
            f"spent {currency} {float(spent):.2f} / cap {currency} {float(cap):.2f}",
            "Remove old projects from dist/ or increase the cap with --confirm.",
        )
    if remaining <= Decimal("0.10"):
        return CheckResult(
            "h3 budget",
            "WARN",
            f"{currency} {float(remaining):.2f} remaining of {currency} {float(cap):.2f} cap",
            "Remove old projects from dist/ or pass --confirm to exceed the cap.",
        )
    return CheckResult(
        "h3 budget",
        "OK",
        f"{currency} {float(remaining):.2f} remaining of {currency} {float(cap):.2f} cap",
        "",
    )


def check_network() -> CheckResult:
    """Ping the GMI Cloud API endpoint to verify network connectivity."""
    from ..cloud.gmi import GMI_SERVING_CHAT_URL

    parsed = GMI_SERVING_CHAT_URL
    # Extract host from URL (e.g. https://api.gmi-serving.com/v1/...)
    host = parsed.replace("https://", "").replace("http://", "").split("/")[0]
    success, latency_ms = _check_network(host, 443)
    if not success:
        return CheckResult(
            "network",
            "FAIL",
            f"cannot reach {host}",
            "Check your internet connection or proxy settings.",
        )
    return CheckResult(
        "network",
        "OK",
        f"{host} reachable ({latency_ms:.0f} ms)",
        "",
    )


def check_disk_space(dist_dir: str | Path = DEFAULT_DIST_DIR) -> CheckResult:
    """Check available disk space on the volume holding *dist_dir*."""
    path = Path(dist_dir).resolve()
    try:
        stat = os.statvfs(str(path))
        free_bytes = stat.f_bavail * stat.f_frsize
        free_gb = free_bytes / (1024**3)
    except OSError:
        return CheckResult(
            "disk space",
            "WARN",
            "could not determine available disk space",
            "",
        )
    # The audio-only build typically produces < 500 MB per project.
    # Require at least 500 MB free.
    if free_gb < 0.5:
        return CheckResult(
            "disk space",
            "FAIL",
            f"only {free_gb:.2f} GB free (need ~0.5 GB)",
            "Free disk space or choose a different --dist-dir.",
        )
    if free_gb < 2.0:
        return CheckResult(
            "disk space",
            "WARN",
            f"{free_gb:.2f} GB free (recommend >= 2 GB)",
            "Consider freeing disk space for larger builds.",
        )
    return CheckResult("disk space", "OK", f"{free_gb:.1f} GB available")


def run_doctor(dist_dir: str | Path = DEFAULT_DIST_DIR) -> list[CheckResult]:
    """Run all preflight checks for a studio build."""
    return [
        check_ffmpeg(),
        check_ffprobe(),
        check_gmi_key(),
        check_openrouter_key(),
        check_h3_budget(dist_dir),
        check_network(),
        check_disk_space(dist_dir),
    ]


__all__ = [
    "CheckResult",
    "CheckStatus",
    "check_disk_space",
    "check_dist_dir",
    "check_ffmpeg",
    "check_ffprobe",
    "check_gmi_key",
    "check_h3_budget",
    "check_network",
    "check_openrouter_key",
    "run_doctor",
]
