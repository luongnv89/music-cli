# Modernization Plan — music-cli

Derived from [`MODERNIZATION_REPORT.md`](./MODERNIZATION_REPORT.md) · **Baseline at audit:** AMBER
**Test command of record:** `.venv/bin/pytest -q -p no:cacheprovider` · **Pass rate at audit:** `403/403` · **Coverage at audit:** `54.69%` (environment-dependent — 53% isolated, see `F-TEST-007`)

Every **P0–P4** task's acceptance criteria include *"`.venv/bin/pytest -q -p no:cacheprovider` passes
at ≥ 403/403"*. The baseline is AMBER, not RED, so no build-command substitution applies — the suite
runs and passes today, and no task may regress it.

**Pre** is exempt from that assertion. Its acceptance criteria are install/run notes plus creating
`CLAUDE.md` and `AGENTS.md`; no P0–P4 task starts before milestone `ME`.

> **Read this first.** The suite is green locally and has been all along. What is broken is the
> *verification apparatus around it*: `mypy` cannot run, CI is red on `main`, coverage is measured but
> never enforced, pre-commit is configured but not installed, and two of the supported Python versions
> are never tested. P0 is therefore not "fix the build" — it is **make the gate mean what it claims**.
> Every later phase depends on that, because until CI is trustworthy no upgrade can be verified.

## At a glance

| Phase | Sprints | Tasks | Closes | Milestone |
|---|---|---|---|---|
| Pre — Agent environment | 1 | 3 | — (enables ME) | `ME` |
| P0 Stabilize | 1 | 9 | 2 Critical, 5 High, 4 Medium, 1 Low | `M0` |
| P1 Secure & Patch | 2 | 14 | 1 Critical, 6 High, 10 Medium, 5 Low | `M1` |
| P2 Modernize | 2 | 9 | 1 High, 4 Medium | `M2` |
| P3 Clean & Harden | 2 | 13 | 3 High, 12 Medium, 5 Low | `M3` |
| P4 Polish | 1 | 6 | 1 High, 6 Medium, 11 Low | `M4` |
| **Total** | **9** | **54** | **3 Critical · 16 High · 36 Medium · 22 Low = 77** | |

**Critical path (21 days):** `Pre.1 → Pre.2 → 0.1 → 0.2 → 1.2 → 5.1 → 5.4 → 6.1 → 6.2 → 6.3`
*(`Pre.3` substitutes for `Pre.2` at position 2 — both are 1-day tasks depending on `Pre.1` and blocking `0.1`, so the chain has two equally-long variants. Every other position is unique.)*

This is the longest chain in the dependency table, recomputed from it rather than asserted. It runs
through the daemon: nothing can be safely restructured (`6.1`–`6.3`) until characterization tests
exist (`5.4`), those tests are only meaningful once command handling is serialised (`5.1`), and that
change is only verifiable once CI is green (`0.2`). Runners-up finish at 18 days (`6.2`) and 17 days
(`6.5`, `7.1`, `7.5`), so shortening the plan means attacking the daemon chain — nothing else.

Nothing in P0–P4 starts before `ME`. Nothing outside P0 starts before `M0`.

---

## Phase Pre — Agent environment

**Goal:** an environment an AI agent can install, run, and verify without unwritten human context.
**Milestone `ME`:** `CLAUDE.md` and `AGENTS.md` both exist at the repo root (both **created** — neither is present today); the recorded build and test commands are documented in `CLAUDE.md` and in the Pre.1 notes.

### Sprint Pre — Agent-runnable environment

#### Task Pre.1: Record how to install, run, and verify this project

**Description**: Capture what an agent cannot infer from the tree: that a `.venv/` exists and every tool must be invoked through it (`.venv/bin/pytest`, not bare `pytest` — the bare binaries on this machine resolve to a different Homebrew Python); that `ffplay` from FFmpeg is a hard runtime prerequisite; that the `ai`, `minimax`, and `youtube` extras are **not installed** and their code paths cannot be exercised without them; that `pyproject.toml:128` already forces `--cov`, so the test command needs no coverage flags. Serves milestone `ME`.

**Closes**: — (milestone-enabling: `ME`)

**Acceptance Criteria**:
- [ ] A written note covers: venv creation, `pip install -e ".[dev]"`, the FFmpeg prerequisite, each optional extra and what it unlocks, and the exact test command of record
- [ ] The note states that `mypy` currently exits 2 and that this is tracked as `F-CI-002`, so an agent does not mistake it for a broken environment
- [ ] A reader following the note from a clean checkout reaches a state where `.venv/bin/pytest -q -p no:cacheprovider` runs

**Dependencies**: None

**Effort**: S (1 day)

**Verify**: from a fresh clone, follow the note verbatim and run `.venv/bin/pytest -q -p no:cacheprovider`

#### Task Pre.2: Create CLAUDE.md

**Description**: `CLAUDE.md` is **absent** — run `/agent-config create` targeting it. It must carry the recorded build/test commands from Pre.1 and the repo's non-obvious etiquette: do not commit without being asked, never add `Co-Authored-By` trailers, and prefer `ruff format` over `black` once `F-CLEAN-009` is resolved. Serves milestone `ME`. Do not run the skill while planning.

**Closes**: — (milestone-enabling: `ME`)

**Acceptance Criteria**:
- [ ] `CLAUDE.md` exists at the repo root — `test -f CLAUDE.md`
- [ ] `CLAUDE.md` names the test command of record `.venv/bin/pytest -q -p no:cacheprovider` and the `.venv/bin/` invocation convention

**Dependencies**: Pre.1

**Effort**: S (1 day)

**Verify**: run `/agent-config create` targeting `CLAUDE.md`, then `grep -q 'pytest -q -p no:cacheprovider' CLAUDE.md`

#### Task Pre.3: Create AGENTS.md

**Description**: `AGENTS.md` is **absent** — run `/agent-config create` targeting it. Scope it to agent-definition content per agent-config's checklists; the build/test commands stay in Pre.1's notes and `CLAUDE.md` rather than being duplicated here. Serves milestone `ME`. Do not run the skill while planning.

**Closes**: — (milestone-enabling: `ME`)

**Acceptance Criteria**:
- [ ] `AGENTS.md` exists at the repo root — `test -f AGENTS.md`
- [ ] Its content follows agent-config's checklists and does not duplicate the command reference that lives in `CLAUDE.md`

**Dependencies**: Pre.1

**Effort**: S (1 day)

**Verify**: run `/agent-config create` targeting `AGENTS.md`, then `test -f AGENTS.md`

---

## Phase P0 — Stabilize

**Goal:** make the quality gate enforce what it advertises, so every later phase is verifiable.
**Milestone `M0`:** from a clean checkout, CI is **green on `main` across all 9 matrix cells**; `mypy` runs to completion under the project config and produces **identical results locally and in CI** (any remaining type errors tracked as issues, none silenced); the test suite is hermetic; a lockfile is committed; and a **derived** coverage floor is enforced in CI.

### Sprint 0 — Make the gate real

#### Task 0.1: Stop the Windows cells failing on a Unix-only syscall

**Description**: `tests/test_ffplay.py::TestFFplayPlayerImmediateExit` patches `os.killpg`, which does not exist on Windows, producing `AttributeError: <module 'os' (frozen)> does not have the attribute 'killpg'`. Three tests fail on every Windows cell of every run. This is the direct cause of `F-CI-001`, so it comes first.

**Closes**: `F-TEST-001`

**Acceptance Criteria**:
- [ ] The three tests either skip on Windows via `@pytest.mark.skipif(sys.platform == "win32", ...)` or patch a module-level indirection that exists on all platforms — chosen deliberately, not by whichever makes the error go away
- [ ] A CI run shows `Test (Python 3.12 / windows-latest)` and `Test (Python 3.13 / windows-latest)` both succeeding
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: Pre.2, Pre.3

**Effort**: M (2 days)

**Verify**: `gh run list --workflow=ci.yml --branch=main -L 1` reports `success`

#### Task 0.2: Restore green CI on `main` and defend it

**Description**: 20 of the last 30 `ci.yml` runs on `main` failed, including the `v0.10.1` release commit. A permanently-red default branch means CI signals nothing and regressions land unnoticed. Once 0.1 lands, confirm green and adopt a stop-the-line rule so red `main` is treated as an incident rather than the status quo.

**Closes**: `F-CI-001`

**Acceptance Criteria**:
- [ ] Three consecutive `ci.yml` runs on `main` conclude `success` across all 9 matrix cells
- [ ] `CONTRIBUTING.md` states that a red `main` blocks merges until fixed
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 0.1

**Effort**: M (2 days)

**Verify**: `gh run list --workflow=ci.yml --branch=main -L 3 --json conclusion` returns three `success`

#### Task 0.3: Repair the mypy gate so it runs at all

**Description**: `.venv/bin/mypy music_cli` exits **2** without checking a single file — `pyproject.toml:114` sets `python_version = "3.10"`, which the installed numpy stubs reject (`Type statement is only supported in Python 3.12 and greater`). CI passes only because `ci.yml:47` invokes mypy with different settings than any developer uses. The type-safety of this codebase is currently **unmeasured**.

