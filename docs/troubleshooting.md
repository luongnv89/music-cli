# Troubleshooting

Real issues encountered while validating runbooks, with resolutions.

## Historical: `mc studio build` fails with `HTTP 400` from GMI queue

- **Cause:** An earlier GMI key could access the text endpoint but not the audio queue.
- **Verify:** run `mc studio doctor`, then `mc cloud smoke --skip speech` to check the
  currently authorized Music 3.0 path.
- **Fix:** obtain a GMI Cloud key with audio-model access if the queue rejects the request.
- **Current status:** the active key reaches Music 3.0; the current external blocker is Speech
  2.8 HD returning persistent `503` capacity errors.
- **Seen during:** Epic 131 real-machine testing (2026-08-28)

## `mc studio build` repeats a completed GMI audio job until timeout

- **Cause:** GMI returns terminal status `success` and nests audio under `outcome`; the generic
  adapter contract expected `completed` and top-level media fields.
- **Fix:** use the current adapter, which accepts both terminal statuses, normalizes nested
  `outcome.audio_url`/`media_urls`, sends UUIDv4-form idempotency keys, and uses the queue's
  required audio settings. Retry with `mc studio build --resume` after a failed job.

## `validate-dev-setup.sh` fails: ruff/mypy versions do not match pins
- **Cause:** `.venv` predated the tool pins (`ruff==0.16.4`, `mypy==2.3.1`,
  `pyproject.toml:70-71`); it still had ruff 0.15.22 and mypy 2.3.0.
- **Fix:** re-sync the dev extra: `pip install -e ".[dev]"`, then re-run
  `./scripts/validate-dev-setup.sh --check`.
- **Seen during:** validate-dev-setup.sh --check (2026-08-22)
