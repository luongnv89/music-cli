# Decisions Log

Append-only log of ambiguities raised during documentation reconciliation and
their resolutions. Each entry records who resolved it and the code source where
one exists.

## 2026-08-22

- Q: Docs state a Python floor of 3.10+, but `requires-python = ">=3.12"`
  (`pyproject.toml:10`) and CI tests 3.12–3.14 only
  (`.github/workflows/ci.yml:111`), while `install.sh` still accepts 3.10+
  (`install.sh:107-118`). Which floor is authoritative?
- A (user): Fix docs to **Python 3.12+**, matching `pyproject.toml` and CI.
  The `install.sh` 3.10-vs-3.12 mismatch is flagged separately as a code issue,
  not papered over in docs.
- Source: `pyproject.toml:10`

- Q: README/user-guide promise automatic YouTube caching (2 GB LRU, m4a
  192 kbps, offline replay). Code shows streaming-only playback
  (`sources/youtube.py:120`, `player/ffplay.py:156`) and a 1000-entry replay
  history (`youtube_history.py:92-104`); no download-to-cache pipeline exists.
  Keep or rewrite?
- A (user): Rewrite docs to match code: describe `mc yt` as replay history;
  remove caching/LRU-eviction/format claims.
- Source: `music_cli/sources/youtube.py:120`, `music_cli/youtube_history.py:96`,
  `music_cli/daemon_handlers.py:686-708`

- Q: Scope of this reconciliation run?
- A (user): Full scope — root `README.md`, all `docs/*.md`, plus
  `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, `CODE_REVIEW.md`.
  Point-in-time artifacts `MODERNIZATION_PLAN.md` / `MODERNIZATION_REPORT.md`
  are skipped.
