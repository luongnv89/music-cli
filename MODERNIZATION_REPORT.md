# Modernization Report — music-cli

**Audited:** 2026-08-19 · **Commit:** `0f00ec5` · **Branch:** `main`
**Stack:** Python 3.14.7 · click CLI + asyncio daemon · setuptools/pyproject · **Size:** 54 source files, ~12.3 kLOC (5.9 kLOC package + 6.4 kLOC tests)
**Baseline:** AMBER — builds, imports, and 403/403 tests pass locally at ~54.7% coverage, but `mypy` cannot run at all, the suite is not hermetic, and CI has been red on `main` for 20 of its last 30 runs

> **This is not an abandoned codebase.** All 103 commits landed within the last 12 months and HEAD is
> from the day of the audit. The findings below are drift and unfinished edges in *actively developed*
> code — not rot. That changes the plan's shape: there is no "resurrect the build" phase, and P0 is
> about closing the gap between what CI claims to verify and what it actually verifies.

## Summary

| Severity | Count |
|---|---|
| Critical | 3 |
| High | 16 |
| Medium | 36 |
| Low | 22 |
| **Total** | **77** |

The project is well-tooled on paper — pre-commit, a 9-cell CI matrix, Bandit, three linters, 403
tests — and the gap between that apparatus and what it actually enforces is where nearly every
serious finding lives. `mypy` exits 2 on a developer machine before checking a single line, so the
type gate has been passing in CI and broken locally. The Windows test cells have failed on every run
since they were added because `tests/test_ffplay.py` patches `os.killpg`, which does not exist on
Windows — so `main` is red, and a red `main` has become normal. Meanwhile `requires-python` promises
3.10 while the matrix tests only 3.12–3.14, and Python 3.10 reaches end-of-life in **73 days**.

Underneath the tooling, the daemon is the real risk surface. Its request framing is genuinely
careful — size caps, deadlines, split-UTF-8 handling — but the commands behind it accept arbitrary
absolute filesystem paths, mutate shared player state without a lock, and on Windows listen on an
unauthenticated TCP port. Two defects were confirmed with runnable reproductions rather than by
inspection: a shallow copy that silently corrupts the user's persisted config, and a path-confinement
gap that lets any local client read audio files anywhere on disk.

**Top 5 by impact:**

- `F-CI-001` — CI is red on `main`; 20 of the last 30 runs failed, including the v0.10.1 release commit.
- `F-BUG-001` — `config.py:337` shallow-copies a nested class attribute, permanently corrupting default config process-wide (reproduced).
- `F-TEST-001` — 3 tests fail on every Windows runner because they patch a Unix-only syscall; this is what keeps CI red.
- `F-CI-002` — `mypy` exits 2 locally before checking anything; the CI type gate passes only because it runs a different invocation.
- `F-DEP-001` — `requires-python = ">=3.10"` is EOL on 2026-10-31 and is not covered by any CI cell.

## Baseline

| Row | Value | Evidence |
|---|---|---|
| Build | pass | `.venv/bin/python -c "import music_cli"` → `version: 0.10.1`; `python -m compileall -q music_cli` → exit 0; `.venv/bin/music-cli --version` → `music-cli, version 0.10.1` |
| Tests runnable | yes | `.venv/bin/pytest -q -p no:cacheprovider` starts and completes in 4.39s |
| Test pass rate | **403/403** (0 failed, 0 skipped) | `403 passed in 4.39s` |
| Coverage | **54.7%** lines (3646 stmts, 1652 missed) — **environment-dependent, see `F-TEST-007`**: 53% under an isolated `HOME`, 55% on the first run against an existing config dir | same command — `addopts` in `pyproject.toml:128` forces `--cov`; three runs at one commit gave 53% / 55% / 54.69% |
| Lint | 0 errors | `.venv/bin/ruff check .` → `All checks passed!` (exit 0) |
| Format | ruff-format clean (50 files); **black wants 2 files** | `ruff format --check .` → `50 files already formatted`; `black --check .` → `2 files would be reformatted` (both in `tests/`) |
| Typecheck | **BROKEN — exit 2, 0 files checked** | `.venv/bin/mypy music_cli` → `numpy/__init__.pyi:737: error: Type statement is only supported in Python 3.12 and greater [syntax]` … `errors prevented further checking` |
| Security scan | 0 findings (with 5 rules skipped) | `.venv/bin/bandit -q -c pyproject.toml -r music_cli` → exit 0 |
| CI | 2 workflows; **last run on `main` FAILED**; 20 fail / 7 pass / 3 cancelled of last 30 | `gh run list --workflow=ci.yml --branch=main -L 30`; run `32255629648` — Windows 3.12 and 3.13 cells failed |
| Runtime declared vs installed | declared `>=3.10` (classifiers stop at 3.12); installed **3.14.7** | `pyproject.toml:10`, `pyproject.toml:29`, `.venv/bin/python -V` |
| Lockfile | **missing** — no `poetry.lock`, `uv.lock`, `requirements*.txt`, or constraints file | `git ls-files \| grep -iE 'lock\|requirements'` → no matches |
| Pre-commit hooks | configured but **not installed** — 0 non-sample hooks | `ls .git/hooks/` → 14 entries, all `*.sample` |
| Repo activity | last commit 2026-08-19 (audit day); **103 commits, all within 12 months** | `git log -1`, `git rev-list --count HEAD` |

