<p align="center">
  <img src="assets/logo/logo-mark.svg" alt="music-cli logo" width="80" height="80">
</p>

<h1 align="center">music-cli</h1>

<p align="center"><em>Code. Listen. Iterate.</em></p>

<p align="center">
  <a href="https://pypi.org/project/coder-music-cli/"><img src="https://img.shields.io/pypi/v/coder-music-cli.svg" alt="PyPI version"></a>
  <a href="https://pepy.tech/project/coder-music-cli"><img src="https://static.pepy.tech/badge/coder-music-cli" alt="PyPI Downloads"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

<p align="center">
  <img src="music-cli-ai.gif" alt="music-cli AI demo" width="600">
</p>

A command-line music player for coders. Background daemon with radio streaming, local MP3s, and AI-generated music.

```bash
music-cli play --mood focus    # Start focus music
music-cli pause                # Pause for meeting
music-cli resume               # Back to coding
music-cli status               # Check what's playing + inspirational quote
```

## Installation

```bash
# Install from PyPI
pip install coder-music-cli

# Or with uv (faster)
uv pip install coder-music-cli

# Install FFmpeg (required)
brew install ffmpeg       # macOS
sudo apt install ffmpeg   # Ubuntu/Debian
choco install ffmpeg      # Windows (or: winget install ffmpeg)
```

### Optional: AI Music Generation

```bash
pip install 'coder-music-cli[ai]'  # ~5GB (PyTorch + Transformers + Diffusers)
```

Supports multiple AI models via HuggingFace: MusicGen, AudioLDM, and Bark.

### Optional: YouTube Audio Streaming

```bash
pip install 'coder-music-cli[youtube]'  # ~10MB (yt-dlp)
```

Stream audio directly from YouTube URLs with automatic offline caching:

```bash
music-cli play -m youtube -s "https://youtube.com/watch?v=..."
music-cli play -m yt -s "https://youtu.be/..."  # Short alias
music-cli youtube                               # List cached tracks
music-cli youtube play 1                        # Play cached track offline
```

## Features
- **Daemon-based** - Persistent background playback
- **Multiple sources** - Local files, radio streams, AI generation, **YouTube audio streaming**
- **Context-aware** - Selects music based on time of day and mood
- **40+ Radio Stations** - Curated stations in English, French, Spanish, Italian, and Synthwave
- **AI Music Generation** - Generate music with MusicGen, AudioLDM, or Bark models
- **YouTube Streaming** - Extract and stream audio directly from YouTube URLs
- **YouTube Offline Cache** - Automatically cache YouTube audio for offline playback
- **Version-aware Updates** - Automatic notification when new stations are available
- **Inspirational Quotes** - Random music quotes with every status check
- **Simple config** - Human-readable text files

## Quick Start

```bash
# Play
music-cli play                    # Context-aware radio
music-cli play --mood focus       # Focus music
music-cli play -m local --auto    # Shuffle local library
music-cli play -m youtube -s "https://youtube.com/watch?v=..."  # YouTube audio
music-cli play -m yt -s "https://youtu.be/..."  # YouTube (short alias)
```

## Commands

| Command | Description |
|---------|-------------|
| `play` | Start playing (radio/local/ai/history/youtube) |
| `stop` / `pause` / `resume` | Playback control |
| `status` | Current track, state, and inspirational quote |
| `next` | Skip track (auto-play mode) |
| `volume [0-100]` | Get/set volume |
| `radios` | Manage radio stations (list/play/add/remove) |
| `youtube` | Manage cached YouTube tracks (list/play/remove/clear) |
| `ai` | Manage AI-generated tracks (list/play/replay/remove) |
| `history` | Playback log |
| `moods` | Available mood tags |
| `config` | Show configuration file locations |
| `update-radios` | Update stations after version upgrade |
| `daemon start\|stop\|status` | Daemon control |

## Radio Station Management

