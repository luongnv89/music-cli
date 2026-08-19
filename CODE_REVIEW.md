# Code Review Report

**Date**: 2026-08-19
**Scope**: Full Audit — `music_cli/` package + `install.sh` (tests excluded by request)
**Mode**: Mode 1 (inline; 37 files, ~5.9 kLOC — under the 50-file / 5 kLOC subagent threshold)
**Files Reviewed**: 37 (36 Python modules + 1 shell script)
**Commit**: `0f00ec5` on `main`
**Excluded**: `tests/`, `build/`, `dist/`, `*.egg-info/`, `.venv/`, generated caches

> Read-only review. No source file was modified — verified with `git diff --stat` (empty).

## Summary

| Severity | Count |
|----------|-------|
| Critical | 2     |
| Major    | 9     |
| Minor    | 11    |
| Info     | 2     |

Two defects were confirmed with runnable reproductions (C-1, M-1) rather than by inspection alone.
The dominant theme is **an unauthenticated local control plane** (`daemon.py` + `platform/ipc.py`)
whose input-handling is well-defended at the framing layer but unguarded at the command layer:
request parsing enforces size caps, timeouts, and strict JSON framing, while the commands those
requests reach accept arbitrary filesystem paths, mutate shared player state without a lock, and
return raw exception text to the caller.

---

## Critical Issues

### [Correctness / Data Integrity]: Shallow copy of `DEFAULT_CONFIG` corrupts class-level defaults process-wide
**File**: `music_cli/config.py:337`
**Smell**: Inappropriate Intimacy / shared mutable state

`DEFAULT_CONFIG` is a **class attribute containing nested dicts**. `.copy()` is shallow, so
`self._config["player"]` *is* `Config.DEFAULT_CONFIG["player"]`. Any unreadable or malformed
`config.toml` sends `_load_config` down this branch; the next `Config.set()` then writes **through
the alias into the class attribute**. From that point every newly constructed `Config` in the
process inherits the mutated defaults and persists them to disk.

Confirmed by reproduction:

```
aliased?                       True
DEFAULT_CONFIG['player'] before: {'backend': 'ffplay', 'volume': 80}
DEFAULT_CONFIG['player'] after : {'backend': 'ffplay', 'volume': 11}
fresh Config default volume    : 11        # <- brand-new Config, brand-new config dir
```

Note the module already defines `_recursive_mapping_merge` using `deepcopy` (`config.py:25-36`) —
the correct primitive exists and is simply not used on this path.

**Before**:
```python
except (OSError, tomllib.TOMLDecodeError) as e:
    logger.warning(f"Failed to load config from {self.config_file}: {e}")
    self._config = self.DEFAULT_CONFIG.copy()
```

**Suggested Fix**:
```python
from copy import deepcopy

except (OSError, tomllib.TOMLDecodeError) as e:
    logger.warning(f"Failed to load config from {self.config_file}: {e}")
    self._config = deepcopy(self.DEFAULT_CONFIG)
```

---

### [Dead Code / Correctness]: `get_media_controller()` raises `ModuleNotFoundError` on every call
**File**: `music_cli/platform/__init__.py:155`
**Smell**: Dead Code / Speculative Generality

`get_media_controller()` is exported in `__all__` (`platform/__init__.py:203`) and documented as
returning a platform-appropriate controller. It imports `.media_controller`,
`.media_controller_linux`, and `.media_controller_windows` — **none of which exist in the
repository**, and `git log --all` shows they were never committed. The unconditional import at
line 155 sits *outside* the `try:` at line 165, so the `except ImportError` guard below it cannot
catch anything:

```
$ python -c "from music_cli.platform import get_media_controller; get_media_controller()"
RAISES ModuleNotFoundError: No module named 'music_cli.platform.media_controller'
```

Impact is currently contained — `grep` finds **zero call sites** in `music_cli/` or `tests/`, and
coverage confirms lines 155-191 are never executed. But this is exported public API that crashes,
and the absent feature is still advertised: `pyproject.toml:18` lists `media-keys`, `mpris`, and
`now-playing` as package keywords, and `README.md:539-540` credits pyobjc and dbus-next "for media
key support" and "Linux MPRIS media controls".

**Suggested Fix**: Delete `get_media_controller()`, its `__all__` entry, and the `MediaController`
`TYPE_CHECKING` import (`platform/__init__.py:23`); drop the now-unused `dbus-next` and
`winrt-Windows.Media.Playback` runtime dependencies (`pyproject.toml:39-40`) and the stale keywords
and README credits. Alternatively restore the three missing modules — but do not leave exported API
that cannot be called.

