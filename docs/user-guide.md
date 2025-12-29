# User Guide

Complete guide to using music-cli for background music while coding.

## Quick Start

```bash
# Install from PyPI
pip install coder-music-cli

# Play context-aware radio (based on time of day)
music-cli play

# Control playback
music-cli pause
music-cli resume
music-cli stop
```

## Installation

### Requirements
- Python 3.9+
- FFmpeg

### Install FFmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt install ffmpeg
```

**Arch Linux:**
```bash
sudo pacman -S ffmpeg
```

### Install music-cli

```bash
# From PyPI
pip install coder-music-cli

# Or with uv (faster)
uv pip install coder-music-cli

# From source
git clone https://github.com/luongnv89/music-cli
cd music-cli
pip install -e .

# With AI support (~5GB download)
pip install 'coder-music-cli[ai]'
```

## Commands Reference

### Playback Control

| Command | Description |
|---------|-------------|
| `music-cli play` | Start playing (context-aware) |
| `music-cli stop` | Stop playback |
| `music-cli pause` | Pause playback |
| `music-cli resume` | Resume playback |
| `music-cli next` | Skip to next (auto-play mode) |
| `music-cli status` | Show current status |
| `music-cli volume [0-100]` | Get/set volume |

### Information

| Command | Description |
|---------|-------------|
| `music-cli radios` | List radio stations |
| `music-cli history` | Show playback history |
| `music-cli moods` | List available moods |
| `music-cli config` | Show config file paths |

### Daemon Control

| Command | Description |
|---------|-------------|
| `music-cli daemon status` | Check daemon status |
| `music-cli daemon start` | Start daemon |
| `music-cli daemon stop` | Stop daemon |
| `music-cli daemon restart` | Restart daemon |

## Playback Modes

### Radio Mode (Default)

Stream from configured radio stations:

```bash
# Context-aware (time-based)
music-cli play

# Specific station by name
music-cli play -s "ChillHop"
music-cli play -s "deep house"

# With mood
music-cli play --mood focus
```

### Local Mode

Play local MP3 files:

```bash
# Specific file
music-cli play -m local -s ~/Music/song.mp3

# Random from library
music-cli play -m local

# Shuffle mode (continuous)
music-cli play -m local --auto
```

### AI Mode

Generate music with MusicGen (requires `[ai]` extras):

```bash
# Context-aware generation
music-cli play -m ai

# With mood
music-cli play -m ai --mood happy

# Custom duration (seconds)
music-cli play -m ai --mood focus -d 60
```

### History Mode

Replay from history:

```bash
# View history
music-cli history

# Replay by index
music-cli play -m history -i 3
```

## Moods

Use moods for context-aware music selection:

| Mood | Description |
|------|-------------|
| `focus` | Lo-fi, ambient for concentration |
| `happy` | Upbeat, cheerful |
| `sad` | Melancholic, emotional |
| `excited` | High-energy, fast tempo |
| `relaxed` | Chill, smooth |
| `energetic` | Powerful, driving beats |
| `melancholic` | Bittersweet, nostalgic |
| `peaceful` | Serene, calm |

```bash
music-cli play --mood focus
music-cli play -m ai --mood energetic
```

## Configuration

All config files are in `~/.config/music-cli/`:

### config.toml

Main settings file:

```toml
[player]
backend = "ffplay"
volume = 80

[context]
enabled = true
use_ai = false

[mood_radio_map]
focus = "https://streams.example.com/focus.mp3"
happy = "https://streams.example.com/happy.mp3"
sad = "https://streams.example.com/sad.mp3"
excited = "https://streams.example.com/excited.mp3"

[time_radio_map]
morning = "https://streams.example.com/morning.mp3"
afternoon = "https://streams.example.com/afternoon.mp3"
evening = "https://streams.example.com/evening.mp3"
night = "https://streams.example.com/night.mp3"
```

### radios.txt

Radio stations (one per line):

```
# Format: name|url or just url
ChillHop|https://streams.ilovemusic.de/iloveradio17.mp3
Deep House|https://streams.ilovemusic.de/iloveradio14.mp3
Top Hits|https://streams.ilovemusic.de/iloveradio1.mp3

# Raw URL (name = URL)
https://some-stream.example.com/stream.mp3
```

### history.jsonl

Playback history (JSON lines):

```json
{"timestamp":"2024-01-15T09:30:00","source":"https://...","source_type":"radio","title":"Focus Radio","mood":"focus","context":"morning"}
{"timestamp":"2024-01-15T14:00:00","source":"/path/to/song.mp3","source_type":"local","title":"song","context":"afternoon"}
```

## Workflows

### Focus Session

```bash
# Start focus music
music-cli play --mood focus

# Check what's playing
music-cli status

# Pause for meeting
music-cli pause

# Resume after
music-cli resume

# End session
music-cli stop
```

### Background Shuffle

```bash
# Start shuffling local library
music-cli play -m local --auto

# Skip boring track
music-cli next

# Check history
music-cli history
```

### AI Music Generation

```bash
# Install AI dependencies
pip install 'music-cli[ai]'

# Generate 2-minute focus track
music-cli play -m ai --mood focus -d 120

# First run downloads model (~3GB)
```

## Troubleshooting

### Daemon Issues

```bash
# Check if running
music-cli daemon status

# Restart if stuck
music-cli daemon restart

# Manual cleanup
rm ~/.config/music-cli/music-cli.sock
rm ~/.config/music-cli/music-cli.pid
```

### No Sound

1. Check FFmpeg: `which ffplay`
2. Test manually: `ffplay -nodisp -autoexit /path/to/file.mp3`
3. Check volume: `music-cli volume`

### Radio Not Playing

1. Check URL accessibility: `curl -I <stream-url>`
2. Try different station: `music-cli radios`
3. Check network connection

### AI Mode Not Working

```bash
# Check if installed
python -c "import audiocraft" 2>&1

# Install if missing
pip install 'music-cli[ai]'

# First run downloads model (~3GB)
```

## Tips

- **Autostart**: Add `music-cli daemon start` to shell profile
- **Aliases**: `alias mplay='music-cli play'`
- **Focus**: Use `--mood focus` for coding sessions
- **History grep**: `grep focus ~/.config/music-cli/history.jsonl`