**Closes**: `F-CI-002`

**Acceptance Criteria**:
- [ ] `.venv/bin/mypy music_cli` runs to completion (no exit-2 crash) and its full output is recorded; every real type error is filed as a tracked issue referenced from `M0` — none silenced with a blanket ignore. `M0` and `M3` require this tracked state, not necessarily exit 0
- [ ] CI runs mypy through the project's own `pyproject.toml` config, not a divergent inline invocation, so local and CI results match
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: Pre.2, Pre.3

**Effort**: M (2 days)

**Verify**: `.venv/bin/mypy music_cli; echo "exit=$?"` locally and the same command in CI produce the same exit code

#### Task 0.4: Commit a lockfile so builds are reproducible

**Description**: No `poetry.lock`, `uv.lock`, `requirements*.txt`, or constraints file is tracked. CI resolves dependencies fresh on every run across 9 cells, so a green build proves nothing about the next one and a bad upstream release breaks CI with no local reproduction. Every upgrade wave in P1 and P2 needs this to be attributable.

**Closes**: `F-DEP-002`

**Acceptance Criteria**:
- [ ] A lockfile or pinned constraints file for the `dev` extra is committed and referenced by the CI install step
- [ ] Two CI runs on the same commit install byte-identical dependency versions
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: Pre.2, Pre.3

**Effort**: M (2 days)

**Verify**: `git ls-files | grep -E 'lock|constraints'` returns the committed file, and the CI log shows it being used

#### Task 0.5: Make the CI matrix cover the Python floor the package declares

**Description**: `pyproject.toml:10` promises `>=3.10` but `ci.yml:59` tests only `["3.12","3.13","3.14"]`. The two oldest supported versions are never built or tested — the package makes a compatibility claim it does not verify. This task makes the matrix and the declaration agree; whether the *floor itself* should move is `F-DEP-001`, decided in P2 once an advisory baseline exists.

**Closes**: `F-CI-003`

**Acceptance Criteria**:
- [ ] The matrix in `ci.yml` covers every version `requires-python` admits, or `requires-python` is narrowed to exactly what the matrix tests — the two agree either way
- [ ] A CI run shows a passing cell for the lowest version `requires-python` admits
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 0.1

**Effort**: S (1 day)

**Verify**: `python3 -c` comparison of the `requires-python` floor against the matrix list in `ci.yml` reports no gap

#### Task 0.6: Pin the CI lint tooling, arm pre-commit, and add shellcheck

**Description**: `ci.yml:37` installs `ruff mypy bandit[toml]` **unpinned**, so the lint gate silently changes whenever any of the three releases. `.git/hooks/` contains 0 non-sample hooks, so the local gate has never been armed. And `install.sh` is shipped code the README pipes into `bash`, yet `shellcheck` runs in neither CI nor pre-commit — it finds `F-BUG-018` and `F-BUG-020` immediately.

**Closes**: `F-CI-005`, `F-CI-004`, `F-CI-007`

**Acceptance Criteria**:
- [ ] `ci.yml` pins ruff, mypy, and bandit to explicit versions matching the pre-commit hook revisions
- [ ] `CONTRIBUTING.md` documents `pre-commit install` in the setup steps, and a bootstrap check reports whether the hook is armed
- [ ] A `shellcheck` step runs against `install.sh` in CI and as a pre-commit hook
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 0.4

**Effort**: S (1 day)

**Verify**: `shellcheck install.sh` runs in CI, and `grep -E 'ruff==|mypy==|bandit' .github/workflows/ci.yml` shows pinned versions

#### Task 0.7: Enforce a coverage floor instead of just reporting one

**Description**: Coverage is measured and uploaded to Codecov, but nothing gates on it — `fail_ci_if_error: false` and no `--cov-fail-under` anywhere. A drop to 10% is a green run. **The floor must be derived from a measured run, not assumed:** the displayed `55%` is rounded, the true value is **54.69%**, and `--cov-fail-under=55` **fails today** — verified during the audit. Depends on 0.9 because coverage is not reproducible until the suite is hermetic (it ranged 53%–55% across three runs at one commit).

**Closes**: `F-TEST-002`, `F-CI-006`

**Acceptance Criteria**:
- [ ] The floor is derived from a recorded hermetic run — the measured percentage rounded **down** to a whole number — and the measured value is quoted in the PR
- [ ] `.venv/bin/pytest -q -p no:cacheprovider --cov-fail-under=<derived floor>` exits 0 on three consecutive runs, proving the floor does not flake
- [ ] A deliberate coverage regression (temporarily deleting a test file) makes CI fail, proving the gate bites
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 0.2, 0.9

**Effort**: S (1 day)

**Verify**: at the derived floor the command exits 0; at `<derived floor>+1` it exits non-zero

#### Task 0.8: Scope the CI workflow token

**Description**: `ci.yml` has no `permissions:` block, so every job runs with the repository's default token scope. `release.yml:11` already narrows correctly to `contents: write`; `ci.yml` should be read-only.

**Closes**: `F-CI-008`

**Acceptance Criteria**:
- [ ] `ci.yml` declares `permissions: contents: read` at workflow level
- [ ] All 9 matrix cells plus the lint, build, and pre-commit jobs still pass under the narrowed scope
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 0.2

**Effort**: S (1 day)

**Verify**: `grep -A1 '^permissions:' .github/workflows/ci.yml` and a green run

#### Task 0.9: Make the test suite hermetic

**Description**: The suite reads and writes the developer's **real** `~/.config/music-cli/`. `Config.__init__` calls `_ensure_config_dir()` as a constructor side effect (`config.py:303`), and `get_config()` is a module-level singleton defaulting to the real directory — so merely constructing `MusicDaemon()` or `DaemonClient()` creates `config.toml`, `radios.txt`, `history.jsonl`, and `ai_tracks.json` there. There is no `tests/conftest.py` and nothing isolates `HOME`. Three consequences, all verified during the audit: coverage is non-deterministic (53% under an isolated `HOME`, 55% on a first run, 54.69% thereafter), runtime varies 3× (13.1s cold vs 4.2s warm), and **the suite can spawn a real background daemon** — the audit's own baseline probe did exactly that, leaving a live `music_cli.daemon` process. This blocks 0.7: no coverage floor is meaningful while the number depends on the developer's home directory.

**Closes**: `F-TEST-007`

**Acceptance Criteria**:
- [ ] `tests/conftest.py` exists with an autouse fixture that points `HOME`/config at `tmp_path` and resets the `get_config` singleton between tests
- [ ] Running the suite with a fake `HOME` leaves **zero** files in the real `~/.config/music-cli/` — verified by comparing a `find` listing and mtimes before and after
- [ ] The suite spawns no background process: after a full run, no new `music_cli.daemon` process exists
- [ ] Two consecutive runs report **identical** total coverage, and that figure matches a run under a fresh `HOME`
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 0.2

**Effort**: M (2 days)

**Verify**: `before=$(find ~/.config/music-cli -newer /tmp/stamp 2>/dev/null | wc -l); .venv/bin/pytest -q -p no:cacheprovider; [ "$(find ~/.config/music-cli -newer /tmp/stamp | wc -l)" = "$before" ]`

---

## Phase P1 — Secure & Patch

**Goal:** close the security and correctness defects, then land the patch/minor upgrade wave.
**Milestone `M1`:** `pip-audit` reports **0 High or Critical advisories**; wave `W2` (hook revisions, ruff skew, orphaned dependencies, yt-dlp floor, classifiers) has landed; CI still green.

> `W1` is **empty by evidence, not by assumption.** No advisory database was consulted during the
> audit because `pip-audit` is not installed and is not in the `dev` extra. Task 1.1 establishes that
> baseline; if it surfaces advisories, they become additional `W1` tasks in this sprint.

### Sprint 1 — Security and correctness defects

#### Task 1.1: Establish an advisory baseline

**Description**: Add `pip-audit` to the `dev` extra and run it. The audit could not assess vulnerabilities at all, so `M1`'s exit condition is currently unmeasurable — this task makes it measurable. Serves milestone `M1`. If it reports High/Critical advisories, raise one task per advisory in this sprint before `M1` can be claimed.

**Closes**: — (milestone-enabling: `M1`)

**Acceptance Criteria**:
- [ ] `pip-audit` is listed in `[project.optional-dependencies] dev` and runs as a CI step
- [ ] A recorded `pip-audit` run produces a machine-readable report, and every High/Critical entry has a corresponding task in this sprint or a row in **Deferred**
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 0.4

**Effort**: S (1 day)

**Verify**: `.venv/bin/pip-audit -f json` exits 0 with no High/Critical entries

#### Task 1.2: Stop config-load failure from corrupting the class-level defaults

**Description**: `config.py:337` does `self.DEFAULT_CONFIG.copy()` — a **shallow** copy of a nested class attribute. A corrupt `config.toml` sends `_load_config` down this branch, and the next `set()` writes through the alias into `Config.DEFAULT_CONFIG`, permanently poisoning defaults for the whole process and persisting them to disk. Reproduced during the audit. `config.py:25` already imports `deepcopy` for `_recursive_mapping_merge`.

