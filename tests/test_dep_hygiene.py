"""Regression tests for dependency-hygiene metadata in ``pyproject.toml``.

Covers issues #54 (prune orphaned dependencies), #56 (raise the yt-dlp floor),
and #57 (correct the Python classifiers).
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_CI_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _load_pyproject() -> dict:
    with _PYPROJECT.open("rb") as f:
        return tomllib.load(f)


def _declared_names(deps: list[str]) -> set[str]:
    return {
        dep.split("[", 1)[0]
        .split(">", 1)[0]
        .split("=", 1)[0]
        .split("<", 1)[0]
        .split(";", 1)[0]
        .strip()
        .lower()
        for dep in deps
    }


# ---------------------------------------------------------------------------
# Issue #54 — prune the orphaned dependencies
# ---------------------------------------------------------------------------


def test_no_orphaned_media_controller_dependencies() -> None:
    """dbus-next and winrt-Windows.Media.Playback must stay removed (#54)."""
    pyproject = _load_pyproject()
    declared = _declared_names(pyproject["project"]["dependencies"])
    assert "dbus-next" not in declared
    assert "winrt-windows.media.playback" not in declared


def test_no_orphaned_ai_extra_dependencies() -> None:
    """accelerate and soundfile have no import sites and must stay removed (#54)."""
    pyproject = _load_pyproject()
    extras = pyproject["project"]["optional-dependencies"]
    for extra in ("ai", "minimax"):
        declared = _declared_names(extras[extra])
        assert "accelerate" not in declared, f"accelerate re-added to {extra}"
        assert "soundfile" not in declared, f"soundfile re-added to {extra}"


def test_diffusers_floor_matches_code_requirements() -> None:
    """The ai extra's diffusers floor must require the ModularPipeline era (#54)."""
    pyproject = _load_pyproject()
    ai_deps = pyproject["project"]["optional-dependencies"]["ai"]
    diffusers = [d for d in ai_deps if d.lower().startswith("diffusers")]
    assert diffusers, "ai extra must declare diffusers"
    match = re.search(r">=\s*(\d+)\.(\d+)", diffusers[0])
    assert match, f"cannot parse diffusers floor: {diffusers[0]}"
    major, minor = int(match.group(1)), int(match.group(2))
    assert (major, minor) >= (0, 39), (
        f"diffusers floor {major}.{minor} is below 0.39 (ModularPipeline)"
    )


def test_removed_packages_have_no_import_sites() -> None:
    """No source file may import any of the pruned packages (#54 verify step)."""
    banned = ("dbus", "winrt", "accelerate", "soundfile")
    offenders: list[str] = []
    for path in (_REPO_ROOT / "music_cli").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if re.match(r"(from|import)\s+", stripped):
                if any(pkg in stripped.lower() for pkg in banned):
                    offenders.append(f"{path.relative_to(_REPO_ROOT)}: {stripped}")
    assert not offenders, f"banned imports found: {offenders}"


# ---------------------------------------------------------------------------
# Issue #56 — raise the yt-dlp floor
# ---------------------------------------------------------------------------


def test_yt_dlp_floor_is_recent() -> None:
    """The youtube extra must pin a recent yt-dlp release (#56)."""
    pyproject = _load_pyproject()
    yt_deps = pyproject["project"]["optional-dependencies"]["youtube"]
    entries = [d for d in yt_deps if d.lower().startswith("yt-dlp")]
    assert entries, "youtube extra must declare yt-dlp"
    match = re.search(r">=\s*(\d{4})\.(\d+)\.(\d+)", entries[0])
    assert match, f"cannot parse yt-dlp floor: {entries[0]}"
    year = int(match.group(1))
    # The old floor was 2023.1.0; anything from before 2026 cannot be trusted
    # to still extract from YouTube.
    assert year >= 2026, f"yt-dlp floor {match.group(0)} is too old"


def test_yt_dlp_floor_documented_with_comment() -> None:
    """The chosen yt-dlp version must be recorded in a comment beside it (#56)."""
    text = _PYPROJECT.read_text(encoding="utf-8")
    youtube_section = text.split("youtube =", 1)[1].split("]", 1)[0]
    assert "#" in youtube_section, "yt-dlp floor must carry an explanatory comment"


# ---------------------------------------------------------------------------
# Issue #57 — correct the Python classifiers
# ---------------------------------------------------------------------------


def _ci_matrix_versions() -> set[str]:
    text = _CI_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"python-version:\s*\[([^\]]+)\]", text)
    assert match, "CI matrix python-version list not found"
    return set(re.findall(r'"(\d+\.\d+)"', match.group(1)))


def test_classifiers_match_requires_python_and_ci_matrix() -> None:
    """Classifiers, requires-python, and the CI matrix must all agree (#57)."""
    pyproject = _load_pyproject()
    requires_python = pyproject["project"]["requires-python"]
    match = re.search(r">=\s*(\d+)\.(\d+)", requires_python)
    assert match, f"cannot parse requires-python: {requires_python}"
    floor = (int(match.group(1)), int(match.group(2)))

    classifiers = [
        c.split("::")[-1].strip()
        for c in pyproject["project"]["classifiers"]
        if c.startswith("Programming Language :: Python :: 3.")
    ]
    classifier_versions = {(int(v.split(".")[0]), int(v.split(".")[1])) for v in classifiers}
    matrix_versions = {(int(v.split(".")[0]), int(v.split(".")[1])) for v in _ci_matrix_versions()}

    assert classifier_versions == matrix_versions, (
        f"classifiers {sorted(classifier_versions)} != CI matrix {sorted(matrix_versions)}"
    )
    assert min(classifier_versions) == floor, (
        f"lowest classifier {min(classifier_versions)} != requires-python floor {floor}"
    )
