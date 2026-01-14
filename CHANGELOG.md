# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
