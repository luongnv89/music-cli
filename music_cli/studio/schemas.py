"""Strict JSON schemas for the four core studio artifacts.

These are the contracts between M3 and the runtime. A parse failure on any
field must trigger a re-prompt, not a silent drop — so every validator is
strict (no extra fields, no coercion) and :meth:`validate` returns a list of
human-readable errors instead of raising.

The schemas are intentionally minimal but strict: they define the fields that
unblock P1.2/P2.1 and leave extension to later phases. All four classes are
importable without any GMI deps (keyring/httpx) installed — this module only
uses the stdlib.

Each class exposes::

    @classmethod
    def validate(cls, data: Any) -> list[str]

Returning ``[]`` means valid; any entries mean invalid. Instances also
expose an instance ``validate()`` that validates ``self._data`` for
convenience. ``model_validate`` is provided as an alias to ease a future
Pydantic migration without breaking callers.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")


def _is_non_empty_str(v: Any) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _err(prefix: str, msg: str) -> str:
    return f"{prefix}: {msg}" if prefix else msg


def _check_no_extra(data: dict[str, Any], allowed: set[str], prefix: str) -> list[str]:
    extra = sorted(set(data.keys()) - allowed)
    if extra:
        return [_err(prefix, f"unexpected field(s): {', '.join(extra)}")]
    return []


def _check_required(data: dict[str, Any], required: set[str], prefix: str) -> list[str]:
    errs: list[str] = []
    for f in sorted(required):
        if f not in data:
            errs.append(_err(prefix, f"missing required field '{f}'"))
    return errs


def _validate_iso_datetime(v: Any, field: str) -> list[str]:
    if not isinstance(v, str):
        return [f"{field}: must be ISO-8601 string"]
    try:
        datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return [f"{field}: invalid ISO-8601 datetime '{v}'"]
    return []


# ---------------------------------------------------------------------------
# Constitution
# ---------------------------------------------------------------------------

_CONSTITUTION_REQUIRED = {"project_id", "title", "brief", "narrative"}
_CONSTITUTION_ALLOWED = {
    "project_id",
    "title",
    "brief",
    "narrative",
    "style",
    "motifs",
    "voice_profile",
    "visual_style",
    "constraints",
    "taste_profile",
    "version",
}


def _validate_constitution(data: Any, prefix: str = "") -> list[str]:
    errs: list[str] = []
    if not isinstance(data, dict):
        return [_err(prefix, "must be an object")]
    errs.extend(_check_required(data, _CONSTITUTION_REQUIRED, prefix))
    errs.extend(_check_no_extra(data, _CONSTITUTION_ALLOWED, prefix))
    if "project_id" in data:
        v = data["project_id"]
        if not _is_non_empty_str(v):
            errs.append(_err(prefix, "project_id: must be non-empty string"))
        elif not _SLUG_RE.match(v):
            errs.append(_err(prefix, "project_id: must be slug (a-z0-9, -, _, 2-63 chars)"))
    for f in ("title", "brief", "narrative"):
        if f in data and not _is_non_empty_str(data[f]):
            errs.append(_err(prefix, f"{f}: must be non-empty string"))
    if "style" in data and data["style"] is not None and not isinstance(data["style"], str):
        errs.append(_err(prefix, "style: must be string"))
    if (
        "visual_style" in data
        and data["visual_style"] is not None
        and not isinstance(data["visual_style"], str)
    ):
        errs.append(_err(prefix, "visual_style: must be string"))
    if "motifs" in data:
        v = data["motifs"]
        if not isinstance(v, list):
            errs.append(_err(prefix, "motifs: must be list of strings"))
        else:
            for i, m in enumerate(v):
                if not _is_non_empty_str(m):
                    errs.append(_err(prefix, f"motifs[{i}]: must be non-empty string"))
    if "voice_profile" in data and data["voice_profile"] is not None:
        v = data["voice_profile"]
        if not isinstance(v, dict):
            errs.append(_err(prefix, "voice_profile: must be object"))
        else:
            # allow any string keys, values must be strings
            for k, val in v.items():
                if not isinstance(k, str):
                    errs.append(_err(prefix, f"voice_profile: key {k!r} must be string"))
                if not isinstance(val, str):
                    errs.append(_err(prefix, f"voice_profile.{k}: must be string"))
    if "constraints" in data and data["constraints"] is not None:
        v = data["constraints"]
        if not isinstance(v, dict):
            errs.append(_err(prefix, "constraints: must be object"))
        else:
            if "duration_seconds" in v:
                dv = v["duration_seconds"]
                if not isinstance(dv, (int, float)) or isinstance(dv, bool):
                    errs.append(_err(prefix, "constraints.duration_seconds: must be number"))
                elif dv <= 0 or dv > 600:
                    errs.append(_err(prefix, "constraints.duration_seconds: must be >0 and <=600"))
            if "budget_cap" in v:
                bv = v["budget_cap"]
                if not isinstance(bv, (int, float)) or isinstance(bv, bool):
                    errs.append(_err(prefix, "constraints.budget_cap: must be number"))
                elif bv < 0:
                    errs.append(_err(prefix, "constraints.budget_cap: must be >=0"))
    if "taste_profile" in data and data["taste_profile"] is not None:
        v = data["taste_profile"]
        if not isinstance(v, dict):
            errs.append(_err(prefix, "taste_profile: must be object"))
    if "version" in data and data["version"] is not None:
        v = data["version"]
        if not isinstance(v, (str, int)) or (isinstance(v, str) and not v.strip()):
            errs.append(_err(prefix, "version: must be non-empty string or int"))
        if isinstance(v, int) and v < 1:
            errs.append(_err(prefix, "version: must be >=1"))
    return errs


# ---------------------------------------------------------------------------
# CreativePlan
# ---------------------------------------------------------------------------

_CREATIVE_PLAN_REQUIRED = {
    "plan_id",
    "project_id",
    "title",
    "objective",
    "brief",
    "duration_seconds",
}
_CREATIVE_PLAN_ALLOWED = {
    "plan_id",
    "project_id",
    "title",
    "objective",
    "brief",
    "duration_seconds",
    "arc",
    "scenes",
    "shot_list",
    "tracks",
    "motifs",
    "voice",
    "locked_assets",
    "validation_rubric",
    "cover_art",
    "version",
}


def _validate_scene(obj: Any, prefix: str) -> list[str]:
    errs: list[str] = []
    if not isinstance(obj, dict):
        return [_err(prefix, "must be object")]
    allowed = {"id", "prompt", "description", "duration_seconds", "visual_prompt"}
    errs.extend(_check_no_extra(obj, allowed, prefix))
    for f in ("id", "prompt"):
        if f not in obj:
            errs.append(_err(prefix, f"missing required field '{f}'"))
        elif not _is_non_empty_str(obj[f]):
            errs.append(_err(prefix, f"{f}: must be non-empty string"))
    if "duration_seconds" in obj:
        v = obj["duration_seconds"]
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            errs.append(_err(prefix, "duration_seconds: must be number"))
        elif v <= 0 or v > 600:
            errs.append(_err(prefix, "duration_seconds: must be >0 and <=600"))
    for f in ("description", "visual_prompt"):
        if f in obj and obj[f] is not None and not isinstance(obj[f], str):
            errs.append(_err(prefix, f"{f}: must be string"))
    return errs


def _validate_creative_plan(data: Any, prefix: str = "") -> list[str]:
    errs: list[str] = []
    if not isinstance(data, dict):
        return [_err(prefix, "must be an object")]
    errs.extend(_check_required(data, _CREATIVE_PLAN_REQUIRED, prefix))
    errs.extend(_check_no_extra(data, _CREATIVE_PLAN_ALLOWED, prefix))
    for f in ("plan_id", "project_id", "title", "objective", "brief"):
        if f in data and not _is_non_empty_str(data[f]):
            errs.append(_err(prefix, f"{f}: must be non-empty string"))
    if (
        "project_id" in data
        and _is_non_empty_str(data["project_id"])
        and not _SLUG_RE.match(data["project_id"])
    ):
        errs.append(_err(prefix, "project_id: must be slug"))
    if "duration_seconds" in data:
        v = data["duration_seconds"]
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            errs.append(_err(prefix, "duration_seconds: must be number"))
        elif v <= 0 or v > 600:
            errs.append(_err(prefix, "duration_seconds: must be >0 and <=600"))
    # arc: list of strings or objects
    if "arc" in data and data["arc"] is not None:
        v = data["arc"]
        if not isinstance(v, list):
            errs.append(_err(prefix, "arc: must be list"))
        else:
            for i, item in enumerate(v):
                if isinstance(item, str):
                    if not item.strip():
                        errs.append(_err(prefix, f"arc[{i}]: must be non-empty string"))
                elif isinstance(item, dict):
                    if "description" not in item and "prompt" not in item and "title" not in item:
                        errs.append(_err(prefix, f"arc[{i}]: must have description/prompt/title"))
                else:
                    errs.append(_err(prefix, f"arc[{i}]: must be string or object"))
            if len(v) == 0:
                errs.append(_err(prefix, "arc: must not be empty if provided"))
    for list_field in ("scenes", "shot_list", "tracks"):
        if list_field in data and data[list_field] is not None:
            v = data[list_field]
            if not isinstance(v, list):
                errs.append(_err(prefix, f"{list_field}: must be list"))
            else:
                for i, item in enumerate(v):
                    errs.extend(
                        _validate_scene(
                            item, f"{prefix}{list_field}[{i}]" if prefix else f"{list_field}[{i}]"
                        )
                    )
    if "motifs" in data and data["motifs"] is not None:
        v = data["motifs"]
        if not isinstance(v, list):
            errs.append(_err(prefix, "motifs: must be list of strings"))
        else:
            for i, m in enumerate(v):
                if not _is_non_empty_str(m):
                    errs.append(_err(prefix, f"motifs[{i}]: must be non-empty string"))
    if "voice" in data and data["voice"] is not None and not isinstance(data["voice"], dict):
        errs.append(_err(prefix, "voice: must be object"))
    if "locked_assets" in data and data["locked_assets"] is not None:
        v = data["locked_assets"]
        if not isinstance(v, list):
            errs.append(_err(prefix, "locked_assets: must be list of strings"))
        else:
            for i, a in enumerate(v):
                if not _is_non_empty_str(a):
                    errs.append(_err(prefix, f"locked_assets[{i}]: must be non-empty string"))
    if (
        "validation_rubric" in data
        and data["validation_rubric"] is not None
        and not isinstance(data["validation_rubric"], dict)
    ):
        errs.append(_err(prefix, "validation_rubric: must be object"))
    if (
        "cover_art" in data
        and data["cover_art"] is not None
        and not isinstance(data["cover_art"], str)
    ):
        errs.append(_err(prefix, "cover_art: must be string"))
    if "version" in data and data["version"] is not None:
        v = data["version"]
        if not isinstance(v, (str, int)) or (isinstance(v, str) and not v.strip()):
            errs.append(_err(prefix, "version: must be non-empty string or int"))
    return errs


# ---------------------------------------------------------------------------
# ProjectManifest
# ---------------------------------------------------------------------------

_MANIFEST_REQUIRED = {"project_id", "plan_id"}
_MANIFEST_ALLOWED = {
    "project_id",
    "plan_id",
    "constitution",
    "plan",
    "nodes",
    "locked_nodes",
    "budget",
    "dist_dir",
    "premiere_path",
    "trace_path",
    "created_at",
    "version",
}


def _validate_manifest_node(obj: Any, prefix: str) -> list[str]:
    errs: list[str] = []
    if not isinstance(obj, dict):
        return [_err(prefix, "must be object")]
    allowed = {"id", "type", "status", "locked", "output_path", "prompt", "duration_seconds"}
    # be strict but allow prompt/duration for forward compat? check extra
    errs.extend(_check_no_extra(obj, allowed, prefix))
    for f in ("id", "type"):
        if f not in obj:
            errs.append(_err(prefix, f"missing required field '{f}'"))
        elif not _is_non_empty_str(obj[f]):
            errs.append(_err(prefix, f"{f}: must be non-empty string"))
    if "type" in obj and _is_non_empty_str(obj["type"]):
        if obj["type"] not in {"music", "speech", "video", "mix", "assemble", "audio", "caption"}:
            errs.append(_err(prefix, f"type: unknown node type '{obj['type']}'"))
    if (
        "status" in obj
        and obj["status"] is not None
        and obj["status"] not in {"pending", "running", "done", "failed", "locked"}
    ):
        errs.append(_err(prefix, "status: must be one of pending, running, done, failed, locked"))
    if "locked" in obj and obj["locked"] is not None and not isinstance(obj["locked"], bool):
        errs.append(_err(prefix, "locked: must be boolean"))
    if (
        "output_path" in obj
        and obj["output_path"] is not None
        and not isinstance(obj["output_path"], str)
    ):
        errs.append(_err(prefix, "output_path: must be string"))
    return errs


def _validate_project_manifest(data: Any, prefix: str = "") -> list[str]:
    errs: list[str] = []
    if not isinstance(data, dict):
        return [_err(prefix, "must be an object")]
    errs.extend(_check_required(data, _MANIFEST_REQUIRED, prefix))
    errs.extend(_check_no_extra(data, _MANIFEST_ALLOWED, prefix))
    for f in ("project_id", "plan_id"):
        if f in data and not _is_non_empty_str(data[f]):
            errs.append(_err(prefix, f"{f}: must be non-empty string"))
    if (
        "project_id" in data
        and _is_non_empty_str(data["project_id"])
        and not _SLUG_RE.match(data["project_id"])
    ):
        errs.append(_err(prefix, "project_id: must be slug"))
    if "constitution" in data and data["constitution"] is not None:
        if not isinstance(data["constitution"], dict):
            errs.append(_err(prefix, "constitution: must be object"))
        else:
            errs.extend(
                _validate_constitution(
                    data["constitution"], f"{prefix}constitution" if prefix else "constitution"
                )
            )
    if "plan" in data and data["plan"] is not None:
        if not isinstance(data["plan"], dict):
            errs.append(_err(prefix, "plan: must be object"))
        else:
            errs.extend(
                _validate_creative_plan(data["plan"], f"{prefix}plan" if prefix else "plan")
            )
    if "nodes" in data and data["nodes"] is not None:
        v = data["nodes"]
        if not isinstance(v, list):
            errs.append(_err(prefix, "nodes: must be list"))
        else:
            seen: set[str] = set()
            for i, n in enumerate(v):
                p = f"{prefix}nodes[{i}]" if prefix else f"nodes[{i}]"
                errs.extend(_validate_manifest_node(n, p))
                if isinstance(n, dict) and "id" in n and isinstance(n["id"], str):
                    if n["id"] in seen:
                        errs.append(_err(prefix, f"nodes[{i}].id: duplicate '{n['id']}'"))
                    seen.add(n["id"])
    if "locked_nodes" in data and data["locked_nodes"] is not None:
        v = data["locked_nodes"]
        if not isinstance(v, list):
            errs.append(_err(prefix, "locked_nodes: must be list of strings"))
        else:
            for i, a in enumerate(v):
                if not _is_non_empty_str(a):
                    errs.append(_err(prefix, f"locked_nodes[{i}]: must be non-empty string"))
    if "budget" in data and data["budget"] is not None:
        v = data["budget"]
        if not isinstance(v, dict):
            errs.append(_err(prefix, "budget: must be object"))
        else:
            allowed_b = {"cap", "spent", "currency", "per_build_cap"}
            errs.extend(_check_no_extra(v, allowed_b, f"{prefix}budget" if prefix else "budget"))
            for k in ("cap", "spent", "per_build_cap"):
                if k in v and v[k] is not None:
                    if not isinstance(v[k], (int, float)) or isinstance(v[k], bool):
                        errs.append(_err(prefix, f"budget.{k}: must be number"))
                    elif v[k] < 0:
                        errs.append(_err(prefix, f"budget.{k}: must be >=0"))
            if "currency" in v and v["currency"] is not None and not isinstance(v["currency"], str):
                errs.append(_err(prefix, "budget.currency: must be string"))
    for f in ("dist_dir", "premiere_path", "trace_path"):
        if f in data and data[f] is not None and not isinstance(data[f], str):
            errs.append(_err(prefix, f"{f}: must be string"))
    if "created_at" in data and data["created_at"] is not None:
        errs.extend(
            _validate_iso_datetime(
                data["created_at"], f"{prefix}created_at" if prefix else "created_at"
            )
        )
    if "version" in data and data["version"] is not None:
        v = data["version"]
        if not isinstance(v, (str, int)) or (isinstance(v, str) and not v.strip()):
            errs.append(_err(prefix, "version: must be non-empty string or int"))
    return errs


# ---------------------------------------------------------------------------
# PlanDiff
# ---------------------------------------------------------------------------

_PLAN_DIFF_REQUIRED = {"from_plan_id", "to_plan_id", "reason", "affected_nodes"}
_PLAN_DIFF_ALLOWED = {
    "from_plan_id",
    "to_plan_id",
    "reason",
    "affected_nodes",
    "changes",
    "added",
    "removed",
    "modified",
    "summary",
}


def _validate_plan_diff(data: Any, prefix: str = "") -> list[str]:
    errs: list[str] = []
    if not isinstance(data, dict):
        return [_err(prefix, "must be an object")]
    errs.extend(_check_required(data, _PLAN_DIFF_REQUIRED, prefix))
    errs.extend(_check_no_extra(data, _PLAN_DIFF_ALLOWED, prefix))
    for f in ("from_plan_id", "to_plan_id", "reason"):
        if f in data and not _is_non_empty_str(data[f]):
            errs.append(_err(prefix, f"{f}: must be non-empty string"))
    if "affected_nodes" in data:
        v = data["affected_nodes"]
        if not isinstance(v, list):
            errs.append(_err(prefix, "affected_nodes: must be list of strings"))
        else:
            for i, a in enumerate(v):
                if not _is_non_empty_str(a):
                    errs.append(_err(prefix, f"affected_nodes[{i}]: must be non-empty string"))
    for lf in ("added", "removed", "modified"):
        if lf in data and data[lf] is not None:
            v = data[lf]
            if not isinstance(v, list):
                errs.append(_err(prefix, f"{lf}: must be list of strings"))
            else:
                for i, a in enumerate(v):
                    if not _is_non_empty_str(a):
                        errs.append(_err(prefix, f"{lf}[{i}]: must be non-empty string"))
    if "changes" in data and data["changes"] is not None:
        v = data["changes"]
        if not isinstance(v, list):
            errs.append(_err(prefix, "changes: must be list"))
        else:
            for i, ch in enumerate(v):
                p = f"{prefix}changes[{i}]" if prefix else f"changes[{i}]"
                if not isinstance(ch, dict):
                    errs.append(_err(p, "must be object"))
                    continue
                allowed_c = {"op", "path", "field", "old_value", "new_value", "value"}
                extra_c = set(ch.keys()) - allowed_c
                if extra_c:
                    errs.append(_err(p, f"unexpected field(s): {', '.join(sorted(extra_c))}"))
                if "op" not in ch:
                    errs.append(_err(p, "missing required field 'op'"))
                elif ch["op"] not in {"add", "remove", "replace", "modify", "update"}:
                    errs.append(_err(p, "op: must be one of add, remove, replace, modify, update"))
                # need at least path or field
                if "path" not in ch and "field" not in ch:
                    errs.append(_err(p, "must have 'path' or 'field'"))
                if "path" in ch and ch["path"] is not None and not _is_non_empty_str(ch["path"]):
                    errs.append(_err(p, "path: must be non-empty string"))
                if "field" in ch and ch["field"] is not None and not _is_non_empty_str(ch["field"]):
                    errs.append(_err(p, "field: must be non-empty string"))
    if "summary" in data and data["summary"] is not None and not isinstance(data["summary"], str):
        errs.append(_err(prefix, "summary: must be string"))
    # cross-field: if changes empty and affected_nodes empty => suspicious but not error; allow no-op diff with reason
    return errs


# ---------------------------------------------------------------------------
# Public classes
# ---------------------------------------------------------------------------


class _BaseSchema:
    """Shared base for the four schemas."""

    _validator: Any = staticmethod(lambda data, prefix="": [])

    def __init__(self, data: dict[str, Any] | None = None, **kwargs: Any) -> None:
        if data is not None and kwargs:
            raise ValueError("pass either data dict or kwargs, not both")
        if data is None:
            data = kwargs
        if not isinstance(data, dict):
            raise TypeError("data must be dict")
        self._data: dict[str, Any] = data

    @classmethod
    def _cls_validate(cls, data: Any) -> list[str]:
        return cls._validator(data)

    def _inst_validate(self) -> list[str]:
        return self.__class__._cls_validate(self._data)

    @classmethod
    def model_validate(cls, data: Any) -> Any:
        errs = cls._cls_validate(data)
        if errs:
            raise ValueError("; ".join(errs))
        return cls(data)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._data!r})"


class _BothDescriptor:
    """Descriptor so ``Cls.validate(data)`` and ``inst.validate()`` both work."""

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:

            def class_call(data: Any) -> list[str]:
                return objtype._validator(data)

            return class_call

        def inst_call(data: Any = None) -> list[str]:
            if data is not None:
                return objtype._validator(data)
            return objtype._validator(obj._data)

        return inst_call


def _make_schema_class(name: str, validator: Any) -> Any:
    cls = type(name, (_BaseSchema,), {"_validator": staticmethod(validator)})
    cls.validate = _BothDescriptor()  # type: ignore[attr-defined]
    return cls


Constitution = _make_schema_class("Constitution", _validate_constitution)
CreativePlan = _make_schema_class("CreativePlan", _validate_creative_plan)
ProjectManifest = _make_schema_class("ProjectManifest", _validate_project_manifest)
PlanDiff = _make_schema_class("PlanDiff", _validate_plan_diff)

__all__ = ["Constitution", "CreativePlan", "PlanDiff", "ProjectManifest"]
