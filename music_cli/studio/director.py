"""M3Director: the Phase-P2 creative compiler front-end (#135).

Wraps the P1.2 adapter layer (``music_cli.cloud``) with three structured
tasks, each of which prompts MiniMax M3, validates the reply against the
P1.1 schemas, and retries on parse failure with a corrective
"re-output the exact JSON" instruction:

- :meth:`M3Director.plan` — brief -> :class:`~music_cli.studio.schemas.CreativePlan`
- :meth:`M3Director.critique` — plan + measured ffprobe results ->
  :class:`CritiqueReport` listing inconsistencies and suggested repairs
- :meth:`M3Director.revise` — plan + revision intent ->
  :class:`~music_cli.studio.schemas.PlanDiff` with ``locked_nodes`` and
  ``regenerate_nodes``

Every call — including each retry attempt — appends one JSON line to the
trace file (``trace.jsonl``) carrying ``step``, ``model``, ``ts``,
``input_hash``, ``output_hash``, ``latency_ms`` and ``retries`` so a build
session can be audited after the fact. The trace path defaults to
``dist/trace.jsonl`` (``dist/`` is gitignored); pass ``trace_path=None``
to disable tracing entirely.

Like :mod:`music_cli.studio.schemas`, this module is stdlib-only: it
depends on the adapter *interface* (async ``m3_plan`` / ``m3_critique``
methods) but never on keyring/httpx, so it is importable in any install.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .schemas import CreativePlan, PlanDiff
from .trace import TraceWriter

#: One initial attempt plus this many corrective retries on parse failure.
MAX_PARSE_RETRIES = 2

#: Default trace file (relative to the working directory, gitignored).
DEFAULT_TRACE_PATH = Path("dist") / "trace.jsonl"

_PLAN_INSTRUCTION = (
    "Respond with ONLY valid JSON. No markdown. No prose. Start with { and end with }.\n"
    "REQUIRED: plan_id, project_id (slug), title, objective, brief, duration_seconds.\n"
    "OPTIONAL: arc, scenes, shot_list, tracks, motifs, voice, locked_assets, "
    "validation_rubric, cover_art, version.\n"
    'Example: {"plan_id": "p1", "project_id": "my-project", "title": "T", '
    '"objective": "O", "brief": "B", "duration_seconds": 60, '
    '"tracks": [{"id": "t1", "prompt": "p", "description": "d", "duration_seconds": 30}], '
    '"scenes": [{"id": "s1", "prompt": "p", "description": "d", "duration_seconds": 5.0}]}'
)

_CRITIQUE_INSTRUCTION = (
    "You are a rigorous music critic. Compare the plan against the measured "
    "results and respond with a single JSON object and nothing else — no "
    "prose, no markdown fences — shaped as:\n"
    '{"ok": <bool>, "issues": [<string>...], "repairs": [<string>...]} '
    'with optional "summary" and "score". "ok" is true only when the '
    "measured results are consistent with the plan."
)

_REVISE_INSTRUCTION = (
    "You are the creative director. Revise the plan per the intent and "
    "respond with a single JSON object and nothing else — no prose, no "
    "markdown fences — shaped as a plan diff:\n"
    "required: from_plan_id, to_plan_id, reason, affected_nodes (list of "
    "node ids)\n"
    "optional: changes, added, removed, modified, summary, locked_nodes "
    "(node ids kept untouched), regenerate_nodes (node ids that must "
    "regenerate)"
)


class DirectorError(Exception):
    """The model could not produce schema-valid output after all retries."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_json(text: str) -> Any:
    """Parse the first JSON object found in ``text``.

    M3 sometimes wraps JSON in markdown fences or leading prose; scan for
    the first ``{`` and decode from there. Raises ``ValueError`` when no
    decodable JSON object is present.
    """
    if not isinstance(text, str):
        raise ValueError("model reply is not text")
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch == "{":
            try:
                obj, _ = decoder.raw_decode(text[i:])
            except ValueError:
                continue
            if isinstance(obj, dict):
                return obj
    raise ValueError("no JSON object found in model reply")


