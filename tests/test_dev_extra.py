"""Regression tests for the ``dev`` optional-dependency extra.

Issue #44 (Task 1.1) establishes the advisory baseline by adding ``pip-audit`` to
the ``dev`` extra and running it in CI. The exit condition for milestone ``M1``
("0 High or Critical advisories") is only measurable while ``pip-audit`` remains
declared, so this guards the declaration against accidental removal.
"""

from __future__ import annotations

from pathlib import Path

import tomllib

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"


def _load_pyproject() -> dict:
    with _PYPROJECT.open("rb") as f:
        return tomllib.load(f)


def test_dev_extra_declares_pip_audit() -> None:
    """The ``dev`` extra must declare ``pip-audit`` (issue #44, M1 baseline)."""
    pyproject = _load_pyproject()
    dev_deps = pyproject["project"]["optional-dependencies"]["dev"]

    declared = {
        dep.split("[", 1)[0].split(">", 1)[0].split("=", 1)[0].split("<", 1)[0].strip().lower()
        for dep in dev_deps
    }
    assert "pip-audit" in declared, (
        "pip-audit must remain in [project.optional-dependencies] dev — it is the "
        "M1 advisory baseline; removing it makes M1's exit condition unmeasurable."
    )


def test_dev_extra_declares_core_dev_tools() -> None:
    """Guard against accidental removal of the other established dev tools."""
    pyproject = _load_pyproject()
    dev_deps = pyproject["project"]["optional-dependencies"]["dev"]

    declared = {
        dep.split("[", 1)[0].split(">", 1)[0].split("=", 1)[0].split("<", 1)[0].strip().lower()
        for dep in dev_deps
    }
    expected = {"pytest", "pytest-cov", "ruff", "mypy", "bandit", "pre-commit", "pip-audit"}
    missing = expected - declared
    assert not missing, f"dev extra lost required tools: {sorted(missing)}"