**Closes**: `F-BUG-001`

**Acceptance Criteria**:
- [ ] `config.py:337` uses `deepcopy`, and `config._config["player"] is Config.DEFAULT_CONFIG["player"]` evaluates `False` after a failed load
- [ ] A regression test reproduces the audit scenario — write invalid TOML, reload, `set("player.volume", 11)`, assert `Config.DEFAULT_CONFIG["player"]["volume"] == 80`
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 404/404 (baseline-green holds, plus the new test)

**Dependencies**: 0.2

**Effort**: S (1 day)

**Verify**: `.venv/bin/pytest tests/test_config.py -q -p no:cacheprovider`

#### Task 1.3: Confine local file playback to the music directory

**Description**: `sources/local.py:25` consults `music_dir` only for *relative* paths; absolute paths pass through with nothing but an extension check. The value arrives from an IPC request at `daemon.py:316`, so any local client can have the daemon open any audio file on the filesystem. Reproduced during the audit.

**Closes**: `F-BUG-003`

**Acceptance Criteria**:
- [ ] `LocalSource.get_track` returns `None` for a resolvable path outside `music_dir`, verified with a test using a temp file outside the boundary
- [ ] Symlink escape is covered — a symlink inside `music_dir` pointing outside it is also rejected (`resolve()` before the boundary check)
- [ ] If out-of-tree playback is kept, it is an explicit opt-in config key documented in the docstring, defaulting to off
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 0.2

**Effort**: S (1 day)

**Verify**: `.venv/bin/pytest tests/test_local_source.py -q -p no:cacheprovider`

#### Task 1.4: Authenticate the Windows TCP IPC transport

**Description**: `platform/ipc.py:245` binds `127.0.0.1:44556` with no access control, while the Unix transport is `chmod 0600` (`ipc.py:139`). On Windows, loopback TCP is reachable by every session and process on the host — any of them can drive playback, read history, issue `shutdown`, or (via `F-BUG-003`) read arbitrary audio files. The two transports are presented as interchangeable but do not carry the same guarantees.

**Closes**: `F-BUG-004`

**Acceptance Criteria**:
- [ ] Every daemon request carries a token generated at daemon start and stored in the config directory with owner-only permissions; requests without a valid token are rejected before dispatch
- [ ] A test asserts that a connection presenting no token, or a wrong token, receives an error and reaches no command handler
- [ ] The Unix transport passes the same test suite, so both transports are held to one standard
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 0.2, 0.5

**Effort**: M (3 days)

**Verify**: `.venv/bin/pytest tests/test_daemon.py -q -p no:cacheprovider` plus a green `windows-latest` CI cell

#### Task 1.5: Close the permission gaps and stop leaking exception text

**Description**: Three related exposures. `ipc.py:133` creates the Unix socket with umask-derived permissions and narrows it to `0600` only on the *next* statement — a TOCTOU window. `config.py:308` creates the config directory with default (typically `0755`) permissions though it holds the socket, PID file, history, and YouTube cache. `daemon.py:294` returns raw exception text — including absolute filesystem paths — to an unauthenticated client.

**Closes**: `F-BUG-005`, `F-BUG-013`, `F-BUG-012`

**Acceptance Criteria**:
- [ ] The socket is never world-accessible at any point — set umask around the bind, or bind inside a `0700` directory; verified by a test that stats the socket immediately after `start()`
- [ ] `Config._ensure_config_dir` creates all three directories with mode `0o700`, verified by a test asserting `stat.S_IMODE(...) == 0o700`
- [ ] `_process_command` returns a generic error string to the client and logs the detail server-side; a test asserts no filesystem path appears in a client-visible error
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 0.2

**Effort**: S (1 day)

**Verify**: `.venv/bin/pytest tests/test_daemon.py tests/test_config.py -q -p no:cacheprovider`

#### Task 1.6: Pin HuggingFace model revisions and un-skip B615

**Description**: `hf_cache.py:166` and five `from_pretrained` calls resolve to whatever the model repo's `main` points at now, and `pyproject.toml:137` globally skips `B615`, hiding this from Bandit. `trust_remote_code` is left at its `False` default, so this is supply-chain drift rather than remote code execution — but an unpinned model is still an unreviewed artifact entering the user's machine.

**Closes**: `F-BUG-014`

**Acceptance Criteria**:
- [ ] Every `snapshot_download` and `from_pretrained` call passes an explicit `revision=` pinned to a commit SHA, sourced from the model registry rather than hardcoded at each call site
- [ ] The blanket `B615` skip is removed from `pyproject.toml`, and `bandit -c pyproject.toml -r music_cli` still exits 0 — proving the pins, not the skip, are what makes it clean
- [ ] The two `# nosec B615` comments at `musicgen_strategy.py:42-43` and `minimax_strategy.py:54` are removed
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 0.2

**Effort**: M (2 days)

**Verify**: `.venv/bin/bandit -q -c pyproject.toml -r music_cli; echo "exit=$?"` returns 0 with B615 enabled

#### Task 1.7: Fix the installer's Windows path and stop it clobbering `mc`

**Description**: Two user-facing defects in the file the README asks people to pipe into `bash`. `install.sh:177` hardcodes `$INSTALL_DIR/bin/python` although `detect_os` accepts Windows at `:55` — Windows venvs use `Scripts/`, so line 181 fails under `set -e`. And `install.sh:206` does `rm -f "$link_target"` on `~/.local/bin/mc` with no ownership check — **`mc` is GNU Midnight Commander's binary**, so a user running the documented one-liner can silently lose an unrelated tool.

**Closes**: `F-BUG-009`, `F-BUG-010`

**Acceptance Criteria**:
- [ ] The venv bin directory is detected after creation (`bin/` vs `Scripts/`), or the Windows branch exits early with an actionable message instead of failing opaquely
- [ ] An existing `~/.local/bin/mc` that does not resolve into `$INSTALL_DIR` is left in place with a warning; overriding requires an explicit `FORCE_LINK=1`
- [ ] `shellcheck install.sh` exits 0
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 0.6

**Effort**: S (1 day)

**Verify**: `shellcheck install.sh && .venv/bin/pytest tests/test_installer.py -q -p no:cacheprovider`

#### Task 1.8: Give install.sh tests that could have caught 1.7

**Description**: `tests/test_installer.py:6` asserts on **three substrings of the script's source text**. It cannot catch `F-BUG-009` or `F-BUG-010` — both live in the very file it nominally covers. Replace text-matching with behaviour against a sandboxed `$HOME` and `$INSTALL_DIR`.

**Closes**: `F-TEST-003`

**Acceptance Criteria**:
- [ ] Tests run `install.sh` against a temporary `HOME` and `INSTALL_DIR` with a stubbed `pip`, asserting on resulting filesystem state rather than script text
- [ ] A test reproduces the `F-BUG-010` scenario — a pre-existing unrelated `~/.local/bin/mc` survives the install
- [ ] A test covers the Windows `Scripts/` layout branch from `F-BUG-009`
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 1.7

**Effort**: M (2 days)

**Verify**: `.venv/bin/pytest tests/test_installer.py -q -p no:cacheprovider`

#### Task 1.9: Harden the documented install flow

**Description**: `README.md:57` (repeated at `:97` and `:169`) documents `curl -sSL … | bash` **without `-f`**. Without `--fail`, an HTTP error page — proxy notice, 404 body, captive portal — is delivered with exit 0 and piped straight into `bash`. No checksum is published, so the "review it first" variant at `:136` cannot prove the reviewed script is the executed one. Separately, `SECURITY.md:40` tells contributors to avoid `shell=True` while `player/ffplay.py:162` uses `create_subprocess_shell` — that usage is safe and arguably necessary, but the contradiction should be recorded rather than left to be rediscovered.

**Closes**: `F-SEC-001`, `F-SEC-002`, `F-SEC-003`

**Acceptance Criteria**:
- [ ] Every documented `curl` invocation uses `-f`; the download-then-run form is the headline example
- [ ] A SHA-256 checksum for `install.sh` is published with each release and the README shows how to verify it
- [ ] `SECURITY.md` records the reviewed `create_subprocess_shell` exception with its justification, or a comment at `ffplay.py:162` references the policy
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 1.7

**Effort**: S (1 day)

**Verify**: `grep -c 'curl -sSL' README.md` returns 0; `grep -c 'curl -fsSL' README.md` returns ≥ 3

### Sprint 2 — Upgrade wave W2

#### Task 2.1: Remove the dead media-controller surface

**Description**: `platform/__init__.py:155` imports `.media_controller`, which does not exist and `git log --all` confirms was never committed. The import sits outside the `try:` at `:165`, so the `except ImportError` cannot catch it — `get_media_controller()` raises `ModuleNotFoundError` on every call. It is exported in `__all__` with zero call sites. This task unblocks 2.2 (the dependencies it justifies) and 7.6 (the docs that advertise it).

**Closes**: `F-BUG-002`

**Acceptance Criteria**:
- [ ] `get_media_controller`, its `__all__` entry, and the `MediaController` `TYPE_CHECKING` import at `:23` are removed — or the three missing modules are restored and the function returns a controller on every platform
- [ ] `python -c "import music_cli.platform"` succeeds and no exported name in `music_cli.platform.__all__` raises when called with valid arguments
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 0.2