**Verdict: AMBER** — it builds and the whole suite passes locally, but the typecheck gate cannot run
and CI does not go green on the default branch.

**Test command of record:** `.venv/bin/pytest -q -p no:cacheprovider` — every P0–P4 plan task's
acceptance criteria reference this at **≥ 403/403**. Pre ACs do not.

## Dimension coverage

| Dim | Disposition | Path | Findings |
|---|---|---|---|
| DEP | Audited | own probes (2 of 2 ecosystems: python, gh-actions) | 13 |
| BUG | Audited | delegated → `code-review` mode `review` | 22 |
| PERF | Audited | delegated → `code-review` mode `perf` | 7 |
| CLEAN | Audited | inline | 10 |
| DEAD | Audited | inline | 2 |
| UX | **Not Assessed — no application UI detected** | — | 0 |
| TEST | Audited | inline | 7 |
| CI | Audited | inline | 8 |
| SEC | Audited | inline | 3 |
| DOCS | Audited | inline | 5 |

`UX` skip rationale: zero `*.tsx/*.jsx/*.vue/*.svelte` files, no frontend dependencies, no template
directories. The single tracked `.html` (`assets/logo/preview.html`) is a static brand-asset preview,
not a product surface. `dont-make-me-think` was therefore **not invoked**, which also removes any
risk of its Redesign Mode touching files.

## Dependency currency

Network was available; latest versions came from the PyPI JSON API and the GitHub releases API.
`pip-audit` is **not installed** and is not in the `dev` extra, so **no advisory database was
consulted** — see Limitations. The installed `dev` environment is essentially current: `pip list
--outdated` reports 22 packages, all patch/minor drift. Every finding below is therefore about
**declared constraints**, not installed staleness.

| ID | Package | Ecosystem | Declared | Latest | Gap | Risk | Blast | Wave | Severity | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| F-DEP-002 | *(lockfile)* | python | none | — | n/a | build not reproducible | repo | W0 | High | repo-wide — no lock/constraints file tracked |
| F-DEP-001 | *(CPython)* | python | `>=3.10` | 3.14.7 | runtime | **EOL 2026-10-31** | repo | W3 | High | `pyproject.toml:10` |
| F-DEP-005 | transformers `[ai]` | python | `>=4.31,<4.51` | 5.15.1 | major (capped) | none | 3 files | W4 | Medium | `pyproject.toml:46` |
| F-DEP-006 | transformers `[minimax]` | python | `>=4.51,<5` | 5.15.1 | major (capped) | none | 3 files | W4 | Medium | `pyproject.toml:56` |
| F-DEP-007 | yt-dlp | python | `>=2023.1.0` | 2026.7.4 | floor 3.5 yr old | extraction breaks without updates | 1 file | W2 | Medium | `pyproject.toml:63` |
| F-DEP-003 | dbus-next | python | `>=0.2.3` | 0.2.3 | current | **unmaintained** (last release 2021-07-25) + 0 import sites | 0 files | W2 | Medium | `pyproject.toml:39` |
| F-DEP-004 | winrt-Windows.Media.Playback | python | `>=2.0.0` | 3.2.1 | floor major×1 | 0 import sites | 0 files | W2 | Medium | `pyproject.toml:40` |
| F-DEP-009 | GitHub Actions (6) | actions | v4/v5/v1 tags | v7/v7/v3 | major×2–4 | mutable tag refs | 2 files | W4 | Medium | `.github/workflows/ci.yml:27` |
| F-DEP-010 | pre-commit hooks (3) | actions | v4.5.0 / v0.11.2 / v1.9.0 | v6.0.0 / v0.16.3 / v2.3.1 | major×1–2 | stale gate | 1 file | W2 | Medium | `.pre-commit-config.yaml:8` |
| F-DEP-011 | ruff (3-way skew) | python | hook `v0.11.2`; venv `0.15.22`; CI unpinned `0.16.3` | 0.16.3 | minor×5 | 3 different linters | 3 files | W2 | Medium | `.pre-commit-config.yaml:21` |
| F-DEP-008 | accelerate / soundfile | python | `>=0.20` / `>=0.12` | 1.14.0 / 0.14.0 | floor major×1 | 0 import sites | 0 files | W2 | Low | `pyproject.toml:50` |
| F-DEP-013 | diffusers `[ai]` | python | `>=0.15.0` | 0.39.0 | floor only (unbounded) | none | 3 files | W2 | Low | `pyproject.toml:47` |
| F-DEP-012 | *(classifiers)* | python | 3.10–3.12 | CI tests 3.12–3.14 | metadata drift | none | 1 file | W2 | Low | `pyproject.toml:29` |

**Runtime and toolchain**

| Component | Declared | Installed | Current stable | Status | Severity |
|---|---|---|---|---|---|
| CPython (floor) | `>=3.10` (`pyproject.toml:10`) | 3.14.7 | 3.14.7 | **3.10 EOL in 73 days**; 3.10/3.11 untested by CI | High |
| CPython (CI matrix) | 3.12, 3.13, 3.14 | — | 3.14.7 | current, but omits the declared floor | High (`F-CI-003`) |
| CPython (CI lint/build jobs) | 3.11 | — | 3.14.7 | inconsistent with the test matrix | Medium |
| mypy target | `python_version = "3.10"` (`pyproject.toml:114`) | mypy 2.3.0 | 2.3.1 | **incompatible with installed numpy stubs → mypy exits 2** | High (`F-CI-002`) |
| setuptools build backend | `>=61.0` | — | 84.0.0 | floor only, unbounded — resolves current | Low |