---

## Major Issues

### M-1. [Security]: `LocalSource.get_track` has no path confinement
**File**: `music_cli/sources/local.py:25-39`
**Smell**: Missing input validation

`music_dir` is documented as the boundary but is only consulted for *relative* paths (line 33). An
absolute path is accepted verbatim; the only filter is the audio-extension check at line 38. The
`source` value reaches this function straight from an IPC request (`daemon.py:316`), so any local
process that can reach the daemon can have it open and stream **any file on the filesystem** whose
name ends in `.mp3/.m4a/.flac/.wav/.ogg/.opus`.

Confirmed by reproduction:
```
music_dir boundary : /Users/montimage/Music
requested path     : /var/folders/.../not-my-music.mp3
track returned     : /var/folders/.../not-my-music.mp3     # accepted, outside the boundary
```

**Suggested Fix**:
```python
file_path = (self.music_dir / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
if not file_path.is_relative_to(self.music_dir.resolve()):
    return None
```
If out-of-tree playback is a deliberate feature, make it an explicit opt-in config flag rather than
the default, and say so in the docstring.

### M-2. [Security]: Windows TCP IPC listener is unauthenticated
**File**: `music_cli/platform/ipc.py:245-249`
**Smell**: Inconsistent security boundary across implementations

The Unix transport restricts the socket to its owner (`ipc.py:139`, `chmod(0o600)`). The Windows
transport binds `127.0.0.1:44556` with **no equivalent access control** — loopback TCP on Windows is
reachable by every user session and every process on the host. Any of them can drive playback, read
history, or issue `shutdown`, and via M-1 can read arbitrary audio files. The two transports are
presented as interchangeable but do not carry the same guarantees.

**Suggested Fix**: Require a shared secret on every request — generate a token at daemon start,
write it to the config dir with owner-only permissions, and have `TCPIPCServer` reject requests
that do not present it. Named pipes with a security descriptor are the stronger alternative.

### M-3. [Security]: Unix socket is world-accessible between bind and `chmod` (TOCTOU)
**File**: `music_cli/platform/ipc.py:133-139`
**Smell**: Time-of-check/time-of-use

`asyncio.start_unix_server` creates the socket with umask-derived permissions (commonly `0755`), and
only the *next* statement narrows it to `0600`. A local attacker that connects inside that window
holds a fully privileged daemon connection. `ruff` also flags line 139 as `ASYNC240` — a blocking
`pathlib` call in an async function.

**Suggested Fix**: Set the umask to `0o077` around the bind, or bind inside a directory that is
itself `0700`, so the socket is never briefly permissive.

### M-4. [Concurrency]: Fire-and-forget `asyncio.create_task` — tasks may be garbage-collected mid-run
**File**: `music_cli/daemon.py:457`, `music_cli/daemon.py:871`
**Smell**: Missing error handling (`ruff RUF006`)

The event loop holds only a weak reference to a task; without a strong reference the task can be
collected before it finishes. Line 871 is the more damaging of the two — it is the `shutdown`
command's stop path, so a collected task means the daemon acknowledges `shutting_down` and then
keeps running. Line 457 is the auto-play chain, which would silently stop advancing.

**Before**:
```python
asyncio.create_task(self.stop())
```

**Suggested Fix**:
```python
self._background_tasks: set[asyncio.Task] = set()   # in __init__
...
task = asyncio.create_task(self.stop())
self._background_tasks.add(task)
task.add_done_callback(self._background_tasks.discard)
```
The same pattern is needed for the signal handler at `daemon.py:147`, which also discards its task.

### M-5. [Concurrency]: `_cmd_play` mutates shared player state with no lock
**File**: `music_cli/daemon.py:302-452`
**Smell**: Race condition

`asyncio.start_server` runs one task per connection, so commands interleave at every `await`.
`_cmd_play` writes `self._auto_play` (line 307), `self._current_mood` (line 312), and then awaits
`self.player.play(track)` (line 423). Two concurrent `play` requests interleave inside
`FFplayPlayer.play`, which itself awaits `self.stop()` and then reassigns `self._process`
(`player/ffplay.py:47,97`) — the loser's ffplay process is dropped from `_process` while still
running, orphaning it until the daemon exits.

**Suggested Fix**: Guard every state-mutating handler with a single `asyncio.Lock` held for the
duration of the command, or serialize commands through a queue.

