# music-cli

[![PyPI version](https://img.shields.io/pypi/v/coder-music-cli.svg)](https://pypi.org/project/coder-music-cli/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

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
brew install ffmpeg      # macOS
sudo apt install ffmpeg  # Ubuntu/Debian
```

### Optional: AI Music Generation

```bash
pip install 'coder-music-cli[ai]'  # ~5GB (PyTorch + MusicGen via Transformers)
```

## Features

- **Daemon-based** - Persistent background playback
- **Multiple sources** - Local files, radio streams, AI generation
- **Context-aware** - Selects music based on time of day and mood
- **35+ Radio Stations** - Curated stations in English, French, Spanish, and Italian
- **AI Music Generation** - Generate music with MusicGen (saved for replay)
- **Version-aware Updates** - Automatic notification when new stations are available
- **Inspirational Quotes** - Random music quotes with every status check
- **Simple config** - Human-readable text files

## Quick Start

```bash
# Play
music-cli play                    # Context-aware radio
music-cli play --mood focus       # Focus music
music-cli play -m local --auto    # Shuffle local library

# Control
music-cli pause | resume | stop | status

# Manage radio stations
music-cli radios                  # List all stations
music-cli radios play 5           # Play station #5
music-cli radios add              # Add new station
```

## Commands

| Command | Description |
|---------|-------------|
| `play` | Start playing (radio/local/ai/history) |
| `stop` / `pause` / `resume` | Playback control |
| `status` | Current track, state, and inspirational quote |
| `next` | Skip track (auto-play mode) |
| `volume [0-100]` | Get/set volume |
| `radios` | Manage radio stations (list/play/add/remove) |
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

35 stations across 4 languages:

- **English**: ChillHop, SomaFM (Groove Salad, Drone Zone, DEF CON, etc.), BBC Radio 3
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

Generate unique music with Meta's MusicGen model:

```bash
# Install AI dependencies
pip install 'coder-music-cli[ai]'

# Generate music
music-cli play -m ai --mood focus -d 30   # 30-second focus track
music-cli play -m ai --mood energetic     # Energetic music
```

Features:
- **Animated feedback** - "composing..." animation while generating
- **Persistent storage** - Generated tracks saved to `~/.config/music-cli/ai_music/`
- **Replay support** - AI tracks appear in history for replay
- **Auto-loop** - Generated tracks loop automatically

## Moods

`focus` `happy` `sad` `excited` `relaxed` `energetic` `melancholic` `peaceful`

## Configuration

Files in `~/.config/music-cli/`:

| File | Purpose |
|------|---------|
| `config.toml` | Settings (volume, mood mappings, version) |
| `radios.txt` | Station URLs (name\|url format) |
| `history.jsonl` | Play history |
| `ai_music/` | AI-generated tracks |

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
| [Architecture](docs/architecture.md) | System design and diagrams |
| [Development](docs/development.md) | Contributing guide |

## Requirements

- Python 3.9+
- FFmpeg

## Changelog

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

## License

MIT