**Upgrade waves**

| Wave | Contents | Lands in |
|---|---|---|
| W0 | commit a lockfile / constraints file; install pre-commit hooks — `F-DEP-002`, `F-CI-004` | P0 |
| W1 | *(empty — no advisories obtainable; `pip-audit` not installed. See Limitations.)* | P1 |
| W2 | patch/minor + hook-rev batch: pre-commit hooks, ruff skew, yt-dlp floor, dead extras, classifiers — `F-DEP-003/004/007/008/010/011/012/013` | P1 |
| W3 | runtime decision: raise `requires-python` to `>=3.11` or add 3.10/3.11 CI cells — `F-DEP-001` | P2 |
| W4a | GitHub Actions majors, one action per task — `F-DEP-009` | P2 |
| W4b | transformers 4.x → 5.x (both extras) — `F-DEP-005`, `F-DEP-006` | P2 |

## Findings

### BUG

*Delegated to `code-review` mode `review`; full narrative with before/after code in
[`CODE_REVIEW.md`](./CODE_REVIEW.md). Severities re-ranked here against this skill's rubric.*

| ID | Severity | Evidence | Problem | Fix direction | Effort |
|---|---|---|---|---|---|
| F-BUG-001 | Critical | `music_cli/config.py:337` | `DEFAULT_CONFIG.copy()` is shallow over a nested **class attribute**; a corrupt config file plus any `set()` permanently mutates the class default for the whole process and writes it to disk. **Reproduced.** | Use `deepcopy` — `_recursive_mapping_merge` at `config.py:25` already imports it | S |
| F-BUG-002 | High | `music_cli/platform/__init__.py:155` | `get_media_controller()` imports `.media_controller`, which does not exist and `git log --all` shows was never committed; the import sits outside the `try:` so the `except ImportError` cannot catch it. Exported in `__all__`, zero call sites. | Delete the function, its `__all__` entry and type import; drop the two orphan runtime deps | S |
| F-BUG-003 | High | `music_cli/sources/local.py:25` | No path confinement: absolute paths bypass `music_dir` entirely, so an IPC client can play **any** audio file on the filesystem. **Reproduced.** | Resolve against `music_dir` and reject with `is_relative_to`, or make out-of-tree an explicit opt-in | S |
| F-BUG-004 | High | `music_cli/platform/ipc.py:245` | Windows TCP transport binds `127.0.0.1:44556` with **no authentication**; the Unix transport is `chmod 0600`. The two are presented as interchangeable but carry different guarantees. | Require a token written to the config dir with owner-only perms, or use a named pipe with an ACL | M |
| F-BUG-006 | High | `music_cli/daemon.py:871` | `asyncio.create_task(self.stop())` keeps no reference (`RUF006`); the shutdown task can be GC'd, so the daemon acknowledges `shutting_down` and keeps running. Same at `:457` and `:147`. | Hold tasks in a set with an `add_done_callback` discard | S |
| F-BUG-007 | High · *also CLEAN* | `music_cli/daemon.py:302` | `_cmd_play` mutates `_auto_play`, `_current_mood`, and the player across `await` points with **no lock**, so concurrent plays orphan an ffplay process. It is simultaneously the worst readability offender: complexity **31**, 36 branches, 80 statements, 151 lines. | Serialise state-mutating handlers behind one `asyncio.Lock`, then decompose per playback mode | L |
| F-BUG-008 | High | `music_cli/daemon.py:886` | `_pid_alive` only asks whether *a* process holds the PID. After PID reuse, `is_daemon_running()` returns True forever and every command fails until the user manually deletes the PID file. | Verify identity — a start-time/nonce recorded with the PID, or a successful `ping` before trusting it | M |
| F-BUG-009 | High | `install.sh:177` | `detect_os` accepts `mingw/msys/cygwin` as `windows` (`:55`) then hardcodes `$INSTALL_DIR/bin/python`; Windows venvs use `Scripts/`, so line 181 fails under `set -e`. | Detect the venv bindir after creation, or `die` early with a clear message | S |
| F-BUG-010 | High | `install.sh:206` | `rm -f "$link_target"` deletes whatever sits at `~/.local/bin/mc` — **`mc` is GNU Midnight Commander's binary** — with no ownership check, prompt, or backup, from a documented `curl \| bash`. | Skip and warn unless the existing target resolves into `$INSTALL_DIR`; gate override on `FORCE_LINK=1` | S |
| F-BUG-005 | Medium | `music_cli/platform/ipc.py:133` | Socket is created with umask-derived perms and only narrowed to `0600` on the *next* statement — a TOCTOU window. `ruff` also flags the blocking `pathlib` call in an async function (`ASYNC240`). | Set umask around the bind, or bind inside a `0700` directory | S |
| F-BUG-011 | Medium | `music_cli/cli.py:156` | Daemon startup sends stdout **and stderr** to `DEVNULL` (`:180`, `:189`), then reports the bare string `Failed to start daemon` — no traceback, no log path, nothing to read afterwards. | Redirect child stderr to a log file under the config dir and print that path on failure | S |
| F-BUG-012 | Medium | `music_cli/daemon.py:294` | `return {"error": str(e)}` hands raw exception text — including absolute filesystem paths — to an unauthenticated client. | Return a generic message; log the detail server-side | S |
| F-BUG-013 | Medium | `music_cli/config.py:308` | Config dir created with default perms (typically `0755`) though it holds the socket, PID file, history, and YouTube cache. | Create `0o700` | S |
| F-BUG-014 | Medium | `music_cli/hf_cache.py:166` | `snapshot_download` and five `from_pretrained` calls have no `revision=` pin, and `B615` is globally skipped at `pyproject.toml:137`, hiding it from Bandit. `trust_remote_code` is left `False`, so this is supply-chain drift, not RCE. | Pin a revision per model; drop the blanket `B615` skip | M |
| F-BUG-015 | Medium | `music_cli/player/ffplay.py:166` | `preexec_fn=os.setsid` is documented-unsafe with threads, and `cli.py` does start threads. | Use `process_group=0` (3.11+), gated on the `requires-python` decision in `F-DEP-001` | S |
| F-BUG-016 | Low | `music_cli/sources/radio.py:12` | YouTube detection is a substring test, so `https://evil-youtube.com.attacker.net/x` matches. Same shape at `daemon.py:337`. | Reuse the regex check already written at `sources/youtube.py:45` | S |
| F-BUG-017 | Low | `music_cli/player/ffplay.py:108` | Liveness inferred from a 0.1 s sleep then a returncode check; a process dying at 150 ms still reports as playing. | Use `wait()` with a timeout instead of sleep-then-poll | S |
| F-BUG-018 | Low | `install.sh:243` | 15 × `SC2059` — user-controlled `INSTALL_DIR` and `EXTRAS` interpolated into `printf` **format** strings. | `printf '%s' "$var"` | S |
| F-BUG-019 | Low | `install.sh:103` | `[ "$minor" -ge 10 ]` rejects a hypothetical Python 4.0 that satisfies `>=3.10`. | Compare on the version tuple | S |
| F-BUG-020 | Low | `install.sh:26` | `BRANCH="main"` assigned, never used (`SC2034`). | Delete | S |
| F-BUG-021 | Low | `music_cli/sources/youtube.py:42` | `_clean_url` strips **all** backslashes to undo paste corruption, silently altering legitimate URLs. | Narrow the fix to the known corruption pattern | S |
| F-BUG-022 | Low | `music_cli/daemon.py:153` | PID-file write is unguarded; an unwritable config dir kills the daemon *after* the socket is already accepting connections. | Wrap and fail before binding | S |