**Effort**: S (1 day)

**Verify**: `python3 -c "import music_cli.platform as p; [getattr(p,n) for n in p.__all__]"` exits 0

#### Task 2.2: Prune the orphaned dependencies

**Description**: Four declared dependencies have **zero import sites**: `dbus-next` (`pyproject.toml:39`, also unmaintained — last release 2021-07-25), `winrt-Windows.Media.Playback` (`:40`, floor a major behind), `accelerate` and `soundfile` (`:50`, `:59`). The first two exist only to support the feature removed in 2.1. `diffusers>=0.15.0` (`:47`) has a floor so far below the current 0.39.0 that it constrains nothing.

**Closes**: `F-DEP-003`, `F-DEP-004`, `F-DEP-008`, `F-DEP-013`

**Acceptance Criteria**:
- [ ] `dbus-next` and `winrt-Windows.Media.Playback` are removed from `[project] dependencies`; a fresh `pip install -e .` on Linux and Windows installs neither
- [ ] `accelerate` and `soundfile` are either removed or their import sites are identified and documented — a dependency stays only with a reason
- [ ] The `diffusers` floor in the `ai` extra is raised to a version the code actually requires
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 2.1, 0.4

**Effort**: S (1 day)

**Verify**: for each removed package, `grep -rn "<pkg>" music_cli --include='*.py'` returns no import

#### Task 2.3: Refresh the pre-commit hooks and end the three-way ruff skew

**Description**: Hook revisions are 1–2 majors stale: `pre-commit-hooks` v4.5.0 → v6.0.0 (`:8`), `ruff-pre-commit` v0.11.2 → v0.16.3 (`:21`), `mirrors-mypy` v1.9.0 → v2.3.1. Worse, **three different ruff versions are in play** — the hook pins 0.11.2, this venv has 0.15.22, and CI installs the latest unpinned. Lint results depend on where you run them. The config declares `autoupdate_schedule: monthly`, which evidently is not running.

**Closes**: `F-DEP-010`, `F-DEP-011`

**Acceptance Criteria**:
- [ ] `pre-commit autoupdate` has been run and the bumped revisions committed; `pre-commit run --all-files` passes
- [ ] The ruff version in `.pre-commit-config.yaml`, the `dev` extra pin, and the CI pin are identical — verified by a single `grep` showing one version string
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 0.6

**Effort**: S (1 day)

**Verify**: `pre-commit run --all-files` exits 0 and `.venv/bin/ruff --version` matches the hook `rev`

#### Task 2.4: Raise the yt-dlp floor

**Description**: `pyproject.toml:63` allows `yt-dlp>=2023.1.0` — a floor 3.5 years behind the current 2026.7.4. yt-dlp requires near-continuous updates to keep extracting from YouTube, so this range permits a resolution that simply cannot play anything.

**Closes**: `F-DEP-007`

**Acceptance Criteria**:
- [ ] The floor is raised to a release that still extracts successfully, with the chosen version recorded in a comment beside it
- [ ] `pip install -e ".[youtube]"` resolves and `music_cli.sources.youtube.is_youtube_available()` returns `True`
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 0.4

**Effort**: S (1 day)

**Verify**: `grep 'yt-dlp' pyproject.toml` shows the raised floor and `pip install -e ".[youtube]"` succeeds

#### Task 2.5: Correct the Python classifiers

**Description**: `pyproject.toml:26-29` advertises 3.10, 3.11, and 3.12 on PyPI while CI tests 3.12–3.14. The classifiers are how users judge compatibility before installing, and they currently describe neither what is tested nor what is supported.

**Closes**: `F-DEP-012`

**Acceptance Criteria**:
- [ ] The classifier list matches the CI matrix and `requires-python` exactly, all three agreeing
- [ ] `python -m build` followed by `twine check dist/*` passes with the corrected metadata
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 0.5

**Effort**: S (1 day)

**Verify**: a script comparing the classifier versions, the matrix, and `requires-python` reports no discrepancy

---

## Phase P2 — Modernize

**Goal:** settle the runtime floor (wave `W3`), then take each major upgrade on its own (wave `W4`).
**Milestone `M2`:** every major identified in the report is either **current or deferred with written rationale**; the supported Python floor is a version with remaining upstream support; CI green throughout.

> Sprint 3 holds only two tasks. That is deliberate: `W3` must land and be verified **before** `W4`,
> because `F-BUG-015` (`process_group`, 3.11+) and the transformers bump both depend on the floor
> decision. Collapsing them into one sprint would make a failed suite unattributable.

### Sprint 3 — Runtime floor (W3)

#### Task 3.1: Decide and enact the supported Python floor

**Description**: `requires-python = ">=3.10"` (`pyproject.toml:10`), and **Python 3.10 reaches end-of-life on 2026-10-31 — 73 days after this audit**. The project must either commit to testing 3.10 until that date and then drop it, or raise the floor now. Raising to `>=3.11` also unlocks `process_group=0` for `F-BUG-015`; raising to `>=3.12` aligns with the current CI matrix and removes the numpy-stub conflict behind `F-CI-002` at its root. This is a decision task — record the reasoning, not just the edit.

**Closes**: `F-DEP-001`

**Acceptance Criteria**:
- [ ] `requires-python`, the classifier list, `[tool.ruff] target-version`, `[tool.black] target-version` (if black survives 6.6), `[tool.mypy] python_version`, and the CI matrix all name the same floor
- [ ] The decision and its rationale — including the 2026-10-31 EOL date — are recorded in `CHANGELOG.md` under Unreleased
- [ ] `pip install -e ".[dev]"` succeeds on the new floor version and on the newest matrix version
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 0.5, 1.1

**Effort**: M (3 days)

**Verify**: a script asserting the floor string is identical across all six declaration sites, plus a green CI run

#### Task 3.2: Replace `preexec_fn` with `process_group`

**Description**: `player/ffplay.py:166` uses `preexec_fn=os.setsid`, documented as unsafe in the presence of threads — and `cli.py` does start threads (`ComposingAnimation`). `process_group=0` is the supported replacement from Python 3.11, so this is only actionable once 3.1 sets the floor.

**Closes**: `F-BUG-015`

**Acceptance Criteria**:
- [ ] `preexec_fn` is gone from `ffplay.py`; the YouTube pipe still runs in its own process group so `os.killpg` at `:206` and `:250` continues to work
- [ ] A test starts the pipe path and asserts the child is in a distinct process group, and that `stop()` reaps it
- [ ] If the floor chosen in 3.1 is below 3.11, this task is deferred with that reason recorded — not silently skipped
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 3.1

**Effort**: S (1 day)

**Verify**: `grep -c preexec_fn music_cli/player/ffplay.py` returns 0; `.venv/bin/pytest tests/test_ffplay.py -q -p no:cacheprovider`

### Sprint 4 — Majors, one per task (W4)

> `F-DEP-009` covers six GitHub Actions spanning 2–4 majors each. They are split into one task per
> action so a failing run is attributable, per the never-batch-majors rule. The finding is fully
> closed when 4.5 lands. **Migration source for all five:** each action's own release notes and
> upgrade guide on GitHub — retrieved per task, not from memory.

#### Task 4.1: actions/checkout v4 → v7

**Description**: Used at `ci.yml:27`, `:66`, `:107`, `:135` and `release.yml:19`, `:45` — three majors behind. **Migration source:** the `actions/checkout` release notes for v5, v6, and v7; read all three before editing, as the Node runtime requirement changed across them.

**Closes**: `F-DEP-009` (partial — `actions/checkout`)

**Acceptance Criteria**:
- [ ] Every `actions/checkout` reference in both workflows is on v7 and no other action is changed in this task
- [ ] A full CI run passes on all 9 matrix cells plus the lint, build, and pre-commit jobs
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 0.2

**Effort**: S (1 day)

**Verify**: `grep -c 'actions/checkout@v7' .github/workflows/*.yml` matches the previous v4 count, and CI is green

#### Task 4.2: actions/setup-python v5 → v7

**Description**: Used at `ci.yml:30`, `:69`, `:110`, `:138` and `release.yml:22` — two majors behind. The matrix cell at `:69` passes `allow-prereleases: true`; confirm that option survives the bump. **Migration source:** `actions/setup-python` release notes for v6 and v7.

**Closes**: `F-DEP-009` (partial — `actions/setup-python`)

**Acceptance Criteria**:
- [ ] Every `actions/setup-python` reference is on v7 and `allow-prereleases` still resolves the newest matrix version
- [ ] A full CI run passes on all 9 matrix cells
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 4.1

**Effort**: S (1 day)

**Verify**: the CI log for the newest Python cell shows the expected interpreter version

#### Task 4.3: actions/upload-artifact v4 → v7 and download-artifact v4 → v8

**Description**: Used at `ci.yml:126`, `release.yml:35` (upload) and `release.yml:48` (download). **These two move together** — upload and download artifacts are only compatible within the same generation, so bumping one alone breaks `release.yml`'s build → github-release handoff. That is a technical coupling, not a batching shortcut. **Migration source:** the `actions/upload-artifact` and `actions/download-artifact` migration notes.

