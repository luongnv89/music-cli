# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Add the `mc cloud key` command group (`set`/`get`/`delete`/`list`) storing cloud provider API keys in the OS keyring via `keyring`; provider `gmi` (GMI Cloud) is supported, and keys never touch config files, environment variables, or git ([#151](https://github.com/luongnv89/music-cli/issues/151)).
- Add the `gmi` optional extra (`pip install 'coder-music-cli[gmi]'`) declaring `keyring>=24` and `httpx>=0.27` for the upcoming GMI Cloud / MiniMax adapter layer ([#151](https://github.com/luongnv89/music-cli/issues/151)).

## [0.11.0] - 2026-08-22

### Breaking Changes
- Raise the supported Python floor from `>=3.10` to `>=3.12` (`F-DEP-001`). **Upgrade:** install and run under Python 3.12+; the dead `tomli` shim (`python_version<'3.11'`) and its fallback import are removed, and standalone CI jobs move 3.11 → 3.12. **Decision rationale:** Python 3.10 reaches end-of-life on **2026-10-31**, so committing to test it until then buys nothing; `>=3.11` was rejected because the installed numpy stubs use PEP 695 `type` statements, which mypy rejects when targeting <3.12; `>=3.12` is the only value that lets all declaration sites (`requires-python`, classifiers, ruff/black target-version, mypy python_version, CI matrix) agree ([#111](https://github.com/luongnv89/music-cli/pull/111), [#58](https://github.com/luongnv89/music-cli/issues/58)).
- Migrate the `ai` and `minimax` extras to transformers 5.x: both extras now require `transformers>=5,<6`, with MusicGen, AudioLDM/Bark strategies and the MiniMax Music 3 Diffusers pipeline validated against the transformers 5.x API ([#113](https://github.com/luongnv89/music-cli/pull/113)).

**Upgrade notes:** users on Python 3.10 or 3.11 must upgrade their interpreter before installing this release (pip will refuse older interpreters via `requires-python`). If you use AI generation (`ai`) or MiniMAX (`minimax`) extras, re-install them to pick up transformers 5.x: `pip install --upgrade 'coder-music-cli[ai,minimax]'` (or run `pip install --upgrade 'transformers>=5,<6'` in an existing environment). No action is needed for radio/local/YouTube playback.

### Added
- Add `pip-audit` to the `dev` extra and a `Dependency Audit` CI job that runs `pip-audit --strict -f json` and uploads the machine-readable report, establishing the advisory baseline for milestone `M1` ([#44](https://github.com/luongnv89/music-cli/issues/44)).

### Performance
- Cap the playback history at 1000 entries (configurable via `history.max_entries` in `config.toml`), rotating the oldest entries out on write to match the YouTube history's bound; `history play N` now reads small indexes from the tail of the file instead of parsing it whole, keeping replay fast on large history files (`F-PERF-002`) ([#80](https://github.com/luongnv89/music-cli/issues/80)).
- Scan the local music library in a single pass keyed by file mtime, so unchanged tracks are no longer rescanned on every library refresh ([#81](https://github.com/luongnv89/music-cli/issues/81)).
- Store AI-generated tracks in an append-only JSONL log with transparent migration of legacy array-format stores, avoiding full-file rewrites on every generation ([#82](https://github.com/luongnv89/music-cli/issues/82)).
- Cache parsed radio stations at startup so repeated radio commands stop re-parsing the station list ([#83](https://github.com/luongnv89/music-cli/issues/83)).

### Fixed
- Fix YouTube URL detection to compare the parsed hostname instead of substring matching, so look-alike hosts such as `evil-youtube.com.attacker.net` are no longer routed to yt-dlp or filtered incorrectly; the check is shared by `RadioSource`, the daemon's radio-mode handler, and `YouTubeSource.get_track` ([#84](https://github.com/luongnv89/music-cli/issues/84)).
- Narrow installer-adjacent URL cleaning so only copy/paste corruption backslashes (before `. ? & = % -`) are stripped; legitimate URLs containing other backslashes are no longer altered before extraction ([#84](https://github.com/luongnv89/music-cli/issues/84)).
- Fix a startup liveness race in `ffplay` playback: the 0.1 s sleep-then-poll is replaced by waiting on the subprocess with a timeout, so a process that dies anywhere inside the probe window is reliably detected as a failed start, for both direct and YouTube-pipe playback ([#84](https://github.com/luongnv89/music-cli/issues/84)).
- Fail daemon startup *before* binding the IPC socket when the PID file cannot be written, instead of killing an already-listening daemon afterwards ([#84](https://github.com/luongnv89/music-cli/issues/84)).
- Fix `install.sh`: color codes are passed as `printf` arguments rather than interpolated into format strings (`SC2059`, hardening against user-controlled `INSTALL_DIR`/`EXTRAS`), and the Python version gate compares tuples instead of fragile string prefixes ([#84](https://github.com/luongnv89/music-cli/issues/84)).
- Surface daemon startup failures to the CLI via `daemon.log` instead of failing silently ([#71](https://github.com/luongnv89/music-cli/issues/71)).
- Make daemon liveness identity-checked so a stale or recycled PID file can no longer make a foreign process look like a running daemon ([#68](https://github.com/luongnv89/music-cli/issues/68)).
- Serialize daemon command handlers and track background tasks, preventing interleaved command execution and lost async work ([#67](https://github.com/luongnv89/music-cli/issues/67)).
- Replace `preexec_fn=os.setsid` with `process_group=0` when spawning `ffplay`, avoiding fork-safety issues in threaded/async contexts ([#112](https://github.com/luongnv89/music-cli/pull/112)).
- Remove the dead media-controller platform surface left behind by earlier removals ([#53](https://github.com/luongnv89/music-cli/issues/53)).
- Pin HuggingFace model revisions for reproducible downloads and un-skip the B615 check ([#49](https://github.com/luongnv89/music-cli/issues/49)).
- Fix `install.sh` venv layout detection and stop it from clobbering an unrelated existing `mc` command ([#50](https://github.com/luongnv89/music-cli/issues/50)).
- Repair the mypy CI gate so it actually runs ([#37](https://github.com/luongnv89/music-cli/issues/37)).
- Skip Unix-only YouTube-pipe `ffplay` tests on Windows ([#35](https://github.com/luongnv89/music-cli/issues/35)).
- Fix HuggingFace download compatibility and upgrade the installer flow ([#31](https://github.com/luongnv89/music-cli/pull/31)).

### Security
- Harden config defaults, IPC authentication, and file/directory permissions for the daemon socket and state ([#45](https://github.com/luongnv89/music-cli/issues/45)).
- Confine local playback to the configured music directory, rejecting paths that escape it ([#46](https://github.com/luongnv89/music-cli/issues/46)).
- Harden the documented install flow against injection and unsafe defaults ([#52](https://github.com/luongnv89/music-cli/issues/52)).
- Establish the `pip-audit` advisory baseline: the initial recorded audit surfaced one advisory (`setuptools` 79.0.1, `PYSEC-2026-3447` / `CVE-2026-59890`), fixed by pinning `setuptools==83.0.0` in `constraints-dev.txt`; a re-run reports **0 High or Critical advisories**, making `M1`'s exit condition measurable ([#44](https://github.com/luongnv89/music-cli/issues/44)).

### Documentation
- Realign the documentation with the code: the Building guide's local-install step now uses the real package name and current version (`pip install dist/coder_music_cli-<version>-py3-none-any.whl` instead of the nonexistent `music_cli-0.1.0` wheel), the PyPI keywords no longer advertise the media-controller support removed by Task 2.1 (`media-keys`, `mpris`, `now-playing` dropped), and the README Acknowledgements no longer credit pyobjc/dbus-next for that absent support (`F-DOCS-001/003/004`), followed up by a reconciliation pass over the remaining docs ([#85](https://github.com/luongnv89/music-cli/issues/85)).
- Add `CLAUDE.md` with build/test commands ([#33](https://github.com/luongnv89/music-cli/issues/33)).
- Add `AGENTS.md` with subagent definitions ([#34](https://github.com/luongnv89/music-cli/issues/34)).
- Record agent install/run/verify instructions ([#32](https://github.com/luongnv89/music-cli/issues/32)).
- Document in CONTRIBUTING that a red `main` blocks merges until fixed ([#36](https://github.com/luongnv89/music-cli/issues/36)).
- Add the modernization audit report and phased plan.

### Dependencies
- Prune orphaned dependencies, raise the `yt-dlp` floor, and fix project classifiers ([#54](https://github.com/luongnv89/music-cli/issues/54)).
- Refresh pre-commit hooks and unify ruff at 0.16.4 ([#55](https://github.com/luongnv89/music-cli/issues/55)).
- Bump actions/checkout v4→v7 and setup-python v5→v7 ([#107](https://github.com/luongnv89/music-cli/pull/107)).
- Bump artifact actions — upload v4→v7, download v4→v8 ([#108](https://github.com/luongnv89/music-cli/pull/108)).
- Bump codecov/codecov-action v4→v7 ([#109](https://github.com/luongnv89/music-cli/pull/109)).
- Bump action-gh-release v1→v3 and SHA-pin every GitHub Action ([#110](https://github.com/luongnv89/music-cli/pull/110)).

### Other Changes
- Refactor the CLI entrypoint: split `cli.py` into a per-group command package ([#76](https://github.com/luongnv89/music-cli/issues/76)).
- Refactor the daemon: split out the command registry and AI handlers ([#74](https://github.com/luongnv89/music-cli/issues/74)); decompose `_cmd_play` into per-mode handlers ([#73](https://github.com/luongnv89/music-cli/issues/73)).
- Standardize formatting on `ruff format` and group wide parameter lists ([#78](https://github.com/luongnv89/music-cli/issues/78)); remove dead code and mark ARG002 interface conformance ([#79](https://github.com/luongnv89/music-cli/issues/79)).
- Test: characterize all 19 daemon command handlers ([#70](https://github.com/luongnv89/music-cli/issues/70)); make coverage honest and enforce a 75 percent floor ([#72](https://github.com/luongnv89/music-cli/issues/72)); make the test suite hermetic ([#43](https://github.com/luongnv89/music-cli/issues/43)).
- CI: enforce a derived 53% coverage floor (superseded by the 75 percent floor above) ([#41](https://github.com/luongnv89/music-cli/issues/41)); test the Python floor the package declares ([#39](https://github.com/luongnv89/music-cli/issues/39)); pin lint tool revs, add shellcheck, arm pre-commit ([#40](https://github.com/luongnv89/music-cli/issues/40)); scope the ci workflow token to `contents: read` ([#42](https://github.com/luongnv89/music-cli/issues/42)).
- Build: commit pinned dev constraints for reproducible installs ([#38](https://github.com/luongnv89/music-cli/issues/38)).

**Full Changelog**: https://github.com/luongnv89/music-cli/compare/v0.10.1...v0.11.0

## [0.10.1] - 2026-08-17

### Fixed
- Fix `mc ai model` crashes when AI extras are not installed by lazily importing concrete AI strategy classes, allowing core AI model types to load without optional dependencies ([#29](https://github.com/luongnv89/music-cli/pull/29)).
- Fix playback state reporting when `ffplay` exits immediately by verifying spawned processes remain alive before declaring playback active and cleaning up failed startup state, including YouTube pipe playback ([#30](https://github.com/luongnv89/music-cli/pull/30)).

**Full Changelog**: https://github.com/luongnv89/music-cli/compare/v0.10.0...v0.10.1

## [0.10.0] - 2026-08-17

### Added
- Add MiniMax Music 3 lyrics-conditioned generation via the official `MiniMaxAI/MiniMax-Music3` model and Diffusers pipeline, with CLI model selection, lyrics propagation, capability validation, replay metadata, tests, and documentation ([#25](https://github.com/luongnv89/music-cli/pull/25)).

### Fixed
- Fix cross-platform daemon PID liveness checks on Windows by replacing the unsafe `os.kill(pid, 0)` probe while preserving Unix checks and stale-PID cleanup ([#26](https://github.com/luongnv89/music-cli/pull/26)).
- Make the MiniMax optional dependency PyPI-compatible by targeting the released Diffusers 0.39.x ModularPipeline integration.

### Changed
- Ignore generated Python bytecode and local issue-resolution state in source control.

**Full Changelog**: https://github.com/luongnv89/music-cli/compare/v0.9.1...v0.10.0

## [0.9.1] - 2026-07-23

### Fixed
- Fix local file playback with relative paths by resolving them against the caller's working directory ([#22](https://github.com/luongnv89/music-cli/pull/22))
- Fix `install.sh` so the `mc` command is symlinked and available after installation ([#21](https://github.com/luongnv89/music-cli/pull/21))

**Full Changelog**: https://github.com/luongnv89/music-cli/compare/v0.9.0...v0.9.1

## [0.9.0] - 2026-04-05

### Added
- Add `mc` alias and short command names for faster CLI usage (CLI v2 Phase 1)
- Add playback aliases for common actions (CLI v2 Phase 1)
- Add smart play detection and unified AI command (CLI v2 Phase 2)
- Add `history` subcommand to view recently played tracks (CLI v2 Phase 2)
- Add volume validation for playback commands (CLI v2 Phase 2)
- Add help shortcut and `NO_COLOR` environment variable support (CLI v2 Phase 3)
- Add one-liner install script (`curl | bash`) for easier installation
- Add end-to-end tests for all commands with CI matrix for Python 3.12, 3.13, and 3.14
- Add YouTube replay history tracking for CLI

### Fixed
- Fix AI timeout increased to 10 minutes and improve URL cleaning for YouTube source
- Fix Windows `PermissionError` in `test_file_exists_true` test
- Fix mypy compatibility in environments with and without `huggingface_hub` installed
- Suppress pre-existing mypy errors with `type: ignore` annotations
- Resolve CI lint failures and test mock contract bugs
- Bump `ruff-pre-commit` to v0.11.2 to match CI ruff version
- Skip `pytest-e2e` in CI pre-commit (language: system requires venv)

### Documentation
- Update all docs to reflect CLI v2 `mc` commands
- Restructure README as a landing page to convert visitors into users

### Other Changes
- Redesign logo with new Pulse Prompt identity
- Remove ASCII logo from `status` output for cleaner terminal display
- Remove web module entirely
- Separate Python and web CI workflows using path filters
- Add AI/dev tool configs to `.gitignore`
- Add OSS community health files (CONTRIBUTING, CODE_OF_CONDUCT, etc.)
- Apply pre-commit auto-fixes

## [0.8.14] - 2025-01-14

### Changed
- Remove ASCII logo from `music-cli status` output for cleaner terminal output

## [0.8.12] - 2025-01-10

### Fixed
- Fix missing mood validation for `melancholic` and `peaceful` in CLI
  - All 8 moods (happy, sad, excited, focus, relaxed, energetic, melancholic, peaceful) now work correctly

## [0.8.11] - 2025-01-08

### Changed
- Update brand color from indigo (#6366F1) to bright green (#22C55E) across all logo files
- Add ASCII art logo to `music-cli status` output (terminal chevron with sound waves)

## [0.8.10] - 2025-01-08

### Fixed
- Disable macOS media controller to fix audio quality issues caused by NSRunLoop polling interference with the asyncio event loop

## [0.8.9] - 2025-01-07

### Changed
- Add acknowledgements section to README listing open-source dependencies
- Fix ruff linting errors (use TimeoutError, import Callable from collections.abc)
- Update Python requirement to 3.10+ in CI and documentation

## [0.8.8] - 2025-01-07

### Changed
- Version bump

## [0.8.7] - 2025-01-07

### Improved
- Improve YouTube livestream playback for radio stations:
  - Pipe yt-dlp directly to ffplay for reliable HLS buffering and reconnections
  - Eliminates intermittent dropouts on YouTube livestreams
  - Falls back to direct URL playback on Windows

### Added
- Add Anjunadeep Radio as example YouTube radio station
- Add contributors section to README

## [0.8.6] - 2025-01-06

### Changed
- Auto-detect terminal width for radio list columns (1-6 columns based on terminal size)

## [0.8.5] - 2025-01-06

### Changed
- Change radio list to 4-column layout for more compact display

## [0.8.4] - 2025-01-06

### Improved
- Improve radio station list display:
  - Show stations in categorized format grouped by genre/language
  - Categories extracted from radios.txt comment structure

## [0.8.3] - 2025-01-05

### Added
- Add 5 new Nightride FM synthwave radio stations (320kbps):
  - Nightride FM (Synthwave/Retrowave/Outrun)
  - Chillsynth FM (Chillsynth/Chillwave)
  - Darksynth FM (Darksynth/Cyberpunk)
  - Datawave FM (Glitchy Synthwave/IDM)
  - Spacesynth FM (Spacesynth/Space Disco)

## [0.8.2] - 2025-01-05

### Fixed
- Fix missing mood radio mappings: all 8 moods now have working radio streams
  - Added streams for: relaxed (Groove Salad), energetic (DEF CON Radio), melancholic (Indie Pop Rocks), peaceful (Drone Zone)
  - Fixed fallback to default config when user config lacks mood mappings

## [0.8.1] - 2025-01-04

### Fixed
- Fix cached YouTube tracks not playing: reconnect options were incorrectly applied to local cached files instead of only remote streams

## [0.8.0] - 2025-01-04

### Added
- Add YouTube offline cache for automatic offline playback:
  - Automatically cache YouTube audio when played
  - Play cached tracks offline with `music-cli youtube play <num>`
  - Manage cache with `music-cli youtube` commands (list/play/remove/clear)
  - 2GB LRU cache with automatic eviction of oldest tracks
  - M4A format at 192kbps quality
  - Thread-safe cache operations
- Add `youtube` command group for cache management

## [0.7.0] - 2025-01-03

### Added
- Add YouTube audio streaming support:
  - Stream audio directly from YouTube URLs without downloading
  - Support for youtube.com, youtu.be, YouTube Shorts, and YouTube Music URLs
  - Install with: `pip install 'coder-music-cli[youtube]'`
  - Play with: `music-cli play -m youtube -s "https://youtube.com/watch?v=..."`
  - Short alias: `music-cli play -m yt -s "https://youtu.be/..."`

### Fixed
- Fix version sync between pyproject.toml and __init__.py

## [0.6.0] - 2025-01-02

### Added
- Add AI model management commands:
  - `music-cli ai models download <model>` - Download models before use
  - `music-cli ai models delete <model>` - Delete cached models to free space
  - `music-cli ai models set-default <model>` - Set default generation model
- Add model descriptions and expected sizes to `ai models` output
- Add download status tracking via HuggingFace cache inspection
- Add comprehensive AI Playbook documentation with examples

### Improved
- Improve config fallback to DEFAULT_CONFIG when user config is missing AI settings

## [0.5.0] - 2025-01-01

### Added
- Add multiple AI model support:
  - **AudioLDM models**: `audioldm-s-full-v2`, `audioldm-l-full` for sound effects and ambient audio
  - **Bark models**: `bark`, `bark-small` for speech synthesis
  - **MusicGen models**: All existing models continue to work
- Add `ai models` command to list all available AI models
- Add LRU cache for AI models with configurable size (default: 2 models)
- Add download progress bar during model downloads
- Add GPU memory management with automatic cleanup on model eviction
- Default model: `musicgen-small`

## [0.4.1] - 2024-12-30

### Added
- Add Windows 10+ support
  - Platform abstraction layer for cross-platform compatibility
  - TCP localhost IPC on Windows (Unix sockets on Linux/macOS)
  - stdin-based pause/resume on Windows (signals on Linux/macOS)
  - Windows-specific config directory (`%LOCALAPPDATA%\music-cli\`)
- Add Windows to CI test matrix

## [0.4.0] - 2024-12-28

### Added
- Add `music-cli ai` command suite for AI track management
  - `ai list` - Display all AI tracks with prompts
  - `ai play [-p "prompt"]` - Generate with context or custom prompt
  - `ai replay <num>` - Replay track (regenerates if missing)
  - `ai remove <num>` - Delete track and audio file
- Add seamless looping via prompt engineering
- Add context-aware AI generation (time of day, day of week, mood)

### Changed
- Default AI duration reduced to 5s for faster generation

## [0.3.0] - 2024-12-25

### Added
- Add radio station management (list/play/add/remove by number)
- Add 35 curated radio stations (English, French, Spanish, Italian)
- Add version-aware config with `update-radios` command
- Add inspirational quotes to status command
- Add "composing..." animation for AI generation
- Save AI-generated music to persistent directory for replay
- Show GitHub link in status output

### Changed
- Remove audiocraft dependency (use transformers only)

## [0.2.0] - 2024-12-20

### Changed
- Switch to HuggingFace Transformers for AI music generation
- Auto-loop AI-generated tracks
- Pin transformers<4.51 for MusicGen compatibility
- CI/CD improvements

## [0.1.0] - 2024-12-15

### Added
- Initial release
- Daemon-based playback
- Radio streaming, local files, AI generation
- Context-aware music selection
- Mood support