### PERF

*Delegated to `code-review` mode `perf`. Two impacts are measured on synthetic workloads, not estimated.*

| ID | Severity | Evidence | Problem | Fix direction | Effort |
|---|---|---|---|---|---|
| F-PERF-002 | High | `music_cli/history.py:99` | History is append-only with **no cap and no rotation**; every read path funnels through `get_all()`, which parses the entire file. `get_by_index(1)` — "replay last track" — pays full cost for one entry. **Measured: 2.3 ms @1k → 42.6 ms @18k (3.5 MB, ≈1 yr at 50 tracks/day) → 120.0 ms @50k.** Sibling `youtube_history.py:114` already caps at 1000. | Apply the same cap; read backwards for index lookups | M |
| F-PERF-001 | Medium | `music_cli/sources/local.py:57` | `scan_directory` issues a **full recursive `rglob` per extension** — 6 complete traversals per scan — and auto-play rescans on every track end (`daemon.py:461`). **Measured on 10,000 files / 800 dirs: 296.6 ms → 90.2 ms, 3.3×.** | One `rglob("*")` filtered on suffix; cache against directory mtime | S |
| F-PERF-003 | Medium | `music_cli/ai_tracks.py:131` | `add_track` does load-all → append → rewrite-all: O(N) per add, **O(N²)** across N adds. Same pair at `:179` and `:200`. | Switch to JSON Lines with an append, matching `history.py` | S |
| F-PERF-004 | Low | `music_cli/sources/radio.py:34` | `get_radios()` re-reads and re-parses `radios.txt` on every call; four lookup methods call it, several per `_cmd_play`. | Cache the parsed list on `Config`, invalidate on mtime | S |
| F-PERF-005 | Low | `music_cli/sources/local.py:76` | `limit` applied *after* the full 6-walk scan, then a redundant `.exists()` stat per file. | Apply the limit during iteration | S |
| F-PERF-006 | Low | `music_cli/daemon.py:266` | 19-entry dispatch dict of bound methods rebuilt per IPC request — the daemon's hottest path. | Build once in `__init__` | S |
| F-PERF-007 | Low | `music_cli/sources/local.py:60` | `sorted()` on the full listing even when the only caller wants one random element. | Sort in `list_tracks`, not the shared scan | S |

### CLEAN

*Measured mechanically with `ruff --isolated --select C901,PLR0911,PLR0912,PLR0913,PLR0915` — no
`pyproject.toml` was modified.*

