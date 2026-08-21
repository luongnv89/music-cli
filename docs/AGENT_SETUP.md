# Agent Setup Guide

This note captures what an AI agent cannot reliably infer from the repository
tree. Follow it verbatim from a clean checkout to reach a verified, runnable
state. It is the source of truth for issue Pre.1 (`#32`) and feeds `CLAUDE.md`
(`#33`) and `AGENTS.md` (`#34`).

## 1. Virtual environment (mandatory)

A `.venv/` exists in development, and **every tool must be invoked through it**.
Do not call bare `pytest`, `mypy`, `ruff`, or `python` — the bare binaries on
this machine resolve to a different Homebrew Python and will produce misleading
results. Always prefix with `.venv/bin/`.

From a clean checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate        # or prefix commands with .venv/bin/
pip install -e ".[dev]"
```

`-e` installs `music_cli` in editable mode so source edits take effect without
reinstalling. `[dev]` pulls in `pytest`, `pytest-cov`, `ruff`, `mypy`, `bandit`,
and `pre-commit` (see `pyproject.toml` → `[project.optional-dependencies].dev`).

## 2. FFmpeg is a hard runtime prerequisite

`ffplay` (part of FFmpeg) is the audio backend — see `music_cli/player/ffplay.py`.
The player logs a warning and cannot play if `ffplay` is not on `PATH`. Install
FFmpeg before exercising playback or the player tests:

- macOS:  `brew install ffmpeg`
- Debian/Ubuntu: `sudo apt install ffmpeg`
- Windows: install FFmpeg and add it to `PATH`

## 3. Optional extras (NOT installed by default)

The `ai`, `minimax`, and `youtube` extras are **not installed** by the dev setup
above. Their code paths cannot be exercised without them:

| Extra | Install command | Unlocks |
|-------|-----------------|---------|
| `ai` | `pip install -e ".[ai]"` | MusicGen / AudioLDM / Bark AI track generation (`music_cli/sources/ai_generator.py`) |
| `minimax` | `pip install -e ".[minimax]"` | MiniMax Music 3 generation (requires Diffusers ≥ 0.39) |
| `youtube` | `pip install -e ".[youtube]"` | YouTube audio streaming via `yt-dlp` (`music_cli/sources/youtube.py`) |

Tests for these paths are skipped when the extra is absent. Do not treat a skip
as a failure.

## 4. Test command of record

```bash
.venv/bin/pytest -q -p no:cacheprovider
```

- Always use `.venv/bin/pytest`, never bare `pytest`.
- `-p no:cacheprovider` disables the pytest cache for hermetic, reproducible runs.
- `pyproject.toml` → `[tool.pytest.ini_options].addopts` already forces
  `--cov=music_cli --cov-report=term-missing`, so **do not add coverage flags**.
- Run a single file or test when iterating:
  `.venv/bin/pytest tests/test_config.py -q -p no:cacheprovider`

## 5. mypy currently exits 2 (tracked, not a broken environment)

`python_version = "3.10"` is set in `pyproject.toml` → `[tool.mypy]`, but the
installed numpy stubs require Python 3.12+ syntax, so mypy crashes before
checking any file:

```bash
.venv/bin/mypy music_cli    # exits 2 — known, not your fault
```

Expected error:
`numpy/__init__.pyi: Type statement is only supported in Python 3.12 and greater`

This is tracked as **`F-CI-002`** (see `MODERNIZATION_PLAN.md` → Task 0.3). Do
not mistake it for a broken environment, and do not attempt to "fix" it by
editing `[tool.mypy]` here — Task 0.3 owns that.

## 6. Formatting

`ruff format` is the formatter (black was removed in `F-CLEAN-009`; use it for
all formatting on `music_cli/` and `tests/`):

```bash
.venv/bin/ruff format .
.venv/bin/ruff check . --fix
```

## 7. Quick verification

After the setup above, a green run confirms the environment:

```bash
.venv/bin/pytest -q -p no:cacheprovider
```