```bash
# List all stations with numbers
music-cli radios
music-cli radios list

# Play by station number
music-cli radios play 5

# Add a new station interactively
music-cli radios add

# Remove a station
music-cli radios remove 10
```

### Pre-configured Stations

40 stations across multiple genres and languages:

- **Chill/Lo-fi**: ChillHop, SomaFM (Groove Salad, Drone Zone, Space Station)
- **Electronic**: Deep House, DEF CON Radio, Beat Blender
- **Synthwave**: Nightride FM, Chillsynth FM, Darksynth FM, Datawave FM, Spacesynth FM
- **French**: FIP Radio, France Inter, France Musique, Mouv
- **Spanish**: Salsa Radio, Tropical 100, Los 40 Principales, Cadena SER
- **Italian**: Radio Italia, RTL 102.5, Radio 105, Virgin Radio Italy

## Play Modes

```bash
# Radio (default)
music-cli play                     # Time-based selection
music-cli play -s "deep house"     # By station name
music-cli play --mood focus        # By mood

# Local
music-cli play -m local -s song.mp3
music-cli play -m local --auto     # Shuffle

# AI (requires [ai] extras)
music-cli play -m ai --mood happy -d 60

# History
music-cli play -m history -i 3     # Replay item #3
```

## AI Music Generation

Generate unique audio with multiple AI models via HuggingFace:

```bash
# Install AI dependencies (~5GB: PyTorch + Transformers + Diffusers)
pip install 'coder-music-cli[ai]'

# Generate and manage AI music
music-cli ai play                              # Context-aware (default: musicgen-small)
music-cli ai play -p "jazz piano"              # Custom prompt
music-cli ai play -m audioldm-s-full-v2        # Use AudioLDM model
music-cli ai play -m bark-small -p "Hello!"    # Use Bark for speech
music-cli ai play --mood focus -d 30           # 30-second focus track
music-cli ai models                            # List available models
music-cli ai list                              # List all generated tracks
music-cli ai replay 1                          # Replay track #1
music-cli ai remove 2                          # Delete track #2
```

### Available AI Models

| Model ID | Type | Best For | Size |
|----------|------|----------|------|
| `musicgen-small` | MusicGen | Music generation (default) | ~1.5GB |
| `musicgen-medium` | MusicGen | Higher quality music | ~3GB |
| `musicgen-large` | MusicGen | Best quality music | ~6GB |
| `musicgen-melody` | MusicGen | Melody-conditioned music | ~3GB |
| `audioldm-s-full-v2` | AudioLDM | Sound effects, ambient audio | ~1GB |
| `audioldm-l-full` | AudioLDM | High-quality audio generation | ~2GB |
| `bark` | Bark | Speech synthesis, audio with voice | ~5GB |
| `bark-small` | Bark | Faster speech synthesis | ~1.5GB |

### AI Command Suite

| Command | Description |
|---------|-------------|
| `ai models` | List all available AI models |
| `ai list` | Show all AI-generated tracks with prompts |
| `ai play` | Generate music from current context |
| `ai play -m <model>` | Generate with specific model |
| `ai play -p "prompt"` | Generate with custom prompt |
| `ai play --mood focus` | Generate with specific mood |
| `ai play -d 30` | Generate 30-second track (default: 5s) |
| `ai replay <num>` | Replay track by number (regenerates if file missing) |
| `ai remove <num>` | Delete track and audio file |

### Features
- **Multiple models** - MusicGen, AudioLDM, and Bark model families
- **Smart caching** - LRU cache keeps up to 2 models in memory (configurable)
- **Download progress** - Progress bar shown during model downloads
- **GPU memory management** - Automatic cleanup when switching models
- **Context-aware** - Uses time of day, day of week, and session mood
- **Custom prompts** - Generate exactly what you want with `-p`
- **Seamless looping** - All tracks engineered for infinite playback
- **Track management** - List, replay, and remove generated tracks
- **Regeneration** - Missing files can be regenerated with original prompt
- **Animated feedback** - "composing..." animation while generating
- **Persistent storage** - Tracks saved to config directory

