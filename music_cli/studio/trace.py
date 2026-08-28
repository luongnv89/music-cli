"""Per-project decision log and on-disk layout for the studio build (#136).

Every phase of a build — plan, generate, probe, repair, assemble — appends
one JSON line to ``dist/<project>/trace.jsonl`` so a session can be audited
after the fact. :class:`TraceWriter` is an append-only context manager::

    with TraceWriter(proj_dir / "trace.jsonl") as trace:
        trace.write(step="generate", node_id="scene-3", payload=node_json)

Each line carries ``ts``, ``step``, ``model``, ``node_id``, ``latency_ms``
and ``payload_hash``; extra keyword fields such as ``retries`` or ``ok`` pass
straight through. Lines are append-only; rotation is not needed (a premiere
build produces ~50 lines).

The module also owns the ``dist/<project>/`` layout (``plan.yaml``,
``trace.jsonl``, ``nodes/``, ``premiere.mp4``), a minimal YAML dumper/loader
for plans, and the human-readable table renderer used by
``mc studio trace <project>``.

Like :mod:`music_cli.studio.schemas`, this module is stdlib-only.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

# ---------------------------------------------------------------------------
# dist/<project>/ layout (P2.2 spec)
# ---------------------------------------------------------------------------

PLAN_FILENAME = "plan.yaml"
TRACE_FILENAME = "trace.jsonl"
NODES_DIRNAME = "nodes"
PREMIERE_FILENAME = "premiere.mp4"

#: Default parent directory for build projects (gitignored).
DEFAULT_DIST_DIR = Path("dist")


def project_dir(dist_dir: str | Path, project_id: str) -> Path:
    """Return ``dist/<project_id>/`` without creating it."""
    return Path(dist_dir) / project_id


def init_project_layout(dist_dir: str | Path, project_id: str) -> Path:
    """Create the skeleton of a build project under ``dist_dir``.

    Creates the project directory, the ``nodes/`` subdirectory and an empty
    ``trace.jsonl``. ``plan.yaml`` and ``premiere.mp4`` appear once the plan
    is dumped and the premiere is rendered. Returns the project directory.
    """
    proj = project_dir(dist_dir, project_id)
    proj.mkdir(parents=True, exist_ok=True)
    (proj / NODES_DIRNAME).mkdir(exist_ok=True)
    trace_path = proj / TRACE_FILENAME
    if not trace_path.exists():
        trace_path.touch()
    return proj


def project_paths(proj_dir: str | Path) -> dict[str, Path]:
    """Return the four spec'd paths of a build project, keyed by filename."""
    proj = Path(proj_dir)
    return {
        PLAN_FILENAME: proj / PLAN_FILENAME,
        TRACE_FILENAME: proj / TRACE_FILENAME,
        NODES_DIRNAME: proj / NODES_DIRNAME,
        PREMIERE_FILENAME: proj / PREMIERE_FILENAME,
    }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# TraceWriter
# ---------------------------------------------------------------------------


class TraceWriter:
    """Append-only JSONL decision log (#136).

    Usable as a context manager (one open append handle for the session) or
    standalone (each :meth:`append` opens the file in append mode and closes
    it again, which is how the async :class:`~music_cli.studio.director
    .M3Director` writes across awaits).
    """

    def __init__(self, path: str | Path, *, model: str = "MiniMax-M3") -> None:
        self.path = Path(path)
        self.model = model
        self._fh: TextIO | None = None

    # -- context-manager protocol ------------------------------------------

    def __enter__(self) -> TraceWriter:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
        return False  # never swallow exceptions

    # -- writing ------------------------------------------------------------

    def append(
        self,
        *,
        step: str,
        node_id: str | None = None,
        latency_ms: float | None = None,
        payload: str | None = None,
        payload_hash: str | None = None,
        **extra: Any,
    ) -> str | None:
        """Append one JSON line; return the ``payload_hash`` written.

        ``payload_hash`` defaults to the SHA-256 of ``payload``. Extra
        keyword arguments (``retries``, ``ok``, ``input_hash`` …) are added
        to the record verbatim.
        """
        if payload_hash is None and payload is not None:
            payload_hash = _sha256(payload)
        record: dict[str, Any] = {
            "ts": _now_iso(),
            "step": step,
            "model": self.model,
            "node_id": node_id,
            "latency_ms": latency_ms,
            "payload_hash": payload_hash,
        }
        record.update(extra)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        if self._fh is not None:
            self._fh.write(line)
            self._fh.flush()
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line)
        return payload_hash


# ---------------------------------------------------------------------------
# plan.yaml (minimal YAML subset — stdlib only, no PyYAML dependency)
# ---------------------------------------------------------------------------


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if text == "" or any(c in text for c in ":#\n") or text != text.strip():
        return json.dumps(text, ensure_ascii=False)
    return text


