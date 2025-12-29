# music-cli

A command-line music application for coders. Play local MP3s, stream radio, or generate AI music based on your mood and the time of day.

## Features

- **Background Daemon**: Runs as a background process, controlled via simple commands
- **Multiple Playback Modes**:
  - Local MP3 files with shuffle/auto-play
  - Radio streaming from configurable stations
  - AI-generated music (optional, via MusicGen)
  - Context-aware playback based on time of day and mood
- **History Tracking**: View and replay tracks from your history
- **Human-readable Config**: All settings stored in simple text files

## Requirements

- Python 3.9+
- FFmpeg (for `ffplay`)

## Installation

```bash
# Install from source
cd music-cli
pip install -e .

# Or with AI music generation support (~5GB download)
pip install -e ".[ai]"
```

### Install FFmpeg

**macOS**:
```bash
brew install ffmpeg
```

**Ubuntu/Debian**:
```bash
sudo apt install ffmpeg
```

## Quick Start

```bash
# Play context-aware radio (based on time of day)
music-cli play

# Play with a specific mood
music-cli play --mood focus

# Play a local file
music-cli play -m local -s ~/Music/song.mp3

# Play a radio station by name
music-cli play -m radio -s "chill"

# Shuffle local music library
music-cli play -m local --auto

# Control playback
music-cli pause
music-cli resume
music-cli stop

# Check status
music-cli status

# View history
music-cli history

# Replay from history
music-cli play -m history -i 3
```

## Commands

| Command | Description |
|---------|-------------|
| `play` | Start playing music |
| `stop` | Stop playback |
| `pause` | Pause playback |
| `resume` | Resume playback |
| `status` | Show current status |
| `next` | Skip to next track (auto-play mode) |
| `volume [0-100]` | Get/set volume |
| `radios` | List available radio stations |
| `history` | Show playback history |
| `moods` | List available mood tags |
| `daemon [start\|stop\|status]` | Control the daemon |
| `config` | Show config file locations |

## Play Modes

### Radio Mode (default)
```bash
music-cli play                    # Context-aware radio
music-cli play -s "deep house"    # Play station by name
music-cli play --mood focus       # Play mood-appropriate station
```

### Local Mode
```bash
music-cli play -m local -s song.mp3   # Play specific file
music-cli play -m local --auto        # Shuffle local library
```

### AI Mode (requires `[ai]` extras)
```bash
music-cli play -m ai                      # Generate based on context
music-cli play -m ai --mood happy         # Generate happy music
music-cli play -m ai --mood focus -d 60   # 60-second focus track
```

### History Mode
```bash
music-cli history              # View recent plays
music-cli play -m history -i 5 # Replay item #5
```

## Mood Tags

- `happy` - Upbeat, cheerful music
- `sad` - Melancholic, emotional music
- `excited` - High-energy, fast tempo
- `focus` - Lo-fi, ambient for concentration
- `relaxed` - Chill, smooth jazz
- `energetic` - Powerful, driving beats

## Configuration

All config files are in `~/.config/music-cli/`:

| File | Description |
|------|-------------|
| `config.toml` | Main settings |
| `radios.txt` | Radio station URLs |
| `history.jsonl` | Playback history |

### Adding Radio Stations

Edit `~/.config/music-cli/radios.txt`:

```
# Format: name|url or just url
ChillHop|https://streams.example.com/chillhop.mp3
Jazz FM|https://streams.example.com/jazz.mp3
https://raw-stream-url.example.com/stream
```

### Configuration Options

Edit `~/.config/music-cli/config.toml`:

```toml
[player]
backend = "ffplay"
volume = 80

[mood_radio_map]
focus = "https://streams.example.com/focus.mp3"
happy = "https://streams.example.com/happy.mp3"

[time_radio_map]
morning = "https://streams.example.com/morning.mp3"
evening = "https://streams.example.com/evening.mp3"
```

## AI Music Generation

AI music requires additional dependencies (~5GB):

```bash
pip install 'music-cli[ai]'
```

The first AI generation will download the MusicGen model (~3GB).

```bash
# Generate context-aware music
music-cli play -m ai

# Generate with specific mood
music-cli play -m ai --mood focus

# Longer generation (up to 300 seconds)
music-cli play -m ai -d 120
```

## Daemon Management

The daemon starts automatically when you run any command. To manage it manually:

```bash
music-cli daemon status   # Check if running
music-cli daemon start    # Start daemon
music-cli daemon stop     # Stop daemon
music-cli daemon restart  # Restart daemon
```

## License

MIT