### Requirements
- ~5GB disk space minimum (PyTorch + Transformers + Diffusers)
- ~8GB RAM minimum for generation (16GB recommended for larger models)
- Models are downloaded on first use

### Configuration

Configure AI settings in `~/.config/music-cli/config.toml`:

```toml
[ai]
default_model = "musicgen-small"  # Default model for generation

[ai.cache]
max_models = 2  # Max models to keep in memory (LRU eviction)

[ai.models.audioldm-s-full-v2.extra_params]
num_inference_steps = 10  # More = better quality, slower
guidance_scale = 2.5      # How closely to follow prompt
```

## YouTube Offline Cache

YouTube audio is automatically cached for offline playback. When you play a YouTube URL, the audio is downloaded in the background and stored locally.

```bash
# Play YouTube audio (automatically cached)
music-cli play -m youtube -s "https://youtube.com/watch?v=..."

# Manage cached tracks
music-cli youtube                    # List all cached tracks
music-cli youtube cached             # Same as above
music-cli youtube play 3             # Play cached track #3 (works offline)
music-cli youtube remove 1           # Remove cached track #1
music-cli youtube clear              # Clear entire cache
```

### YouTube Command Suite

| Command | Description |
|---------|-------------|
| `youtube` | List all cached tracks (default) |
| `youtube cached` | List cached tracks with cache statistics |
| `youtube play <num>` | Play cached track by number (offline) |
| `youtube remove <num>` | Remove a cached track |
| `youtube clear` | Clear all cached tracks |

### Features
- **Automatic caching** - Audio cached in background while streaming
- **Offline playback** - Play cached tracks without internet
- **LRU eviction** - 2GB cache limit with automatic cleanup of oldest tracks
- **M4A format** - 192kbps quality for good balance of size and quality
- **Instant replay** - Cached tracks play immediately

### Configuration

Configure YouTube cache in `~/.config/music-cli/config.toml`:

```toml
[youtube.cache]
enabled = true          # Enable/disable automatic caching
max_size_gb = 2.0       # Maximum cache size in GB
```

### Cache Location

Cached files are stored in:
- **Linux/macOS**: `~/.config/music-cli/youtube_cache/`
- **Windows**: `%LOCALAPPDATA%\music-cli\youtube_cache\`

## Moods

`focus` `happy` `sad` `excited` `relaxed` `energetic` `melancholic` `peaceful`

## Configuration

Configuration files location:
- **Linux/macOS**: `~/.config/music-cli/`
- **Windows**: `%LOCALAPPDATA%\music-cli\`

| File | Purpose |
|------|---------|
| `config.toml` | Settings (volume, mood mappings, version) |
| `radios.txt` | Station URLs (name\|url format) |
| `history.jsonl` | Play history |
| `ai_tracks.json` | AI track metadata (prompts, durations) |
| `ai_music/` | AI-generated audio files |
| `youtube_cache.json` | YouTube cache metadata |
| `youtube_cache/` | Cached YouTube audio files |

### Version Updates

When you update music-cli, you'll be notified if new radio stations are available:

```bash
# Check and update stations
music-cli update-radios

# Options:
# [M] Merge   - Add new stations to your list (recommended)
# [O] Overwrite - Replace with new defaults (backs up old file)
# [K] Keep    - Keep your current stations unchanged
```

### Add Custom Stations

```bash
# Interactive
music-cli radios add

# Or edit directly: ~/.config/music-cli/radios.txt
ChillHop|https://streams.example.com/chillhop.mp3
Jazz FM|https://streams.example.com/jazz.mp3
```

## Status & Quotes

The `status` command shows playback info plus a random inspirational quote:

```bash
$ music-cli status
Status: ▶ playing
Track: Groove Salad [radio]
Volume: 80%
Context: morning / weekday

"Music gives a soul to the universe, wings to the mind, flight to the imagination." - Plato