### M-6. [Correctness]: PID reuse wedges the daemon permanently
**File**: `music_cli/daemon.py:886-914`
**Smell**: Insufficient validation

`_pid_alive` asks only "does *a* process with this PID exist". After an unclean exit the stale PID
file survives, and once the OS recycles that PID to an unrelated process, `is_daemon_running()`
returns `True` forever. `ensure_daemon` (`cli.py:145`) therefore never restarts the daemon, and
every subsequent command fails on connect. Recovery requires manually deleting the PID file — which
nothing tells the user to do.

**Suggested Fix**: Record an identity token alongside the PID (daemon start time, or a random nonce
also served by `ping`) and treat the PID as live only when both match. Falling back to a successful
`ping` over the socket before trusting the PID file is the simplest robust check.

### M-7. [Correctness]: `install.sh` cannot work on Windows despite detecting it
**File**: `install.sh:177-178`
**Smell**: Dead path / untested branch

`detect_os` explicitly recognises `mingw*|msys*|cygwin*` and returns `windows` (`install.sh:55`),
and `main` proceeds to `install_music_cli` for that value. But the venv layout is hardcoded to the
POSIX form:

```bash
local venv_python="$INSTALL_DIR/bin/python"
local venv_pip="$INSTALL_DIR/bin/pip"
```

On Windows, `python -m venv` creates `Scripts/`, not `bin/`, so line 181 fails immediately. The
`ln -s` in `link_binary` (line 208) is likewise not meaningful there. Either the Windows branch
works or it should `die` with a clear message — right now it fails opaquely under `set -e`.

**Suggested Fix**: Select the layout after creating the venv:
```bash
local venv_bindir="$INSTALL_DIR/bin"
[ -d "$INSTALL_DIR/Scripts" ] && venv_bindir="$INSTALL_DIR/Scripts"
```
and gate `link_binary` on a non-Windows OS.

### M-8. [Safety]: Installer silently deletes any existing `~/.local/bin/mc`
**File**: `install.sh:205-208`
**Smell**: Destructive default

```bash
if [ -L "$link_target" ] || [ -f "$link_target" ]; then
    rm -f "$link_target"
fi
ln -s "$venv_bin" "$link_target"
```

`mc` is a widely used name — GNU Midnight Commander installs exactly that binary. The loop removes
whatever is at `~/.local/bin/mc` with no check that it belongs to music-cli, no prompt, and no
backup. A user who runs the documented `curl … | bash` one-liner can lose an unrelated tool from
their `PATH` without ever being told.

**Suggested Fix**: Skip and warn when the existing target does not resolve into `$INSTALL_DIR`;
offer `FORCE_LINK=1` for the deliberate override.

### M-9. [Maintainability]: Daemon startup failures produce no diagnostic
**File**: `music_cli/cli.py:156`, `music_cli/cli.py:180`, `music_cli/cli.py:189`

`start_daemon_background` sends both `stdout` and `stderr` to `DEVNULL`, so any exception raised
during daemon startup is discarded. `ensure_daemon` then polls for a fixed 2 s and exits with the
bare string `Failed to start daemon`. The user gets no traceback, no log path, and no hint — and
because the daemon writes its log only after it starts, there is nothing to read afterwards either.

**Suggested Fix**: Redirect the child's `stderr` to a log file under the config dir and print that
path in the failure message.

---

## Minor Issues