def dump_plan_yaml(plan: dict[str, Any]) -> str:
    """Serialize a plan dict to the simple YAML subset we also re-read.

    Supports scalars, lists of scalars, and lists of flat string mappings —
    exactly what a CreativePlan needs. Returns text ending in a newline.
    """
    lines: list[str] = []
    for key, value in plan.items():
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
                continue
            lines.append(f"{key}:")
            for item in value:
                if isinstance(item, dict):
                    first = True
                    for k, v in item.items():
                        prefix = "  - " if first else "    "
                        lines.append(f"{prefix}{k}: {_yaml_scalar(v)}")
                        first = False
                else:
                    lines.append(f"  - {_yaml_scalar(item)}")
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            for k, v in value.items():
                lines.append(f"  {k}: {_yaml_scalar(v)}")
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    return "\n".join(lines) + "\n"


def write_plan_yaml(path: str | Path, plan: dict[str, Any]) -> Path:
    """Write ``plan.yaml`` under the project directory; returns the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_plan_yaml(plan), encoding="utf-8")
    return path


def _yaml_unquote(value: str) -> Any:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        inner = value[1:-1]
        if value[0] == '"':
            try:
                return json.loads(f'"{inner}"')
            except json.JSONDecodeError:
                return inner
        return inner.replace("''", "'")
    # minimal scalar typing for the plan subset: ints, floats, booleans, null
    if value == "null":
        return None
    lowered = value.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def load_plan_yaml(path: str | Path) -> dict[str, Any]:
    """Read back the minimal YAML subset written by :func:`dump_plan_yaml`.

    Not a general YAML parser: it handles the flat scalars, lists of
    scalars and lists of flat mappings that plans use — enough for
    ``mc studio plan`` to verify it can read what we wrote.
    """
    plan: dict[str, Any] = {}
    current_list: list[Any] | None = None
    current_item: dict[str, Any] | None = None
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        stripped = raw.lstrip()
        indented = raw.startswith("  ") or raw.startswith("\t")
        if stripped.startswith("- "):
            body = stripped[2:]
            if ":" in body:
                current_item = {}
                if current_list is not None:
                    current_list.append(current_item)
                k, _, v = body.partition(":")
                current_item[k.strip()] = _yaml_unquote(v)
                continue
            if current_list is not None:
                current_list.append(_yaml_unquote(body))
            continue
        if indented and current_item is not None and ":" in stripped:
            k, _, v = stripped.partition(":")
            current_item[k.strip()] = _yaml_unquote(v)
            continue
        key, _, value = raw.partition(":")
        key = key.strip()
        value = value.strip()
        current_item = None
        current_list = None
        if value in ("", "[]"):
            plan[key] = []
            current_list = plan[key]
        else:
            plan[key] = _yaml_unquote(value)
    return plan


# ---------------------------------------------------------------------------
# trace.jsonl reading / table rendering
# ---------------------------------------------------------------------------


def load_trace(path: str | Path) -> list[dict[str, Any]]:
    """Read a ``trace.jsonl`` file into a list of records.

    Blank lines are skipped; a non-JSON line raises ``ValueError``.
    """
    records: list[dict[str, Any]] = []
    text = Path(path).read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"trace.jsonl line {lineno}: invalid JSON: {exc}") from exc
        if not isinstance(rec, dict):
            raise ValueError(f"trace.jsonl line {lineno}: record must be a JSON object")
        records.append(rec)
    return records


def _render_row(row: tuple[str, ...], widths: list[int]) -> str:
    return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip()


def render_trace_table(records: list[dict[str, Any]]) -> str:
    """Render trace records as a human-readable table (``mc studio trace``)."""
    headers = ("ts", "step", "model", "node_id", "latency_ms", "payload_hash")
    rows: list[tuple[str, ...]] = []
    for rec in records:
        rows.append(
            (
                str(rec.get("ts", "")),
                str(rec.get("step", "")),
                str(rec.get("model", "")),
                str(rec.get("node_id") if rec.get("node_id") is not None else "-"),
                str(rec.get("latency_ms") if rec.get("latency_ms") is not None else "-"),
                str(rec.get("payload_hash") or "-")[:12],
            )
        )
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    sep = tuple("-" * w for w in widths)
    return "\n".join(
        [_render_row(headers, widths), _render_row(sep, widths)]
        + [_render_row(row, widths) for row in rows]
    )


__all__ = [
    "DEFAULT_DIST_DIR",
    "NODES_DIRNAME",
    "PLAN_FILENAME",
    "PREMIERE_FILENAME",
    "TRACE_FILENAME",
    "TraceWriter",
    "dump_plan_yaml",
    "init_project_layout",
    "load_plan_yaml",
    "load_trace",
    "project_dir",
    "project_paths",
    "render_trace_table",
    "write_plan_yaml",
]