Version: 0.3.0
GitHub: https://github.com/luongnv89/music-cli
```

## Documentation

| Document | Description |
|----------|-------------|
| [User Guide](docs/user-guide.md) | Complete usage instructions |
| [AI Playbook](docs/AI_PLAYBOOK.md) | AI music generation guide with examples |
| [Architecture](docs/architecture.md) | System design and diagrams |
| [Development](docs/development.md) | Contributing guide |

## Requirements

- Python 3.10+
- FFmpeg
- **Supported Platforms**: Linux, macOS, Windows 10+

## Changelog

### v0.8.9
- Add acknowledgements section to README listing open-source dependencies
- Fix ruff linting errors (use TimeoutError, import Callable from collections.abc)
- Update Python requirement to 3.10+ in CI and documentation

### v0.8.7
- Improve YouTube livestream playback for radio stations:
  - Pipe yt-dlp directly to ffplay for reliable HLS buffering and reconnections
  - Eliminates intermittent dropouts on YouTube livestreams
  - Falls back to direct URL playback on Windows
- Add Anjunadeep Radio as example YouTube radio station
- Add contributors section to README

### v0.8.6
- Auto-detect terminal width for radio list columns (1-6 columns based on terminal size)

### v0.8.5
- Change radio list to 4-column layout for more compact display

### v0.8.4
- Improve radio station list display:
  - Show stations in categorized format grouped by genre/language
  - Categories extracted from radios.txt comment structure

### v0.8.3
- Add 5 new Nightride FM synthwave radio stations (320kbps):
  - Nightride FM (Synthwave/Retrowave/Outrun)
  - Chillsynth FM (Chillsynth/Chillwave)
  - Darksynth FM (Darksynth/Cyberpunk)
  - Datawave FM (Glitchy Synthwave/IDM)
  - Spacesynth FM (Spacesynth/Space Disco)

### v0.8.2
- Fix missing mood radio mappings: all 8 moods now have working radio streams
  - Added streams for: relaxed (Groove Salad), energetic (DEF CON Radio), melancholic (Indie Pop Rocks), peaceful (Drone Zone)
  - Fixed fallback to default config when user config lacks mood mappings

### v0.8.1
- Fix cached YouTube tracks not playing: reconnect options were incorrectly applied to local cached files instead of only remote streams

### v0.8.0
- Add YouTube offline cache for automatic offline playback:
  - Automatically cache YouTube audio when played
  - Play cached tracks offline with `music-cli youtube play <num>`
  - Manage cache with `music-cli youtube` commands (list/play/remove/clear)
  - 2GB LRU cache with automatic eviction of oldest tracks
  - M4A format at 192kbps quality
  - Thread-safe cache operations
- Add `youtube` command group for cache management

### v0.7.0
- Add YouTube audio streaming support:
  - Stream audio directly from YouTube URLs without downloading
  - Support for youtube.com, youtu.be, YouTube Shorts, and YouTube Music URLs
  - Install with: `pip install 'coder-music-cli[youtube]'`
  - Play with: `music-cli play -m youtube -s "https://youtube.com/watch?v=..."`
  - Short alias: `music-cli play -m yt -s "https://youtu.be/..."`
- Fix version sync between pyproject.toml and __init__.py

### v0.6.0
- Add AI model management commands:
  - `music-cli ai models download <model>` - Download models before use
  - `music-cli ai models delete <model>` - Delete cached models to free space
  - `music-cli ai models set-default <model>` - Set default generation model
- Add model descriptions and expected sizes to `ai models` output
- Add download status tracking via HuggingFace cache inspection
- Add comprehensive AI Playbook documentation with examples
- Improve config fallback to DEFAULT_CONFIG when user config is missing AI settings

### v0.5.0
- Add multiple AI model support:
  - **AudioLDM models**: `audioldm-s-full-v2`, `audioldm-l-full` for sound effects and ambient audio
  - **Bark models**: `bark`, `bark-small` for speech synthesis
  - **MusicGen models**: All existing models continue to work
- Add `ai models` command to list all available AI models
- Add LRU cache for AI models with configurable size (default: 2 models)
- Add download progress bar during model downloads
- Add GPU memory management with automatic cleanup on model eviction
- Default model: `musicgen-small`

### v0.4.1
- Add Windows 10+ support
  - Platform abstraction layer for cross-platform compatibility
  - TCP localhost IPC on Windows (Unix sockets on Linux/macOS)
  - stdin-based pause/resume on Windows (signals on Linux/macOS)
  - Windows-specific config directory (`%LOCALAPPDATA%\music-cli\`)
- Add Windows to CI test matrix

### v0.4.0
- Add `music-cli ai` command suite for AI track management
  - `ai list` - Display all AI tracks with prompts
  - `ai play [-p "prompt"]` - Generate with context or custom prompt
  - `ai replay <num>` - Replay track (regenerates if missing)
  - `ai remove <num>` - Delete track and audio file
- Add seamless looping via prompt engineering
- Add context-aware AI generation (time of day, day of week, mood)
- Default AI duration reduced to 5s for faster generation

### v0.3.0
- Add radio station management (list/play/add/remove by number)
- Add 35 curated radio stations (English, French, Spanish, Italian)
- Add version-aware config with `update-radios` command
- Add inspirational quotes to status command
- Add "composing..." animation for AI generation
- Save AI-generated music to persistent directory for replay
- Show GitHub link in status output
- Remove audiocraft dependency (use transformers only)

### v0.2.0
- Switch to HuggingFace Transformers for AI music generation
- Auto-loop AI-generated tracks
- Pin transformers<4.51 for MusicGen compatibility
- CI/CD improvements

### v0.1.0
- Initial release
- Daemon-based playback
- Radio streaming, local files, AI generation
- Context-aware music selection
- Mood support

## Contributors

Thanks to all contributors who have helped improve music-cli!

| Contributor | PR | Contribution |
|-------------|-----|--------------|
| [kylephillipsau](https://github.com/kylephillipsau) | [#5](https://github.com/luongnv89/music-cli/pull/5) | Improved YouTube livestream playback for radio stations by piping yt-dlp to ffplay for reliable HLS buffering and reconnections |

## Acknowledgements

music-cli is built with these excellent open-source libraries:

| Library | Maintainer | Purpose |
|---------|------------|---------|
| [Click](https://github.com/pallets/click) | [Pallets](https://github.com/pallets) | CLI framework for building commands and argument parsing |
| [tomli](https://github.com/hukkin/tomli) | [hukkin](https://github.com/hukkin) | TOML parser for reading configuration files |
| [tomli-w](https://github.com/hukkin/tomli-w) | [hukkin](https://github.com/hukkin) | TOML writer for saving configuration files |
| [pyobjc](https://github.com/ronaldoussoren/pyobjc) | [Ronald Oussoren](https://github.com/ronaldoussoren) | macOS framework bindings for media key support |
| [dbus-next](https://github.com/altdesktop/python-dbus-next) | [altdesktop](https://github.com/altdesktop) | D-Bus client for Linux MPRIS media controls |
| [PyTorch](https://github.com/pytorch/pytorch) | [PyTorch Team](https://github.com/pytorch) | Deep learning framework powering AI music generation |
| [Transformers](https://github.com/huggingface/transformers) | [Hugging Face](https://github.com/huggingface) | Pre-trained models for MusicGen and Bark |
| [Diffusers](https://github.com/huggingface/diffusers) | [Hugging Face](https://github.com/huggingface) | Diffusion models for AudioLDM audio generation |
| [SciPy](https://github.com/scipy/scipy) | [SciPy Community](https://github.com/scipy) | Scientific computing for audio signal processing |
| [tqdm](https://github.com/tqdm/tqdm) | [tqdm developers](https://github.com/tqdm) | Progress bars for model downloads and generation |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | [yt-dlp Team](https://github.com/yt-dlp) | YouTube audio extraction and streaming |

## License

MIT