| ID | Severity | Evidence | Problem | Fix direction | Effort |
|---|---|---|---|---|---|
| — | — | `music_cli/daemon.py:302` | *See `F-BUG-007` — same line, also a CLEAN issue (complexity 31 / 36 branches / 80 statements). Excluded from counts.* | — | — |
| F-CLEAN-002 | Medium | `music_cli/daemon.py:50` | `_JSONRequestFramer.feed` — complexity 21, 21 branches. Correct and well-tested, but a single 52-line state machine. | Table-driven states, or accept with a documented rationale | M |
| F-CLEAN-003 | Medium | `music_cli/cli.py:334` | `play()` — 97 lines, complexity 13, 13 branches, **7 parameters**. | Extract per-mode handlers; group options into a dataclass | M |
| F-CLEAN-004 | Medium | `music_cli/daemon.py:540` | `_cmd_ai_play` — 104 lines, complexity 12, **9 returns**. | Extract generation setup and error mapping | M |
| F-CLEAN-005 | Medium | `music_cli/daemon.py:645` | `_cmd_ai_replay` — 91 lines, **10 returns**. | Same as above; share the extracted helpers | M |
| F-CLEAN-006 | Medium | `music_cli/client.py:35` | `send_command` — complexity 11, 13 branches, mixing connect / frame / decode / error-map in one method. | Split transport from protocol | S |
| F-CLEAN-007 | Medium | `music_cli/cli.py:1` | 1658 lines / 52 KB holding all 14 command groups plus animation, aliasing, and daemon bootstrap — a god module. | Split into `cli/` with one module per command group | L |
| F-CLEAN-008 | Medium | `music_cli/daemon.py:112` | `MusicDaemon` — 968-line module; the class owns 19 command handlers, request framing, playback, history, and PID management. | Extract a command-handler registry and a lifecycle manager | L |
| F-CLEAN-009 | Medium | `pyproject.toml:69` | **Two formatters configured**: `black>=23.0` + `[tool.black]` (`:92`) alongside `ruff-format` in pre-commit (`:25`) and CI (`ci.yml:41`). They agree on `music_cli/` today but **disagree on `tests/`** — black wants 2 files reformatted that ruff considers correct. | Drop black and its config; standardise on `ruff format` | S |
| F-CLEAN-010 | Low | `music_cli/sources/ai_generator.py:80` | `_get_strategy` and `generate` (`:212`) both at complexity 11; `generate` also has 6 params and 7 returns. Invisible to coverage (see `F-TEST-005`). | Dispatch table for strategy selection | M |
| F-CLEAN-011 | Low | `music_cli/history.py:74` | `PLR0913` at 5 more sites — `log` (6 params), `client.py:106` (6), `youtube_history.py:92` (6), `ai_generator.py:212` (6), `cli.py:334` (7). | Introduce entry/request dataclasses | S |

### DEAD

| ID | Severity | Evidence | Problem | Fix direction | Effort |
|---|---|---|---|---|---|
| F-DEAD-001 | Low | `README.backup.md:1` | A 426-line stale duplicate README tracked at the repo root, last touched 2026-03-18 while `README.md` moved on to 550 lines on 2026-08-17. | Delete — git history is the backup | S |
| F-DEAD-002 | Low | `music_cli/daemon.py:479` | 21 × `ARG002` unused arguments — 9 in `daemon.py` handlers, 4 in `platform/ipc.py`, 5 in AI strategies, 2 in `progress_callback.py`. Mostly interface conformance, but unmarked. | Rename to `_args` or add explicit `# noqa` with a reason | S |
| — | — | `music_cli/platform/__init__.py:155` | *See `F-BUG-002` — dead **and** crashing. Excluded from counts.* | — | — |
| — | — | `pyproject.toml:39-40, 50, 59` | *See `F-DEP-003/004/008` — `dbus-next`, `winrt-*`, `accelerate`, `soundfile` declared with **zero import sites**. Excluded from counts.* | — | — |

**Checked and clean** (named so the absence is not mistaken for an unchecked box):

- **Duplication** — exact AST clone detection (≥6 statements repeated ≥3×) and identifier-blind
  structural clone detection (≥5 statements, names/constants normalised) found only import blocks and
  sliding-window artifacts. **No real logic duplication exists in this codebase.**
- **TODO / FIXME / HACK / XXX** — 0 occurrences across `music_cli/`, `tests/`, and `install.sh`.
- **Commented-out code** — `ruff --select ERA001` reports 0.
- **Unreferenced modules** — every non-`__init__` module under `music_cli/` is imported somewhere.

### TEST

