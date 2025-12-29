# music-cli

[![PyPI version](https://badge.fury.io/py/coder-music-cli.svg)](https://badge.fury.io/py/coder-music-cli)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A command-line music player for coders. Background daemon with radio streaming, local MP3s, and AI-generated music.

```bash
music-cli play --mood focus    # Start focus music
music-cli pause                # Pause for meeting
music-cli resume               # Back to coding
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
pip install 'coder-music-cli[ai]'  # ~5GB (PyTorch + MusicGen)
```

## Features

- **Daemon-based** - Persistent background playback
- **Multiple sources** - Local files, radio streams, AI generation
- **Context-aware** - Selects music based on time of day and mood
- **Simple config** - Human-readable text files

## Quick Start

```bash
# Play
music-cli play                    # Context-aware radio
music-cli play --mood focus       # Focus music
music-cli play -m local --auto    # Shuffle local library

# Control
music-cli pause | resume | stop | status
```

## Commands

| Command | Description |
|---------|-------------|
| `play` | Start playing (radio/local/ai/history) |
| `stop` / `pause` / `resume` | Playback control |
| `status` | Current track and state |
| `next` | Skip track (auto-play mode) |
| `volume [0-100]` | Get/set volume |
| `radios` | List stations |
| `history` | Playback log |
| `moods` | Available mood tags |
| `daemon start\|stop\|status` | Daemon control |

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

## Moods

`focus` `happy` `sad` `excited` `relaxed` `energetic` `melancholic` `peaceful`

## Configuration

Files in `~/.config/music-cli/`:

| File | Purpose |
|------|---------|
| `config.toml` | Settings |
| `radios.txt` | Station URLs |
| `history.jsonl` | Play history |

Add stations to `radios.txt`:
```
ChillHop|https://streams.example.com/chillhop.mp3
Jazz FM|https://streams.example.com/jazz.mp3
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

## License

MIT