class CritiqueReport:
    """Structured M3 critique: consistency verdict plus repair list.

    Mirrors the schema conventions of :mod:`music_cli.studio.schemas`:
    ``validate`` returns a list of errors (empty means valid) and
    :meth:`model_validate` raises ``ValueError`` on invalid input.
    ``ok`` is required; ``issues`` and ``repairs`` default to empty lists.
    """

    ALLOWED = {"ok", "issues", "repairs", "summary", "score", "measured"}

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = dict(data)
        self.ok: bool = bool(self._data.get("ok", False))
        self.issues: list[Any] = list(self._data.get("issues") or [])
        self.repairs: list[Any] = list(self._data.get("repairs") or [])

    @classmethod
    def validate(cls, data: Any) -> list[str]:
        if not isinstance(data, dict):
            return ["must be an object"]
        errs: list[str] = []
        if "ok" not in data:
            errs.append("missing required field 'ok'")
        elif not isinstance(data["ok"], bool):
            errs.append("ok: must be boolean")
        for field in ("issues", "repairs"):
            v = data.get(field)
            if v is not None and not isinstance(v, list):
                errs.append(f"{field}: must be list of strings")
        v = data.get("summary")
        if v is not None and not isinstance(v, str):
            errs.append("summary: must be string")
        if "score" in data and data["score"] is not None:
            if not isinstance(data["score"], (int, float)) or isinstance(data["score"], bool):
                errs.append("score: must be number")
        extra = sorted(set(data.keys()) - cls.ALLOWED)
        if extra:
            errs.append(f"unexpected field(s): {', '.join(extra)}")
        return errs

    @classmethod
    def model_validate(cls, data: Any) -> CritiqueReport:
        errs = cls.validate(data)
        if errs:
            raise ValueError("; ".join(errs))
        return cls(data)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"CritiqueReport({self._data!r})"