| ID | Severity | Evidence | Problem | Fix direction | Effort |
|---|---|---|---|---|---|
| F-TEST-001 | Critical | `tests/test_ffplay.py:1` | `TestFFplayPlayerImmediateExit` patches `os.killpg`, which **does not exist on Windows** → `AttributeError: <module 'os' (frozen)> does not have the attribute 'killpg'`. 3 tests fail on every Windows cell of every run, which is the direct cause of `F-CI-001`. | Guard with `@pytest.mark.skipif(sys.platform == "win32")` or patch the module-level symbol | M |
| F-TEST-007 | High | `music_cli/config.py:303` | **The suite is not hermetic.** `Config.__init__` calls `_ensure_config_dir()` as a constructor side effect, and `get_config()` is a module-level singleton defaulting to the real `~/.config/music-cli/`. There is no `tests/conftest.py` and no test isolates `HOME` or `XDG_CONFIG_HOME`, so merely constructing `MusicDaemon()` or `DaemonClient()` writes `config.toml`, `radios.txt`, `history.jsonl`, and `ai_tracks.json` into the developer's real config directory — **verified by running the suite under a fake `HOME`**. Consequences: coverage is non-deterministic (53% isolated / 55% first run / 54.69% after), runtime varies 3× (13.1s cold vs 4.2s warm), and **the suite can spawn a real background daemon** — this audit's own baseline probe did so (see Limitations). | Add `tests/conftest.py` with an autouse fixture pointing `HOME`/config at `tmp_path`; reset the `get_config` singleton between tests | M |
| F-TEST-002 | High | `pyproject.toml:128` | Coverage is measured (55%) but **never enforced** — no `--cov-fail-under` in `addopts` or CI, so coverage can regress silently. | Add `--cov-fail-under` at the current floor, then ratchet | M |
| F-TEST-003 | High | `tests/test_installer.py:6` | The only installer test asserts **three substrings of the script's source text**. It cannot catch `F-BUG-009` (Windows `bin/` vs `Scripts/`) or `F-BUG-010` (clobbering `mc`) — both live in the very file it "covers". | Add behavioural tests against a fake `$HOME`/`$INSTALL_DIR`; run `shellcheck` in CI | M |
| F-TEST-004 | Medium | `music_cli/sources/ai_models/progress_callback.py:3` | 66 statements at **0% coverage** — the only module in the package with none. Reached solely through a lazy import at `model_strategy.py:97`. | Unit-test the callback wrapper directly | M |
| F-TEST-005 | Medium | `pyproject.toml:142` | `omit = ["music_cli/sources/ai_generator.py"]` hides a module containing **two of the eight highest-complexity functions** from the coverage metric entirely. | Remove the omit and let the real number show; test with AI deps mocked | S |
| F-TEST-006 | Medium | `music_cli/daemon.py:1` | Lowest-covered modules: `bark` 16%, `musicgen` 18%, `youtube` 20%, `audioldm` 21%, `radio` 26%, `player_control` 27%, `youtube_history` 36%, `hf_cache` 37%, **`daemon` 38%**. The daemon is the largest attack surface and the least covered non-optional module. | Prioritise `daemon.py` and `platform/` via `test-coverage`; treat AI strategies as a separate optional-dep tier | L |

### CI

| ID | Severity | Evidence | Problem | Fix direction | Effort |
|---|---|---|---|---|---|
| F-CI-001 | Critical | `.github/workflows/ci.yml:52` | **`main` is red.** 20 failures / 7 successes / 3 cancelled across the last 30 runs, including the `v0.10.1` release commit and HEAD. A permanently-red default branch means CI signals nothing. | Fix `F-TEST-001`, then treat red `main` as a stop-the-line event | M |
| F-CI-002 | High | `.github/workflows/ci.yml:47` | CI runs `mypy music_cli/ --ignore-missing-imports` on Python **3.11**, while `pyproject.toml:114` targets `python_version = "3.10"`. Locally that config makes mypy **exit 2 without checking anything** (numpy stubs need 3.12+). The gate passes in CI purely because it uses different settings than any developer does. | Align `python_version` with the supported floor; run mypy through the same config in CI and locally | M |
| F-CI-003 | High | `.github/workflows/ci.yml:59` | Matrix is `["3.12","3.13","3.14"]` but `requires-python = ">=3.10"`. **The two oldest supported versions are never built or tested** — and 3.10 is EOL in 73 days. | Either add 3.10/3.11 cells or raise `requires-python` to `>=3.12`. Do not ship an untested claim | S |
| F-CI-004 | Medium | `.pre-commit-config.yaml:3` | The file documents `pre-commit install`, but `.git/hooks/` contains **0 non-sample hooks** — the local gate has never been armed in this clone. CI runs the hooks, so drift lands and is caught late. | Document in `CONTRIBUTING.md` and verify in a bootstrap script | S |
| F-CI-005 | Medium | `.github/workflows/ci.yml:37` | `pip install ruff mypy bandit[toml]` — **unpinned**. The lint gate silently changes whenever any of the three releases; combined with `F-DEP-011` there are three different ruff versions in play. | Pin to the same versions the pre-commit hooks use | S |
| F-CI-006 | Medium | `.github/workflows/ci.yml:93` | Coverage is uploaded to Codecov but no threshold gates the build (`fail_ci_if_error: false`); a drop to 10% is a green run. | Gate with `--cov-fail-under` — pairs with `F-TEST-002` | S |
| F-CI-007 | Medium | `install.sh:1` | `install.sh` is shipped code the README asks users to pipe into `bash`, yet **`shellcheck` runs in neither CI nor pre-commit**. It is installed on this machine and finds `F-BUG-018` and `F-BUG-020` immediately. | Add a `shellcheck` job and pre-commit hook | S |
| F-CI-008 | Low | `.github/workflows/ci.yml:6` | No `permissions:` block, so every job gets the repository default token scope. `release.yml:11` correctly narrows to `contents: write`; `ci.yml` does not. | Add `permissions: contents: read` at workflow level | S |
| — | — | `.github/workflows/ci.yml:27` | *See `F-DEP-009` — actions pinned to mutable major tags rather than SHAs. Excluded from counts.* | — | — |

### SEC

