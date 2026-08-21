# CLAUDE.md

Project context for Claude. Full agent setup (venv creation, FFmpeg, optional
extras, mypy/F-CI-002) lives in `docs/AGENT_SETUP.md` — read it first.

## Critical commands

- **Install:** `python3 -m venv .venv && pip install -e ".[dev]"` (see `docs/AGENT_SETUP.md`)
- **Test (command of record):** `.venv/bin/pytest -q -p no:cacheprovider`
- **Lint:** `.venv/bin/ruff check . --fix`
- **Format:** `.venv/bin/ruff format .`
- **Type check:** `.venv/bin/mypy music_cli` — currently **exits 2** (known, tracked as `F-CI-002`; see Task 0.3). Do not "fix" it here.

IMPORTANT: always invoke tools through `.venv/bin/` — bare `pytest`/`mypy` resolve to a different Homebrew Python and give wrong results. `pyproject.toml` already forces `--cov`, so add no coverage flags.

## Architecture map

- `music_cli/cli.py` — Click CLI (`mc`) front end
- `music_cli/daemon.py` — background daemon transport/lifecycle; IPC command handlers live in `music_cli/daemon_handlers.py`, registered via the `COMMAND_HANDLERS` table
- `music_cli/player/ffplay.py` — `ffplay` (FFmpeg) audio backend
- `music_cli/sources/` — radio, local, youtube, ai_generator (optional extras)
- `music_cli/platform/` — OS media controllers
- `tests/` — pytest suite (asyncio_mode=auto)

## Hard rules

- YOU MUST NOT commit, push, or open a PR unless explicitly asked.
- Never add `Co-Authored-By` trailers.
- Format with `ruff format` (black was removed; `F-CLEAN-009`).
- Never edit `[tool.mypy] python_version` to "fix" the exit-2 — Task 0.3 owns that.
- Do not install the `ai`, `minimax`, or `youtube` extras unless the task needs them.
- One logical change per commit; commit message format: `<type>(<scope>): <desc> (#N)`.

## Workflow preferences

- Make minimal, focused changes; do not rewrite whole files for one-line fixes.
- After code changes, run the test command of record before claiming success.
- Prefer single-test runs while iterating; run the full suite before finishing.
- Skip "I'll continue..." filler; just act, then report the result.

## What NOT to include

- No file-by-file descriptions (use the architecture map above).
- No style rules `ruff` already enforces.
- No version numbers or dates that change frequently.
- No duplicating `docs/AGENT_SETUP.md` — link to it instead.

## Token Efficiency
- Never re-read files you just wrote or edited. You know the contents.
- Never re-run commands to "verify" unless the outcome was uncertain.
- Don't echo back large blocks of code or file contents unless asked.
- Batch related edits into single operations. Don't make 5 edits when 1 handles it.
- Skip confirmations like "I'll continue..." Just do it.
- If a task needs 1 tool call, don't use 3. Plan before acting.
- Do not summarize what you just did unless the result is ambiguous or you need additional input.