| # | File | Issue |
|---|---|---|
| m-1 |  `music_cli/daemon.py:294` | `return {"error": str(e)}` returns raw exception text to the caller — leaks absolute filesystem paths and internal state to an unauthenticated client. Return a generic message and log the detail. |
| m-2 | `music_cli/config.py:308-310` | Config dir created with default permissions (typically `0755`). It holds the socket, PID file, history, and YouTube cache. Create it `0o700`. |
| m-3 | `music_cli/hf_cache.py:166` | `snapshot_download(repo_id=...)` with no `revision=` pin — resolves to whatever `main` points at now. Same for the five `from_pretrained` calls (`musicgen_strategy.py:42-43`, `minimax_strategy.py:54`, `bark_strategy.py:56-57`, `audioldm_strategy.py:56`). `trust_remote_code` is left at its `False` default, which rules out remote code execution, so this is supply-chain drift rather than an RCE. `B615` is globally skipped in `pyproject.toml:137`, which hides it from Bandit. Pin a revision per model. |
| m-4 | `music_cli/player/ffplay.py:166` | `preexec_fn=os.setsid` is documented as unsafe in the presence of threads (and `cli.py` does start threads). Python 3.11+ offers `process_group=0`; `requires-python` is `>=3.10`, so gate it or raise the floor. |
| m-5 | `music_cli/sources/radio.py:12`, `music_cli/daemon.py:337` | YouTube detection is a substring test (`"youtube.com" in url`), which matches `https://evil-youtube.com.attacker.net/x`. Parse the URL and compare the host. `sources/youtube.py:45` already does this properly with regex patterns — reuse it. |
| m-6 | `music_cli/player/ffplay.py:108`, `:171` | Liveness is inferred from `await asyncio.sleep(0.1)` then checking `returncode`. An ffplay that dies at 150 ms is still reported as playing. This is the mitigation added for #28/#30; a `wait()`-with-timeout race would be deterministic. |
| m-7 | `install.sh:238-243`, `:283-300` | 15 × `SC2059` — variables in `printf` format strings. `INSTALL_DIR` (line 243) and `EXTRAS` (line 293) are user-controlled env vars, so `INSTALL_DIR='%s%s'` produces garbled output. Use `printf '%s' "$var"`. |
| m-8 | `install.sh:103` | `[ "$major" -ge 3 ] && [ "$minor" -ge 10 ]` rejects a hypothetical Python 4.0 despite it satisfying `>=3.10`. Compare on the tuple. |
| m-9 | `music_cli/daemon.py:266-286` | The 19-entry handler dict is rebuilt on every single request. Hoist it to a class attribute or build it once in `__init__`. |
| m-10 | `install.sh:26` | `BRANCH="main"` is assigned and never used (`SC2034`). Dead variable. |
| m-11 | `music_cli/sources/youtube.py:42` | `_clean_url` strips *all* backslashes unconditionally to undo copy/paste damage. A URL with a legitimately percent-decoded backslash is silently altered. Restrict the fix to the known paste corruption. |

## Info

| # | File | Note |
|---|---|---|
| i-1 | `music_cli/player/ffplay.py:157-160` | The `create_subprocess_shell` pipeline is **safe as written** — both paths are `shlex.quote`d and `self._volume` is int-typed at every assignment (`base.py:50`, `ffplay.py:299`, `daemon.py:510`). It is worth noting only because the safety rests on an invariant no type checker enforces at this call site; an f-string into a shell is a fragile place to depend on one. |
| i-2 | `music_cli/daemon.py:153` | `self.config.pid_file.write_text(...)` is unguarded. If the config dir is not writable the daemon dies *after* the IPC server is already accepting connections, leaving a listening socket with no PID file. |

---

## What is done well

Worth recording so it is not "improved" away:

- **`_JSONRequestFramer` (`daemon.py:35-109`)** is a genuinely careful incremental JSON framer —
  string/escape/unicode state machine, correct bracket matching, and rejection of trailing garbage.
- **`_read_request` (`daemon.py:179-229`)** enforces a 1 MB cap, a 5 s deadline, and correct handling
  of UTF-8 sequences split across chunk boundaries — including the subtle case at lines 218-222
  where a pending continuation byte after the closing brace must not be mistaken for completion.
- Error paths in `platform/ipc.py:204-215` close the socket before re-raising, and chain with
  `from e` throughout.

## Recommendations

1. **Fix C-1 first** — it is a two-word change (`deepcopy`) that prevents silent corruption of the
   user's persisted config, and it has a reproduction to turn into a regression test.
2. **Decide what the daemon's trust boundary is**, then enforce it uniformly. M-1, M-2, M-3, and m-1
   are one design gap seen from four angles: the Unix path assumes owner-only access and the Windows
   path silently does not provide it. Either both transports authenticate, or the Windows transport
   should not ship.
3. **Resolve C-2 by deletion, not restoration**, unless media-key support is actually on the roadmap
   — and drop the two runtime dependencies, three keywords, and two README credits that advertise it.
4. **Add a concurrency guard to the daemon** (M-4, M-5). These are cheap to fix and expensive to
   diagnose in the field, since both fail intermittently and leave no log.
5. **Treat `install.sh` as shipped code.** M-7 and M-8 are user-facing defects in the file the README
   asks people to pipe into `bash`; `shellcheck` is installed on this machine and catches m-7 and
   m-10 today but runs in neither CI nor pre-commit. Its only test asserts on three substrings of the
   script text.