| ID | Severity | Evidence | Problem | Fix direction | Effort |
|---|---|---|---|---|---|
| F-SEC-001 | Medium | `README.md:57` | The primary documented install is `curl -sSL … \| bash` **without `-f`**. Without `--fail`, an HTTP error page (proxy notice, 404 body, captive portal) is delivered with exit 0 and piped straight into `bash`. Repeated at `:97` and `:169`. | Add `-f`; prefer `curl -fsSL … -o install.sh && bash install.sh` as the headline form | S |
| F-SEC-002 | Low | `README.md:136` | The "review before running" variant is offered, but **no checksum or signature** is published for `install.sh`, so a reviewed script and an executed script cannot be proven identical. | Publish a SHA-256 alongside releases | S |
| F-SEC-003 | Low | `SECURITY.md:40` | The project's own policy says "Avoid `shell=True` in subprocess calls unless strictly necessary", while `player/ffplay.py:162` uses `create_subprocess_shell`. The usage **is** safe (both paths `shlex.quote`d, volume int-typed) and arguably necessary for the pipe — but the policy and the code should not appear to contradict. | Note the reviewed exception in `SECURITY.md` or beside the call | S |

**Checked and clean:**

- **Committed secrets** — `git log --all -p -S` for key patterns, history search for `.env`/`*.pem`/
  `*.key`/`secrets*`, and a regex sweep for `api_key|secret|token|password|bearer` assignments across
  all tracked `.py`/`.sh`/`.toml`/`.yml` files: **zero hits**.
- **Bandit** — `bandit -c pyproject.toml -r music_cli` exits 0. Caveat: 5 rules are skipped, and
  `B615` in particular hides `F-BUG-014`.
- **Injection sinks** — the only `shell=True`-equivalent is `ffplay.py:162`, reviewed above; no
  `eval`, `exec`, or `os.system` anywhere.

### DOCS

| ID | Severity | Evidence | Problem | Fix direction | Effort |
|---|---|---|---|---|---|
| F-DOCS-001 | Medium | `docs/development.md:127` | `pip install dist/music_cli-0.1.0-py3-none-any.whl` — **wrong package name** (the wheel is `coder_music_cli`) and a version 10 releases stale. Copy-pasting it fails. | Use a glob: `pip install dist/*.whl` | S |
| F-DOCS-002 | Medium | `CONTRIBUTING.md:155` | Contributors are told to run `black music_cli/` (also `docs/development.md:86`) while CI enforces `ruff format --check` and pre-commit runs `ruff-format`. See `F-CLEAN-009`. | Update both docs once black is dropped | S |
| F-DOCS-003 | Medium | `pyproject.toml:18` | Package keywords advertise `media-keys`, `mpris`, and `now-playing` — a feature whose implementation modules do not exist (`F-BUG-002`). These keywords are how PyPI search surfaces the project. | Remove the three keywords | S |
| F-DOCS-004 | Medium | `README.md:539` | Credits pyobjc for "media key support" and dbus-next for "Linux MPRIS media controls" (`:540`) — neither is implemented, and dbus-next has zero import sites. | Remove both rows with `F-DEP-003` | S |
| F-DOCS-006 | Low | `music_cli/platform/__init__.py:11` | The module docstring lists "Media controller abstraction (MPRIS, macOS Now Playing, Windows SMTC)" as a key component. `docs/architecture.md:225-231` correctly lists only the 4 modules that exist — the code docstring is the drifted one. | Update with `F-BUG-002` | S |
| — | — | `pyproject.toml:29` | *See `F-DEP-012` — classifiers stop at 3.12 while CI tests 3.14. Excluded from counts.* | — | — |

**Checked and clean:** every documented top-level command was executed against the real CLI. All 17
resolve, including `mc radios`, `mc update-radios`, and `mc volume` — these are **working hidden
aliases**, correctly presented at `README.md:240-242` as a legacy→new mapping table, not drift.

## Cross-cutting patterns

- **The quality apparatus is not wired to the quality gate.** Three linters, pre-commit, Bandit, and a
  9-cell matrix exist, but mypy can't run locally, pre-commit isn't installed, coverage isn't
  enforced, shellcheck isn't run, lint tools are unpinned, and `main` is red. Every one of these
  passes a casual "does the repo have CI?" inspection. (`F-CI-001`, `F-CI-002`, `F-CI-004`,
  `F-CI-005`, `F-CI-006`, `F-CI-007`, `F-TEST-002`, `F-DEP-011`)
- **Declared platform support exceeds tested platform support.** Windows is in the classifiers, the
  matrix, the IPC layer, the player controller, and the installer — and is broken or unverified in
  each: tests fail there, the TCP transport is unauthenticated, and the installer references a
  directory that does not exist on Windows. The same shape applies to Python 3.10/3.11.
  (`F-TEST-001`, `F-BUG-004`, `F-BUG-009`, `F-CI-003`, `F-DEP-001`)
- **A removed feature left declarations behind everywhere but the code.** The media-controller
  feature is absent from the source yet still present in a crashing exported function, two runtime
  dependencies, three PyPI keywords, two README credit rows, and a module docstring.
  (`F-BUG-002`, `F-DEP-003`, `F-DEP-004`, `F-DOCS-003`, `F-DOCS-004`, `F-DOCS-006`)