class M3Director:
    """Structured build/direct loop over an M3 adapter.

    ``adapter`` is any object exposing async ``m3_plan(prompt)`` and
    ``m3_critique(prompt)`` chat methods returning ``{"text": str}``
    (both :class:`~music_cli.cloud.gmi.GMIAdapter` and
    :class:`~music_cli.cloud.openrouter.OpenRouterAdapter` qualify).
    """

    def __init__(
        self,
        adapter: Any,
        *,
        model: str = "MiniMax-M3",
        trace_path: Path | str | None = DEFAULT_TRACE_PATH,
    ) -> None:
        self._adapter = adapter
        self.model = model
        self.trace_path = Path(trace_path) if trace_path is not None else None

    # -- public task methods --------------------------------------------

    async def plan(self, brief: str) -> CreativePlan:
        """Ask M3 for a CreativePlan for ``brief``, schema-validated."""
        system_prompt = (
            "You are a creative director. You MUST respond with ONLY valid JSON. "
            "No markdown. No prose. No code blocks. No explanation. "
            "Your response must start with { and end with }. "
            "REQUIRED FIELDS: plan_id, project_id (slug), title, objective, brief, duration_seconds."
        )
        prompt = f"Brief:\n{brief}"
        data = await self._ask_json_with_system("plan", prompt, system_prompt, CreativePlan)
        return CreativePlan(data)

    async def critique(self, plan: Any, measurements: Any) -> CritiqueReport:
        """Ask M3 to reconcile ``plan`` against measured ffprobe results."""
        prompt = (
            f"{_CRITIQUE_INSTRUCTION}\n\nPlan:\n"
            f"{json.dumps(_as_dict(plan), indent=2, default=str)}\n\n"
            f"Measured results (ffprobe):\n{json.dumps(measurements, indent=2, default=str)}"
        )
        data = await self._ask_json("critique", prompt, CritiqueReport)
        return CritiqueReport(data)

    async def revise(self, plan: Any, intent: str) -> PlanDiff:
        """Ask M3 for a revision diff (locked vs regenerate nodes)."""
        prompt = (
            f"{_REVISE_INSTRUCTION}\n\nPlan:\n"
            f"{json.dumps(_as_dict(plan), indent=2, default=str)}\n\n"
            f"Revision intent:\n{intent}"
        )
        data = await self._ask_json("revise", prompt, PlanDiff)
        return PlanDiff(data)

    # -- internals --------------------------------------------------------

    async def _ask_json_with_system(
        self, step: str, prompt: str, system_prompt: str, schema: Any
    ) -> dict[str, Any]:
        """Like _ask_json but sends a system message for JSON enforcement."""
        current_prompt = prompt
        previous_text: str | None = None
        start = time.monotonic()
        last_errors: list[str] = []

        for attempt in range(1 + MAX_PARSE_RETRIES):
            if previous_text is not None:
                current_prompt = (
                    f"{prompt}\n\nYour previous reply was not valid JSON for this "
                    f"schema. Errors:\n"
                    + "\n".join(f"- {e}" for e in last_errors)
                    + f"\n\nPrevious reply:\n{previous_text}\n\n"
                    "Re-output the exact JSON, corrected. No prose, no markdown fences."
                )
            reply = await self._call_with_system(step, current_prompt, system_prompt)
            text = reply.get("text", "") if isinstance(reply, dict) else str(reply)
            try:
                data = extract_json(text)
                errors = schema.validate(data)
                if errors:
                    last_errors = errors
                    previous_text = text
                    continue
                self._trace(step, prompt, text, start, attempt, ok=True)
                return data
            except (ValueError, TypeError):
                last_errors = ["model did not return JSON"]
                previous_text = text
                continue

        self._trace(step, prompt, previous_text or "", start, MAX_PARSE_RETRIES, ok=False)
        raise DirectorError(
            f"{step}: model failed to produce schema-valid JSON after "
            f"{1 + MAX_PARSE_RETRIES} attempts; last errors: {'; '.join(last_errors)}"
        )

    async def _ask_json(self, step: str, prompt: str, schema: Any) -> dict[str, Any]:
        """Call M3 and retry on parse/validation failure, tracing each attempt.

        Up to ``1 + MAX_PARSE_RETRIES`` attempts; each failed attempt gets a
        corrective prompt embedding the validation errors and the invalid
        reply with a "re-output the exact JSON" instruction. Raises
        :class:`DirectorError` when every attempt fails.
        """
        current_prompt = prompt
        previous_text: str | None = None
        start = time.monotonic()
        last_errors: list[str] = []

        for attempt in range(1 + MAX_PARSE_RETRIES):
            if previous_text is not None:
                current_prompt = (
                    f"{prompt}\n\nYour previous reply was not valid JSON for this "
                    "schema. Errors:\n"
                    + "\n".join(f"- {e}" for e in last_errors)
                    + f"\n\nPrevious reply:\n{previous_text}\n\n"
                    "Re-output the exact JSON, corrected. No prose, no markdown fences."
                )
            reply = await self._call(step, current_prompt)
            text = reply.get("text", "") if isinstance(reply, dict) else str(reply)
            try:
                data = extract_json(text)
                errs = schema.validate(data)
                if errs:
                    raise ValueError("; ".join(errs))
                # ``attempt`` corrective re-prompts have been issued so far.
                self._trace(step, current_prompt, text, start, attempt)
                return data
            except ValueError as exc:
                last_errors = [e for e in str(exc).split("; ") if e]
                previous_text = text

        self._trace(step, current_prompt, previous_text or "", start, MAX_PARSE_RETRIES, ok=False)
        raise DirectorError(
            f"{step}: model failed to produce schema-valid JSON after "
            f"{1 + MAX_PARSE_RETRIES} attempts; last errors: {'; '.join(last_errors)}"
        )

    async def _call(self, step: str, prompt: str) -> Any:
        if step == "critique":
            return await self._adapter.m3_critique(prompt)
        return await self._adapter.m3_plan(prompt)

    async def _call_with_system(self, step: str, prompt: str, system_prompt: str) -> Any:
        if step == "critique":
            return await self._adapter.m3_critique(prompt, system=system_prompt)
        return await self._adapter.m3_plan(prompt, system=system_prompt)

    def _trace(
        self,
        step: str,
        prompt: str,
        output: str,
        start: float,
        retries: int,
        *,
        ok: bool = True,
    ) -> None:
        """Append one decision-log line for a (possibly retried) call."""
        if self.trace_path is None:
            return
        TraceWriter(self.trace_path, model=self.model).append(
            step=step,
            latency_ms=round((time.monotonic() - start) * 1000, 3),
            input_hash=_sha256(prompt),
            output_hash=_sha256(output),
            retries=retries,
            ok=ok,
        )


def _as_dict(obj: Any) -> Any:
    """Best-effort serialization of schema instances to plain dicts."""
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    return obj


__all__ = [
    "DEFAULT_TRACE_PATH",
    "MAX_PARSE_RETRIES",
    "CritiqueReport",
    "DirectorError",
    "M3Director",
    "extract_json",
]