**Closes**: `F-DEP-009` (partial — artifact actions)

**Acceptance Criteria**:
- [ ] Both actions are bumped in the same change and the `release.yml` build → download handoff succeeds end to end
- [ ] A tagged pre-release dry run produces a downloadable `dist/` artifact
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 4.2

**Effort**: S (1 day)

**Verify**: a test tag triggers `release.yml` and the `github-release` job downloads the artifact successfully

#### Task 4.4: codecov/codecov-action v4 → v7

**Description**: Used at `ci.yml:96`, three majors behind. v5+ changed token handling; since `fail_ci_if_error: false` is set, a silent upload failure would go unnoticed — verify the upload actually lands rather than trusting a green job. **Migration source:** `codecov-action` v5/v6/v7 release notes.

**Closes**: `F-DEP-009` (partial — `codecov-action`)

**Acceptance Criteria**:
- [ ] The action is on v7 and a coverage report is visible in Codecov for the run, not merely a green step
- [ ] `fail_ci_if_error` is set deliberately (either value) with a comment recording the choice
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 4.3

**Effort**: S (1 day)

**Verify**: the Codecov dashboard shows a report for the commit SHA of the run

#### Task 4.5: softprops/action-gh-release v1 → v3

**Description**: Used at `release.yml:54`, two majors behind and pinned to the floating `v1` tag. This task closes `F-DEP-009` — after it, no action in either workflow is behind. Also switch every `uses:` to a commit SHA, which is what makes the pins immutable rather than merely current. **Migration source:** `softprops/action-gh-release` v2 and v3 release notes.

**Closes**: `F-DEP-009`

**Acceptance Criteria**:
- [ ] `action-gh-release` is on v3 and a test tag produces a GitHub release with `dist/*` attached and generated notes
- [ ] Every `uses:` in both workflows references a commit SHA with the version in a trailing comment
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 4.4

**Effort**: S (1 day)

**Verify**: `grep -E 'uses: .*@[0-9a-f]{40}' .github/workflows/*.yml | wc -l` equals the total `uses:` count

#### Task 4.6: transformers 4.x → 5.x for the `ai` extra

**Description**: `pyproject.toml:46` caps at `transformers>=4.31,<4.51` while 5.15.1 is current — the extra is pinned below a whole major line. **Migration source: `MIGRATION_GUIDE_V5.md` in the transformers repository, retrieved via Context7 during this audit.** The breaking changes that touch this codebase are the `generate` changes — old output-type aliases removed, the default KV cache now model-defined rather than always `DynamicCache`, and generation parameters no longer readable from `model.config` (they must come from `model.generation_config`). `musicgen_strategy.py` and `bark_strategy.py` both call `.generate()`. The removal of `AutoModelWithLMHead` and `AutoModelForVision2Seq` does not apply — this code uses `AutoProcessor`, `MusicgenForConditionalGeneration`, and `BarkModel`.

**Closes**: `F-DEP-005`

**Acceptance Criteria**:
- [ ] The `ai` extra requires `transformers>=5,<6`, and `pip install -e ".[ai]"` resolves on the floor set in 3.1
- [ ] Every `.generate()` call site reads generation parameters from `model.generation_config`, not `model.config`
- [ ] An end-to-end generation run with `musicgen-small` produces a playable audio file, exercised manually and recorded in the PR
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 3.1, 1.6

**Effort**: M (3 days)

**Verify**: `pip install -e ".[ai]" && .venv/bin/pytest tests/test_ai_tracks.py tests/test_lazy_ai_imports.py -q -p no:cacheprovider`

#### Task 4.7: transformers 4.x → 5.x for the `minimax` extra

**Description**: `pyproject.toml:56` caps at `transformers>=4.51,<5`. Separate from 4.6 because the `minimax` extra also pins `diffusers>=0.39.0,<0.40.0` (`:55`) for `ModularPipeline`, so the two constraint sets must be resolved together and independently verified. Same migration source as 4.6; additionally confirm `ModularPipeline.from_pretrained` — guarded at `minimax_strategy.py:40` — still exists under the resolved diffusers version.

**Closes**: `F-DEP-006`

**Acceptance Criteria**:
- [ ] The `minimax` extra requires `transformers>=5,<6` and `pip install -e ".[minimax]"` resolves without conflicting with the pinned diffusers range
- [ ] `minimax_strategy.py:40`'s capability guard still passes, and `tests/test_minimax_strategy.py` passes in full
- [ ] If diffusers must also move, that is raised as its own task rather than folded in here
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 4.6

**Effort**: M (3 days)

**Verify**: `pip install -e ".[minimax]" && .venv/bin/pytest tests/test_minimax_strategy.py -q -p no:cacheprovider`

---

## Phase P3 — Clean & Harden

