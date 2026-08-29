# Troubleshooting

Real issues encountered while validating runbooks, with resolutions.

## `mc studio build` fails with `HTTP 400` from GMI queue

- **Cause:** The GMI Cloud API key is scoped for the **text model endpoint**
  (`api.gmi-serving.com`) but not the **audio queue endpoint**
  (`console.gmicloud.ai/api/v1/ie/requestqueue/apikey/requests`). Music 3.0 and Speech 2.8 run as
  async jobs on the queue endpoint; a text-only key will pass `mc cloud ping` but fail during
  `mc studio build` with `HTTP 400`.
- **Verify:** run `mc studio doctor` — it should show `OK: gmi key: stored in the OS keyring`.
  Then try `mc cloud ping` to confirm the text endpoint works.
- **Fix:** obtain a GMI Cloud key with audio-model access. Contact GMI Cloud support or the
  MiniMax Week organizers for a key authorized for the async queue endpoint.
- **Seen during:** Epic 131 real-machine testing (2026-08-28)

## `validate-dev-setup.sh` fails: ruff/mypy versions do not match pins
- **Cause:** `.venv` predated the tool pins (`ruff==0.16.4`, `mypy==2.3.1`,
  `pyproject.toml:70-71`); it still had ruff 0.15.22 and mypy 2.3.0.
- **Fix:** re-sync the dev extra: `pip install -e ".[dev]"`, then re-run
  `./scripts/validate-dev-setup.sh --check`.
- **Seen during:** validate-dev-setup.sh --check (2026-08-22)