- **Careful at the perimeter, unguarded behind it.** The daemon's request framer is the most rigorous
  code in the repository — and the handlers it feeds take arbitrary paths, race on shared state, leak
  exception text, and never authenticate. (`F-BUG-003`, `F-BUG-004`, `F-BUG-007`, `F-BUG-012`)
- **Append-only stores with no ceiling.** `history.py` and `ai_tracks.py` grow without bound and are
  fully re-parsed per read; `youtube_history.py` already solved this with a 1000-entry cap that the
  other two never adopted. (`F-PERF-002`, `F-PERF-003`)

## Artifacts written

| File | Why |
|---|---|
| `MODERNIZATION_REPORT.md` | this report |
| `MODERNIZATION_PLAN.md` | the derived plan |
| `CODE_REVIEW.md` | **declared artifact** — written by `code-review` mode `review` (`BUG` dimension) |

**Tracked files modified: 0.** `git status --porcelain` was empty before the run and lists only the
three untracked files above after it; `git diff` is byte-identical to the pre-run snapshot. Verified
before and after Phase 0 and again before this report.

Pre-existing and untouched (all gitignored, none created by this run): `.coverage` — **rewritten** by
the test probe, as `addopts` forces `--cov`; `build/`, `dist/`, `coder_music_cli.egg-info/`,
`.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `.venv/`.

## Limitations

- **No vulnerability database was consulted.** `pip-audit` is not installed and is not in the `dev`
  extra, and no equivalent tool was available. Every `Risk` value in the DEP table is derived from
  release dates, maintenance status, and version gaps — **not from advisories**. There may be known
  CVEs in the dependency tree that this audit did not see. Wave `W1` is empty for this reason, not
  because the tree is clean. Installing `pip-audit` is the first task of P1.
- **`UX` — Not Assessed**: no application UI. CLI and terminal ergonomics (help text, error copy,
  prompt flow) were consequently **not** audited as a UX dimension; `dont-make-me-think` targets
  visual interfaces and was not invoked.
- **Agent tool available but not used.** Repo size (54 tracked source files) meets this skill's
  ≥50-file threshold, which selects parallel `dimension-auditor` subagents. Session policy prohibits
  spawning subagents unless the user requests them, so **all ten dimensions ran inline and
  sequentially** — including `plan-architect` and `plan-validator`. This is reduced depth relative to
  a parallel run, and the validator loses the fresh-context independence its design assumes.
- **Optional extras are not installed.** `torch`, `transformers`, `diffusers`, `scipy`, `accelerate`,
  `soundfile`, `tqdm`, and `yt-dlp` are absent from the venv, so the `ai`, `minimax`, and `youtube`
  code paths were reviewed **statically only** and their low coverage figures reflect an environment
  where those imports fail. Whether the pinned AI stack even resolves on Python 3.14 was not
  determined.
- **Packaging was not re-probed.** `python -m build` provisions an isolated environment over the
  network and rewrites `dist/`, so the Build baseline row uses an import + `compileall` + entry-point
  check instead. `twine check` was likewise not run.
- **`mypy` produced no findings** because it exits 2 before checking any file. Type-safety issues in
  this codebase are therefore entirely unmeasured — that absence is itself `F-CI-002`.
- **This audit's test probe started a background daemon on the machine.** The suite is not hermetic
  (`F-TEST-007`), and the timeline is unambiguous: the pre-run snapshot was taken at 15:03:45, the first
  `pytest` run began at ~15:04:05, and `~/.config/music-cli/music-cli.pid` is stamped **15:04:05**. A
  `python -m music_cli.daemon` process (PID 14601) is running as a result. It is **outside the repository**,
  so the read-only contract over tracked files is intact — but it is a real side effect of this audit and is
  reported rather than silently cleaned up, since stopping it is the user's call.
- **The suite also wrote to the real user config directory.** For the same reason, running the baseline
  probe touched `~/.config/music-cli/`. Nothing there was deleted, but `config.toml`, `radios.txt`,
  `history.jsonl`, and `ai_tracks.json` are read/written by the suite as a matter of course.
- **Coverage is a range, not a number.** Three runs at commit `0f00ec5` produced 53%, 55%, and 54.69%
  depending on the state of the config directory. The baseline records 54.7% as the steady-state value;
  any coverage gate must be derived from a measured run rather than assumed — `--cov-fail-under=55`
  **fails today** at the true 54.69%.
- **A nested `package.json` was not probed.** `scripts/dep_scan.sh` reported partial coverage and named
  `.opencode/package.json`. It is excluded deliberately: `.opencode/` is gitignored AI-tool configuration,
  not project source, and contains no code shipped by this package. The "2 of 2 ecosystems" figure in the
  coverage table counts only tracked, shipped manifests.
- **CI history is a 30-run window.** The 20/7/3 figure covers the most recent 30 `ci.yml` runs on
  `main`, not the project's full history.
- Performance impacts for `F-PERF-001` and `F-PERF-002` are **measured on synthetic workloads**
  (a generated 10,000-file library; generated history files at 1k/18k/50k entries) on this machine —
  they establish the scaling shape, not absolute numbers on any user's hardware. The other five PERF
  findings are reasoned from code, not measured.

## Next step

The plan derived from this report: [`MODERNIZATION_PLAN.md`](./MODERNIZATION_PLAN.md).
