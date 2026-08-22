# Troubleshooting

Real issues encountered while validating runbooks, with resolutions.

## `validate-dev-setup.sh` fails: ruff/mypy versions do not match pins
- **Cause:** `.venv` predated the tool pins (`ruff==0.16.4`, `mypy==2.3.1`,
  `pyproject.toml:70-71`); it still had ruff 0.15.22 and mypy 2.3.0.
- **Fix:** re-sync the dev extra: `pip install -e ".[dev]"`, then re-run
  `./scripts/validate-dev-setup.sh --check`.
- **Seen during:** validate-dev-setup.sh --check (2026-08-22)
