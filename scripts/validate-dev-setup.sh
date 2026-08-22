#!/usr/bin/env bash
# Validates: docs/development.md (Setup) and docs/AGENT_SETUP.md  (check-only by default)
# Usage: validate-dev-setup.sh [--check] [--run-destructive]
set -uo pipefail

MODE="check"
for arg in "$@"; do
  case "$arg" in
    --check) ;;
    --run-destructive) MODE="destructive" ;;
    -h|--help)
      printf 'Usage: %s [--check] [--run-destructive]\n' "${0##*/}"
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$arg" >&2
      printf 'Usage: %s [--check] [--run-destructive]\n' "${0##*/}" >&2
      exit 2
      ;;
  esac
done

fail=0
ok()   { printf '[CHECK] %-34s OK\n' "$1"; }
bad()  { printf '[CHECK] %-34s FAIL — %s\n' "$1" "$2"; fail=1; }
man()  { printf '[MANUAL] %-33s SKIPPED (run by operator)\n' "$1"; }

# --- Step 1: Python floor (docs/development.md Prerequisites; pyproject.toml:10) ---
if command -v python3 >/dev/null; then
  v="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
    && ok "python3 >= 3.12 ($v)" \
    || bad "python3 >= 3.12 ($v)" "pyproject.toml requires >=3.12"
else
  bad "python3 present" "not on PATH"
fi

# --- Step 2: virtualenv exists (docs/AGENT_SETUP.md section 1) ---
[ -x .venv/bin/python ] && ok ".venv/bin/python" || bad ".venv/bin/python" ".venv missing — run: python3 -m venv .venv"

# --- Step 3: ffplay on PATH (docs/AGENT_SETUP.md section 2) ---
command -v ffplay >/dev/null && ok "ffplay installed" || bad "ffplay installed" "install ffmpeg"

# --- Step 4: pinned tool versions match pyproject.toml:70-71 ---
if [ -x .venv/bin/ruff ]; then
  .venv/bin/ruff --version | grep -q "0.16.4" \
    && ok "ruff == 0.16.4" || bad "ruff == 0.16.4" "$( .venv/bin/ruff --version )"
else
  bad "ruff installed in .venv" "pip install -e '.[dev]'"
fi
if [ -x .venv/bin/mypy ]; then
  .venv/bin/mypy --version | grep -q "2.3.1" \
    && ok "mypy == 2.3.1" || bad "mypy == 2.3.1" "$( .venv/bin/mypy --version )"
else
  bad "mypy installed in .venv" "pip install -e '.[dev]'"
fi

# --- Step 5: editable install resolves the package ---
[ -x .venv/bin/pytest ] && ok "pytest in .venv" || bad "pytest in .venv" "pip install -e '.[dev]'"
if [ -f music_cli/__init__.py ] && [ -d .venv ]; then
  .venv/bin/python -c 'import music_cli' 2>/dev/null \
    && ok "music_cli importable (editable)" \
    || bad "music_cli importable (editable)" "pip install -e ."
fi

# --- Step 6: pre-commit hooks installed (docs/development.md Setup step 4) ---
if [ -f .git/hooks/pre-commit ]; then
  ok "pre-commit hook installed"
elif [ "$MODE" = "destructive" ]; then
  echo "[RUN] pre-commit install"
  pre-commit install && ok "pre-commit hook installed"
else
  man "pre-commit install"
fi

exit $fail