**Goal:** make the daemon correct and covered, *then* restructure it.
**Milestone `M3`:** coverage ≥ **75%** (baseline 54.69% + 20pp, floored at 60%) with the floor enforced in CI and reproducible under an isolated `HOME`; `mypy music_cli` runs clean under the project config with zero untracked errors; no `ruff --select C901` function exceeds complexity 15; the duplication threshold holds — **no logic block repeated ≥ 3 times survives in the `DEAD` findings** (the audit's clone detection found none, so this milestone requires that it *stays* true, checked with the same method).

> **Sequencing that must hold:** every refactor here depends on the tests that cover the code it
> touches. `6.1`–`6.5` all descend from `5.4`, and `5.4` descends from `5.1`, because
> characterization tests written against a racy command surface would encode the race.

### Sprint 5 — Correctness and coverage before refactoring

#### Task 5.1: Serialize daemon command handling

**Description**: `asyncio.start_server` runs one task per connection, so commands interleave at every `await`. `_cmd_play` (`daemon.py:302`) writes `_auto_play` (`:307`) and `_current_mood` (`:312`), then awaits `player.play(track)` (`:423`), which itself awaits `stop()` and reassigns `_process` (`ffplay.py:47`, `:97`). Two concurrent plays orphan an ffplay process. This is part 1 of 2 for `F-BUG-007`; part 2 (decomposition) is 6.1, and it must come after the tests in 5.4.

**Closes**: `F-BUG-007` (part 1 of 2 — the lock; decomposition is 6.1)

**Acceptance Criteria**:
- [ ] All state-mutating command handlers execute under a single `asyncio.Lock` held for the duration of the command
- [ ] A test issues two concurrent `play` commands and asserts exactly one ffplay process survives and `_process` matches it
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 1.2

**Effort**: M (2 days)

**Verify**: `.venv/bin/pytest tests/test_daemon.py -q -p no:cacheprovider`

#### Task 5.2: Make daemon liveness identity-checked

**Description**: `daemon.py:886` `_pid_alive` only asks whether *a* process holds the PID. After an unclean exit the stale PID file survives, and once the OS recycles that PID, `is_daemon_running()` returns `True` forever — `ensure_daemon` never restarts, every command fails on connect, and recovery requires manually deleting a file nothing tells the user about.

**Closes**: `F-BUG-008`

**Acceptance Criteria**:
- [ ] Liveness requires identity, not just PID existence — a recorded start-time or nonce that `ping` also returns, or a successful `ping` before the PID file is trusted
- [ ] A test writes a PID file pointing at a live unrelated process and asserts `is_daemon_running()` returns `False` and the stale file is cleaned up
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 5.1

**Effort**: M (2 days)

**Verify**: `.venv/bin/pytest tests/test_daemon.py -q -p no:cacheprovider`

#### Task 5.3: Hold references to background tasks

**Description**: `daemon.py:871` (`shutdown`), `:457` (auto-play chain), and `:147` (signal handler) all call `asyncio.create_task` without keeping a reference — `ruff RUF006`. The event loop holds only a weak reference, so the task can be collected mid-execution. Line 871 is the worst: the daemon answers `shutting_down` and then keeps running.

**Closes**: `F-BUG-006`

**Acceptance Criteria**:
- [ ] All three call sites store the task in a set with an `add_done_callback` discard; `ruff --select RUF006 music_cli` reports 0
- [ ] A test asserts the daemon actually terminates after a `shutdown` command, not merely that it responds
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 5.1

**Effort**: S (1 day)

**Verify**: `.venv/bin/ruff check --select RUF006 music_cli` exits 0

#### Task 5.4: Characterization tests for the daemon command surface

**Description**: `daemon.py` is 38% covered and is both the largest attack surface and the target of every refactor in Sprint 6. Write tests that pin **current observable behaviour** of all 19 command handlers before any restructuring, so 6.1–6.3 have a safety net. Part 1 of 2 for `F-TEST-006`; part 2 (raising the number to target) is 5.6.

**Closes**: `F-TEST-006` (part 1 of 2 — characterization; coverage target is 5.6)

**Acceptance Criteria**:
- [ ] Every one of the 19 handlers in the dispatch table at `daemon.py:266` has at least one test covering its success path and one covering its primary error path
- [ ] `daemon.py` coverage is ≥ 70%, up from 38%
- [ ] Tests assert on observable responses, not internal attributes, so they survive the Sprint 6 restructuring
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 5.1

**Effort**: M (3 days)

**Verify**: `.venv/bin/pytest -q -p no:cacheprovider` and read the `daemon.py` row of the coverage table

#### Task 5.5: Surface daemon startup failures

**Description**: `cli.py:180` and `:189` send the daemon's stdout **and stderr** to `DEVNULL`, so any startup exception is discarded. `cli.py:156` then reports the bare string `Failed to start daemon` after a fixed 2-second poll — no traceback, no log path, and because the daemon logs only after it starts, nothing to read afterwards either.

**Closes**: `F-BUG-011`

**Acceptance Criteria**:
- [ ] The daemon child's stderr is redirected to a log file under the config directory, and the failure message prints that path
- [ ] A test forces a startup failure and asserts the CLI output contains the log path and the log file contains the traceback
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 5.4

**Effort**: S (1 day)

**Verify**: `.venv/bin/pytest tests/test_cli.py -q -p no:cacheprovider`

#### Task 5.6: Make coverage honest, then raise it to target

**Description**: Two problems compound. `pyproject.toml:142` omits `music_cli/sources/ai_generator.py` from coverage entirely — a module holding two of the eight highest-complexity functions is invisible to the metric, so the reported 55% overstates reality. And `progress_callback.py` sits at **0%** across 66 statements. Remove the omit first so the number is true, then raise it. Part 2 of 2 for `F-TEST-006`.

**Closes**: `F-TEST-004`, `F-TEST-005`, `F-TEST-006`

**Acceptance Criteria**:
- [ ] The `omit` entry is removed from `pyproject.toml` and the resulting *true* baseline coverage is recorded in the PR before any new tests are added
- [ ] `progress_callback.py` coverage is ≥ 70%, up from 0%
- [ ] Total coverage is ≥ **75%** and `--cov-fail-under` is raised from 55 to 75
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 0.7, 5.4

**Effort**: M (3 days)

**Verify**: `.venv/bin/pytest -q -p no:cacheprovider --cov-fail-under=75` exits 0

### Sprint 6 — Decomposition

#### Task 6.1: Decompose `_cmd_play` into per-mode handlers

**Description**: `daemon.py:302` is the worst readability offender in the codebase — **complexity 31, 36 branches, 80 statements, 151 lines** — dispatching six playback modes inline. Part 2 of 2 for `F-BUG-007`; the lock landed in 5.1 and the characterization tests in 5.4, so this is now a behaviour-preserving change with a net beneath it.

**Closes**: `F-BUG-007` (part 2 of 2 — decomposition)

**Acceptance Criteria**:
- [ ] Each playback mode (`local`, `radio`, `ai`, `context`, `history`, `youtube`) resolves its track in a dedicated function; `_cmd_play` only dispatches and handles the common tail
- [ ] `ruff --isolated --select C901 --config 'lint.mccabe.max-complexity=15' music_cli/daemon.py` no longer flags `_cmd_play`
- [ ] The 5.4 characterization tests pass **unmodified** — proving behaviour was preserved
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 5.4

**Effort**: M (3 days)

**Verify**: `.venv/bin/ruff check --isolated --select C901 --config 'lint.mccabe.max-complexity=15' music_cli/daemon.py`

#### Task 6.2: Extract the daemon command registry

**Description**: `daemon.py:266` rebuilds a 19-entry dict of bound methods on **every IPC request** — the hottest path in the daemon. Replacing it with a registry built once also begins splitting the 968-line `MusicDaemon` (`F-CLEAN-008`), which currently owns request framing, playback, history, PID management, and all 19 handlers.

**Closes**: `F-PERF-006`, `F-CLEAN-008` (part 1 of 2 — registry extraction; completion is 6.3)

**Acceptance Criteria**:
- [ ] The dispatch table is constructed once (class-level or in `__init__`), and a test asserts the same mapping object is reused across two requests
- [ ] Handler registration is decoupled from `_process_command` so handlers can move to their own module in 6.3
- [ ] The 5.4 characterization tests pass unmodified
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 6.1

**Effort**: M (3 days)

**Verify**: `.venv/bin/pytest tests/test_daemon.py -q -p no:cacheprovider`

#### Task 6.3: Simplify the AI handlers and finish the daemon split

**Description**: `_cmd_ai_play` (`daemon.py:540` — 104 lines, complexity 12, 9 returns) and `_cmd_ai_replay` (`:645` — 91 lines, 10 returns) repeat generation setup and error mapping. `sources/ai_generator.py:80` and `:212` are both at complexity 11. Completing the extraction started in 6.2 brings `MusicDaemon` below the god-class threshold. Part 2 of 2 for `F-CLEAN-008`.

**Closes**: `F-CLEAN-004`, `F-CLEAN-005`, `F-CLEAN-008` (part 2 of 2), `F-CLEAN-010`

**Acceptance Criteria**:
- [ ] Generation setup and error mapping are shared between the two AI handlers; neither exceeds 6 return statements
- [ ] `music_cli/daemon.py` is under 500 lines, with handlers living in their own module
- [ ] `ruff --isolated --select C901,PLR0911 --config 'lint.mccabe.max-complexity=15'` reports 0 for `daemon.py` and `sources/ai_generator.py`
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 6.2

**Effort**: M (3 days)

**Verify**: `wc -l music_cli/daemon.py` and the ruff command above

#### Task 6.4: Split cli.py — extract the command groups

**Description**: `cli.py` is **1658 lines / 52 KB** holding all 14 command groups plus the animation thread, the alias group, and daemon bootstrap. `play()` at `:334` is 97 lines with complexity 13, 13 branches, and **7 parameters**. Part 1 of 2 for `F-CLEAN-007`.

**Closes**: `F-CLEAN-003`, `F-CLEAN-007` (part 1 of 2 — command-group extraction; completion is 6.5)

**Acceptance Criteria**:
- [ ] `music_cli/cli/` exists as a package with one module per command group (`ai`, `radio`, `history`, `yt`, `daemon`, …), and both console-script entry points still resolve
- [ ] `play()` is under 50 lines, and its options are grouped into a dataclass so the parameter count drops to ≤ 4
- [ ] `.venv/bin/music-cli --help` and `.venv/bin/mc --help` list all 14 commands exactly as before
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 5.4

**Effort**: M (3 days)

**Verify**: `diff <(.venv/bin/music-cli --help) <(git show HEAD~1:/dev/null 2>/dev/null; .venv/bin/music-cli --help)` — command list unchanged; `.venv/bin/pytest tests/test_cli.py tests/test_e2e.py -q -p no:cacheprovider`

#### Task 6.5: Finish the cli split and thin the client

**Description**: Complete `F-CLEAN-007` by moving the remaining helpers (`ComposingAnimation`, `AliasedGroup`, `ensure_daemon`, `start_daemon_background`) out of the root module. Also split `client.py:35` `send_command` (complexity 11, 13 branches), which currently mixes connect, frame, decode, and error mapping in one method. Part 2 of 2 for `F-CLEAN-007`.

**Closes**: `F-CLEAN-007` (part 2 of 2), `F-CLEAN-006`

**Acceptance Criteria**:
- [ ] No module under `music_cli/cli/` exceeds 400 lines
- [ ] `send_command` separates transport from protocol; `ruff --select C901 --config 'lint.mccabe.max-complexity=10' music_cli/client.py` exits 0
- [ ] All aliases still resolve — `mc radios`, `mc update-radios`, and `mc volume` each still run
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 6.4

**Effort**: M (2 days)

**Verify**: `for c in radios update-radios volume; do .venv/bin/music-cli $c --help >/dev/null || exit 1; done`

#### Task 6.6: Standardize on one formatter and shrink parameter lists

**Description**: **Two formatters are configured** — `black>=23.0` (`pyproject.toml:69`) with `[tool.black]` (`:92`), alongside `ruff-format` in pre-commit (`:25`) and CI (`ci.yml:41`). They agree on `music_cli/` today but **disagree on `tests/`**: black wants 2 files reformatted that ruff considers correct. Contributors are told to run black (`CONTRIBUTING.md:155`) while CI enforces ruff. Also address `PLR0913` at 5 remaining sites and the complexity-21 `feed` state machine at `daemon.py:50`.

**Closes**: `F-CLEAN-009`, `F-CLEAN-011`, `F-CLEAN-002`

**Acceptance Criteria**:
- [ ] `black` and `[tool.black]` are removed from `pyproject.toml`; `ruff format --check .` exits 0 across all 50 files including `tests/`
- [ ] `ruff --select PLR0913 music_cli` reports 0 — the 5 remaining 6-parameter functions take dataclasses
- [ ] `feed` at `daemon.py:50` is either simplified below complexity 15 or retains its complexity with a comment justifying why the state machine is clearer as one unit
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 2.3

**Effort**: S (1 day)

**Verify**: `.venv/bin/ruff format --check . && .venv/bin/ruff check --isolated --select PLR0913 music_cli`

#### Task 6.7: Remove the dead code

**Description**: `README.backup.md` is a 426-line stale duplicate tracked at the repo root, last touched 2026-03-18 while `README.md` moved on to 550 lines on 2026-08-17 — git history is the backup. Separately, 21 `ARG002` unused arguments (9 in `daemon.py` from `:479`, 4 in `platform/ipc.py`, 5 in AI strategies, 2 in `progress_callback.py`) are mostly interface conformance but are unmarked as such.

**Closes**: `F-DEAD-001`, `F-DEAD-002`

**Acceptance Criteria**:
- [ ] `README.backup.md` is deleted and `git ls-files | grep -c backup` returns 0
- [ ] Every `ARG002` site is renamed to `_`-prefixed or carries a `# noqa: ARG002` with a stated reason; `ruff --select ARG002 music_cli` exits 0
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 2.1

**Effort**: S (1 day)

**Verify**: `.venv/bin/ruff check --isolated --select ARG002 music_cli` exits 0

---

## Phase P4 — Polish

**Goal:** meet the measured performance budget and realign the documentation with the code.
**Milestone `M4`:** the perf budget holds — `scan_directory` completes in **≤ 100 ms** on a 10,000-file library (measured 296.6 ms at audit) and `History.get_by_index(1)` completes in **≤ 5 ms** on a 50,000-entry history (measured 120.0 ms at audit); every `DOCS` finding is closed. **The UX clause is deliberately dropped** — `UX` was Not Assessed (no application UI), so there is no UX budget to invent.

### Sprint 7 — Performance and documentation

#### Task 7.1: Cap and index the playback history

**Description**: `history.py:99` — history is append-only with **no cap and no rotation**, and every read path funnels through `get_all()`, which parses the whole file. `get_by_index(1)` — "replay the last track" — pays that cost to return one entry. Measured: **2.3 ms at 1k entries → 42.6 ms at 18k → 120.0 ms at 50k**, growing without limit. The sibling `youtube_history.py:114` already solved this with a 1000-entry cap that `history.py` never adopted.

**Closes**: `F-PERF-002`

**Acceptance Criteria**:
- [ ] History is capped (rotation or a `max_entries` bound matching `youtube_history.py`), and the cap is configurable
- [ ] `get_by_index(n)` for small `n` reads from the end of the file rather than parsing it whole
- [ ] A benchmark test asserts `get_by_index(1)` completes in **≤ 5 ms** on a 50,000-entry file
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 5.6

**Effort**: M (2 days)

**Verify**: the benchmark test in `tests/test_history.py` passes at the stated threshold

#### Task 7.2: Single-pass, cached library scan

**Description**: `sources/local.py:57` issues a **full recursive `rglob` per extension** — six complete traversals per scan — and auto-play rescans on every track end (`daemon.py:461`). Measured on 10,000 files / 800 directories: **296.6 ms → 90.2 ms, a 3.3× reduction**. Also `list_tracks` (`:76`) applies its limit *after* the full scan and re-stats each file, and `:60` sorts the whole listing even when the only caller wants one random element.

**Closes**: `F-PERF-001`, `F-PERF-005`, `F-PERF-007`

**Acceptance Criteria**:
- [ ] `scan_directory` performs exactly one traversal, filtering on `suffix.lower()`, and caches the result against the directory's mtime
- [ ] A benchmark test asserts a 10,000-file scan completes in **≤ 100 ms**, and a second call against an unchanged directory is served from cache
- [ ] `list_tracks` applies its limit during iteration without a redundant `exists()` per file; sorting moves out of the shared scan
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 5.6

**Effort**: S (1 day)

**Verify**: the benchmark test in `tests/test_local_source.py` passes at the stated threshold

#### Task 7.3: Make ai_tracks append-only

**Description**: `ai_tracks.py:131` does load-all → append → rewrite-all: **O(N) per add, O(N²) across N adds**. The same pair repeats at `:179` and `:200`. `history.py` already uses JSON Lines with a plain append — adopt the same shape.

**Closes**: `F-PERF-003`

**Acceptance Criteria**:
- [ ] Adding a track appends without reading or rewriting the whole file; a test asserts the file is opened in append mode for `add_track`
- [ ] Existing JSON-array track files migrate on first read without data loss, covered by a test
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 5.6

**Effort**: S (1 day)

**Verify**: `.venv/bin/pytest tests/test_ai_tracks.py -q -p no:cacheprovider`

#### Task 7.4: Cache the parsed radio stations

**Description**: `config.py:377` re-opens and re-parses `radios.txt` on every `get_radios()` call, and `sources/radio.py:34` calls it from four lookup methods — several times per `_cmd_play`. The neighbouring `_check_youtube` (`radio.py:23`) is already memoised; the file read next to it is not.

**Closes**: `F-PERF-004`

**Acceptance Criteria**:
- [ ] `Config` caches the parsed station list and invalidates it on `radios.txt` mtime change
- [ ] A test asserts a single radio-mode play reads `radios.txt` at most once, and that editing the file is picked up on the next call
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 5.6

**Effort**: S (1 day)

**Verify**: `.venv/bin/pytest tests/test_config.py -q -p no:cacheprovider`

#### Task 7.5: Fix the remaining correctness papercuts

**Description**: Seven Low-severity defects batched because each is a few lines and none interacts with the others: weak substring URL matching (`radio.py:12`, `daemon.py:337`) that accepts `evil-youtube.com.attacker.net`; the 0.1-second liveness race (`ffplay.py:108`); 15 `SC2059` printf format-string issues with user-controlled `INSTALL_DIR`/`EXTRAS` (`install.sh:243`, `:293`); a version gate rejecting a hypothetical Python 4.0 (`install.sh:103`); an unused `BRANCH` variable (`install.sh:26`); unconditional backslash-stripping that mangles legitimate URLs (`youtube.py:42`); and an unguarded PID-file write that kills the daemon after the socket is already listening (`daemon.py:153`).

**Closes**: `F-BUG-016`, `F-BUG-017`, `F-BUG-018`, `F-BUG-019`, `F-BUG-020`, `F-BUG-021`, `F-BUG-022`

**Acceptance Criteria**:
- [ ] YouTube detection parses the URL and compares the host, reusing `sources/youtube.py:45`; a test asserts `https://evil-youtube.com.attacker.net/x` is rejected
- [ ] `shellcheck install.sh` exits 0 with no `SC2059` or `SC2034`, and the version gate accepts a `4.0` stub
- [ ] The PID-file write is guarded so failure occurs before the socket binds, covered by a test
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 5.6

**Effort**: M (2 days)

**Verify**: `shellcheck install.sh && .venv/bin/pytest -q -p no:cacheprovider`

#### Task 7.6: Realign the documentation with the code

**Description**: Five documentation claims that no longer match reality. `docs/development.md:127` tells contributors to install `dist/music_cli-0.1.0-py3-none-any.whl` — wrong package name (the wheel is `coder_music_cli`) and a version 10 releases stale. `CONTRIBUTING.md:155` and `docs/development.md:86` instruct `black music_cli/` after 6.6 removed black. `pyproject.toml:18` advertises `media-keys`, `mpris`, and `now-playing` — the keywords PyPI search indexes — for a feature 2.1 deleted, and `README.md:539-540` credits pyobjc and dbus-next for that same absent support. `platform/__init__.py:11` still lists "Media controller abstraction" as a key component.

**Closes**: `F-DOCS-001`, `F-DOCS-002`, `F-DOCS-003`, `F-DOCS-004`, `F-DOCS-006`

**Acceptance Criteria**:
- [ ] Every documented command and install step executes successfully when copy-pasted — verified by running each one
- [ ] The three stale keywords and both README credit rows are removed, and `platform/__init__.py`'s docstring matches the modules that exist
- [ ] `grep -rn 'black ' CONTRIBUTING.md docs/development.md` returns no formatting instruction
- [ ] `.venv/bin/pytest -q -p no:cacheprovider` passes at ≥ 403/403 (baseline-green holds)

**Dependencies**: 2.1, 6.6

**Effort**: S (1 day)

**Verify**: a script extracting every fenced `bash` command from `README.md`, `CONTRIBUTING.md`, and `docs/development.md` and running the non-destructive ones exits 0

---

## Dependency table

| Task | Depends on | Blocks | Wave |
|---|---|---|---|
| Pre.1 | — | Pre.2, Pre.3 | — |
| Pre.2 | Pre.1 | 0.1, 0.3, 0.4 | — |
| Pre.3 | Pre.1 | 0.1, 0.3, 0.4 | — |
| 0.1 | Pre.2, Pre.3 | 0.2, 0.5 | W0 |
| 0.2 | 0.1 | 0.7, 0.8, 0.9, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 4.1 | W0 |
| 0.3 | Pre.2, Pre.3 | — | W0 |
| 0.4 | Pre.2, Pre.3 | 0.6, 1.1, 2.2, 2.4 | W0 |
| 0.5 | 0.1 | 1.4, 2.5, 3.1 | W0 |
| 0.6 | 0.4 | 1.7, 2.3 | W0 |
| 0.7 | 0.2, 0.9 | 5.6 | W0 |
| 0.8 | 0.2 | — | W0 |
| 0.9 | 0.2 | 0.7 | W0 |
| 1.1 | 0.4 | 3.1 | W1 |
| 1.2 | 0.2 | 5.1 | — |
| 1.3 | 0.2 | — | — |
| 1.4 | 0.2, 0.5 | — | — |
| 1.5 | 0.2 | — | — |
| 1.6 | 0.2 | 4.6 | — |
| 1.7 | 0.6 | 1.8, 1.9 | — |
| 1.8 | 1.7 | — | — |
| 1.9 | 1.7 | — | — |
| 2.1 | 0.2 | 2.2, 6.7, 7.6 | W2 |
| 2.2 | 2.1, 0.4 | — | W2 |
| 2.3 | 0.6 | 6.6 | W2 |
| 2.4 | 0.4 | — | W2 |
| 2.5 | 0.5 | — | W2 |
| 3.1 | 0.5, 1.1 | 3.2, 4.6 | W3 |
| 3.2 | 3.1 | — | W3 |
| 4.1 | 0.2 | 4.2 | W4 |
| 4.2 | 4.1 | 4.3 | W4 |
| 4.3 | 4.2 | 4.4 | W4 |
| 4.4 | 4.3 | 4.5 | W4 |
| 4.5 | 4.4 | — | W4 |
| 4.6 | 3.1, 1.6 | 4.7 | W4 |
| 4.7 | 4.6 | — | W4 |
| 5.1 | 1.2 | 5.2, 5.3, 5.4 | — |
| 5.2 | 5.1 | — | — |
| 5.3 | 5.1 | — | — |
| 5.4 | 5.1 | 5.5, 5.6, 6.1, 6.4 | — |
| 5.5 | 5.4 | — | — |
| 5.6 | 0.7, 5.4 | 7.1, 7.2, 7.3, 7.4, 7.5 | — |
| 6.1 | 5.4 | 6.2 | — |
| 6.2 | 6.1 | 6.3 | — |
| 6.3 | 6.2 | — | — |
| 6.4 | 5.4 | 6.5 | — |
| 6.5 | 6.4 | — | — |
| 6.6 | 2.3 | 7.6 | — |
| 6.7 | 2.1 | — | — |
| 7.1 | 5.6 | — | — |
| 7.2 | 5.6 | — | — |
| 7.3 | 5.6 | — | — |
| 7.4 | 5.6 | — | — |
| 7.5 | 5.6 | — | — |
| 7.6 | 2.1, 6.6 | — | — |

Verified programmatically: **no cycles, no dangling task IDs, all 53 tasks reachable.**

## Execution waves

Tasks with no unmet dependencies, grouped by the round they can start in. Everything in a wave can run in parallel.

| Wave | Tasks |
|---|---|
| 1 | Pre.1 |
| 2 | Pre.2, Pre.3 |
| 3 | 0.1, 0.3, 0.4 |
| 4 | 0.2, 0.5, 0.6, 1.1, 2.4 |
| 5 | 0.8, 0.9, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.1, 2.3, 2.5, 3.1, 4.1 |
| 6 | 0.7, 1.8, 1.9, 2.2, 3.2, 4.2, 4.6, 5.1, 6.6, 6.7 |
| 7 | 4.3, 4.7, 5.2, 5.3, 5.4, 7.6 |
| 8 | 4.4, 5.5, 5.6, 6.1, 6.4 |
| 9 | 4.5, 6.2, 6.5, 7.1, 7.2, 7.3, 7.4, 7.5 |
| 10 | 6.3 |

## Milestones

| ID | Phase | Exit condition (measurable) | Verify with |
|---|---|---|---|
| `ME` | Pre | `CLAUDE.md` and `AGENTS.md` both exist (both created via `/agent-config create`); the test command of record is documented in `CLAUDE.md` and the Pre.1 notes | `test -f CLAUDE.md && test -f AGENTS.md && grep -q 'pytest -q -p no:cacheprovider' CLAUDE.md` |
| `M0` | P0 | From a clean checkout, CI is green on `main` across all 9 matrix cells; `mypy music_cli` produces identical output locally and in CI with no untracked errors; the suite is hermetic; a lockfile is committed; a derived coverage floor is enforced | `gh run list --workflow=ci.yml --branch=main -L 3 --json conclusion` → 3 × `success`; `diff` of local vs CI mypy output is empty |
| `M1` | P1 | `pip-audit` reports 0 High or Critical advisories; wave W2 has landed | `.venv/bin/pip-audit -f json` exits 0 with no High/Critical entries |
| `M2` | P2 | Every major is current or listed in **Deferred** with a written rationale; the Python floor has remaining upstream support | `grep -E 'uses: .*@[0-9a-f]{40}' .github/workflows/*.yml \| wc -l` equals the total `uses:` count; `python3 -c` check that the `requires-python` floor's EOL date is in the future |
| `M3` | P3 | Coverage ≥ **75%** with the floor enforced and reproducible under an isolated `HOME`; `mypy music_cli` clean with zero untracked errors; no function exceeds complexity 15; no logic block repeated ≥ 3 times appears in a re-run of the audit's clone detection | `.venv/bin/pytest -q -p no:cacheprovider --cov-fail-under=75`; `.venv/bin/ruff check --isolated --select C901 --config 'lint.mccabe.max-complexity=15' music_cli` |
| `M4` | P4 | `scan_directory` ≤ **100 ms** on 10,000 files (was 296.6 ms); `History.get_by_index(1)` ≤ **5 ms** on 50,000 entries (was 120.0 ms); every documented command runs as written | the benchmark tests from 7.1 and 7.2 pass; the doc-command extraction script from 7.6 exits 0 |

## Deferred and out of scope

Every `Critical` and `High` finding is scheduled — **nothing is deferred**. The table is retained
because the following decisions are the ones most likely to *become* deferrals during execution, and
recording them now makes that a decision rather than an oversight.

| ID | Severity | Why it might be deferred | Revisit when |
|---|---|---|---|
| `F-DEP-005`, `F-DEP-006` | Medium | The transformers v5 `generate` changes may prove deeper than the migration guide suggests once the AI extras are actually installed — the audit could not verify this, since `torch`/`transformers` are absent from the environment. If 4.6 exceeds its 3-day estimate, deferring is legitimate: the `<4.51` and `<5` caps are safe pins, not vulnerabilities. | The AI extras are installed and a generation run is reproducible in CI |
| `F-BUG-015` | Medium | `process_group=0` requires Python ≥ 3.11. If 3.1 keeps the floor at 3.10 until its October 2026 EOL, this cannot land. | The floor moves to ≥ 3.11 |
| `F-CLEAN-002` | Medium | `_JSONRequestFramer.feed` is complexity 21 but is the most rigorous and best-tested code in the repository. "Leave it, with a comment" is an acceptable outcome of 6.6 — the criterion allows it explicitly. | A defect is found in the framer, or it needs extension |

## Risks

| Risk | Affects | Mitigation |
|---|---|---|
| **`W1` is empty on unverified grounds.** No advisory database was consulted during the audit, so "0 vulnerabilities" is *unmeasured*, not *confirmed*. If `pip-audit` surfaces High/Critical advisories, P1 grows and `M1` slips. | 1.1, `M1`, the whole P1 estimate | 1.1 runs first in P1 and its criteria require a task or a Deferred row per advisory before `M1` can be claimed |
| **The Python 3.10 EOL is 73 days out**, which is inside this plan's likely execution window. Deferring 3.1 means shipping a package whose declared floor receives no security fixes. | 3.1, 3.2, 4.6, `M2` | 3.1 sits early in P2 and depends only on 0.5 and 1.1 — it can start in wave 5, well before the deadline |
| **The daemon refactor chain is the critical path and has no parallel slack.** Any slip in 5.1, 5.4, or 6.1 moves the finish date one-for-one. | 5.1 → 5.4 → 6.1 → 6.2 → 6.3 | 5.4 writes characterization tests *before* any restructuring, so a failed refactor is detected immediately rather than after 6.3; 6.1's criteria require the 5.4 tests to pass **unmodified** |
| **AI code paths cannot be verified in the current environment.** `torch`, `transformers`, `diffusers`, `scipy`, `accelerate`, `soundfile`, and `yt-dlp` are not installed, so 4.6, 4.7, and parts of 5.6 rest on static reading. Whether the pinned AI stack even resolves on Python 3.14 is unknown. | 4.6, 4.7, 5.6, `M2`, `M3` | 4.6 and 4.7 both require a manual end-to-end generation run recorded in the PR — not merely a green suite |
| **`mypy` has never actually run**, so the type-error count behind 0.3 is unknown. It could be zero or it could be hundreds, which would change P0's size substantially. | 0.3, `M0`, `M3` | 0.3's criteria permit triaging real errors into follow-up issues rather than requiring exit 0 immediately — but explicitly forbid silencing them with a blanket ignore |
| **Two Sprint-6 refactors touch the same files as Sprint-4 upgrades** if execution overlaps (both modify workflows and `pyproject.toml`). | 4.1–4.5 vs 6.6, 7.6 | The dependency table places 6.6 after 2.3 and 7.6 after 6.6; keep the action bumps on a separate branch and land them in wave order |
