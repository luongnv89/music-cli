"""Guard the supported-Python-floor decision (Task 3.1 / #58, F-DEP-001).

Every declaration site must name the same floor: `requires-python`, the
trove classifiers, `[tool.ruff] target-version`, `[tool.mypy]
python_version`, and the CI matrix. (`[tool.black]` was removed with
F-CLEAN-009; ruff format is the single formatter.)
"""

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYPROJECT = REPO / "pyproject.toml"
CI_YML = REPO / ".github" / "workflows" / "ci.yml"

FLOOR = "3.12"


def _load_pyproject() -> dict:
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


def test_requires_python_names_floor() -> None:
    data = _load_pyproject()
    assert data["project"]["requires-python"] == f">={FLOOR}"


def test_classifiers_list_floor_and_above_only() -> None:
    data = _load_pyproject()
    py_cls = sorted(
        c
        for c in data["project"]["classifiers"]
        if c.startswith("Programming Language :: Python :: 3.")
    )
    floor_minor = int(FLOOR.split(".")[1])
    for c in py_cls:
        minor = int(c.rsplit("::", 1)[1].strip().split(".")[1])
        assert minor >= floor_minor, f"classifier below floor: {c}"
    assert any(c.endswith(FLOOR) for c in py_cls), "floor classifier missing"


def _tool_target(tool: str) -> str:
    text = PYPROJECT.read_text()
    m = re.search(rf"\[tool\.{tool}\]\n(?:.*\n)*?target-version\s*=\s*(.+)", text)
    assert m, f"[tool.{tool}] target-version not found"
    return m.group(1)


def test_ruff_target_version_names_floor() -> None:
    assert f"py{FLOOR.replace('.', '')}" in _tool_target("ruff")


def test_mypy_python_version_names_floor() -> None:
    text = PYPROJECT.read_text()
    m = re.search(r'\[tool\.mypy\]\n(?:.*\n)*?python_version\s*=\s*"([\d.]+)"', text)
    assert m, "[tool.mypy] python_version not found"
    assert m.group(1) == FLOOR


def test_ci_matrix_covers_floor_and_admits_nothing_below() -> None:
    text = CI_YML.read_text()
    m = re.search(r"python-version:\s*\[([^\]]+)\]", text)
    assert m, "CI matrix python-version list not found"
    versions = [v.strip().strip('"').strip("'") for v in m.group(1).split(",")]
    floor_minor = int(FLOOR.split(".")[1])
    assert min(int(v.split(".")[1]) for v in versions) >= floor_minor
    assert FLOOR in versions


def test_no_standalone_ci_job_below_floor() -> None:
    text = CI_YML.read_text()
    pins = re.findall(r'python-version:\s*"([\d.]+)"', text)
    floor_minor = int(FLOOR.split(".")[1])
    below = [p for p in pins if int(p.split(".")[1]) < floor_minor]
    assert not below, f"standalone CI jobs below the floor: {below}"
