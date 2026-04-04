# User Guide

Complete guide to using music-cli (`mc`) for background music while coding.

## Quick Start

```bash
# Install from PyPI
pip install coder-music-cli

# Play context-aware radio (based on time of day)
mc play

# Control playback
mc pause
mc resume
mc stop
```

## Installation

### Requirements
- Python 3.10+
- FFmpeg
- **Supported Platforms**: Linux, macOS, Windows 10+

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

**Windows:**
```bash
choco install ffmpeg
# or
winget install ffmpeg
# or
scoop install ffmpeg
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
| `mc play` | Start playing (context-aware) |
| `mc stop` | Stop playback |
| `mc pause` | Pause playback |
| `mc resume` | Resume playback |
| `mc next` | Skip to next track (auto-play mode) |
| `mc status` | Show current status + inspirational quote |
| `mc vol` | Show current volume |
| `mc vol <0-100>` | Set volume |

### Radio Stations

| Command | Description |
|---------|-------------|
| `mc radio` | List all radio stations |
| `mc radio list` | List all radio stations |
| `mc radio play <num>` | Play station by number |
| `mc radio add` | Add a new station interactively |
| `mc radio remove <num>` | Remove a station by number |
| `mc radio update` | Update stations after version upgrade |

### AI Music

| Command | Description |
|---------|-------------|
| `mc ai` | List all AI-generated tracks |
| `mc ai list` | List all AI-generated tracks |
| `mc ai play` | Generate and play AI music |
| `mc ai play -p "prompt"` | Generate with custom prompt |
| `mc ai replay <num>` | Replay a track by number |
| `mc ai remove <num>` | Remove a track |
| `mc ai model` | List available AI models |

### YouTube Cache

| Command | Description |
|---------|-------------|
| `mc yt` | List cached YouTube tracks |
| `mc yt list` | List cached YouTube tracks |
| `mc yt play <num>` | Play cached track by number (offline) |
| `mc yt remove <num>` | Remove a cached track |
| `mc yt clear` | Clear entire YouTube cache |

### History

| Command | Description |
|---------|-------------|
| `mc history` | Show recent playback history |
| `mc history list` | Show recent playback history |
| `mc history list -n 5` | Show last 5 entries |
| `mc history play <num>` | Replay an item by number |

### Moods

| Command | Description |
|---------|-------------|
| `mc mood` | List available moods |
| `mc mood <name>` | Start mood-based radio |

### Daemon Control

| Command | Description |
|---------|-------------|
| `mc daemon status` | Check daemon status |
| `mc daemon start` | Start daemon |
| `mc daemon stop` | Stop daemon |
| `mc daemon restart` | Restart daemon |

### Other

| Command | Description |
|---------|-------------|
| `mc config` | Show config file locations |
| `mc --version` | Show installed version |

## Playback Modes

### Smart Play (auto-detection)

`mc play` auto-detects the source type from the argument:

```bash
mc play                              # Context-aware radio (time of day)
mc play ~/song.mp3                   # Auto-detect: local file
mc play "https://youtube.com/..."    # Auto-detect: YouTube URL
mc play "https://some-stream.mp3"   # Auto-detect: radio stream URL
mc play "deep house"                 # Auto-detect: station name
```

### Mood-Based

```bash
mc play -M focus        # Radio matching the focus mood
mc mood focus           # Same — shortcut for mood radio
```

### Local Mode

```bash
# Specific file
mc play ~/Music/song.mp3

# Shuffle with auto-play
mc play -m local --auto
```

### AI Mode

```bash
# Context-aware generation (default: musicgen-small)
mc ai play

# With mood
mc ai play -M focus

# Custom prompt and duration
mc ai play -p "upbeat jazz piano" -d 60
```

For the full AI command suite, see [AI Music Generation](#ai-music-generation) or the comprehensive [AI Playbook](AI_PLAYBOOK.md).

### YouTube Streaming

```bash
# Stream and auto-cache
mc play "https://youtube.com/watch?v=xxx"

# Play from cache (offline)
mc yt play 3
```

### History Mode

```bash
# View history
mc history

# Replay by number
mc history play 3

# Also: replay via play command
mc play -m history -i 3
```

## Moods

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
mc mood focus
mc play -M focus
mc ai play -M energetic
```

## Configuration

All config files are stored in a platform-specific directory:

- **Linux/macOS**: `~/.config/music-cli/`
- **Windows**: `%LOCALAPPDATA%\music-cli\`

Show paths:

```bash
mc config
```

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

[ai]
default_model = "musicgen-small"

[ai.cache]
max_models = 2  # Max models to keep in memory (LRU eviction)

# Optional: customize model parameters
[ai.models.audioldm-s-full-v2.extra_params]
num_inference_steps = 10
guidance_scale = 2.5

[youtube.cache]
enabled = true
max_size_gb = 2.0
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

### Files Summary

| File | Purpose |
|------|---------|
| `config.toml` | Settings (volume, mood mappings, version) |
| `radios.txt` | Station URLs (`name\|url` format) |
| `history.jsonl` | Playback history |
| `ai_tracks.json` | AI track metadata (prompts, durations) |
| `ai_music/` | AI-generated audio files |
| `youtube_cache.json` | YouTube cache metadata |
| `youtube_cache/` | Cached YouTube audio files |

## Workflows

### Focus Session

```bash
mc play -M focus    # Start focus radio
mc status           # What's playing
mc pause            # Pause for a meeting
mc resume           # Back to work
mc stop             # End session
```

### Background Shuffle

```bash
mc play -m local --auto   # Shuffle local library
mc next                    # Skip a track
mc history                 # Review what played
```

### AI Music Generation

```bash
# Install AI dependencies (~5GB: PyTorch + Transformers + Diffusers)
pip install 'coder-music-cli[ai]'

# Generate and manage AI music
mc ai play                              # Context-aware (default: musicgen-small)
mc ai play -p "jazz piano"              # Custom prompt
mc ai play -m audioldm-s-full-v2        # Use AudioLDM model
mc ai play -m bark-small -p "Hello!"    # Use Bark for speech
mc ai play -M focus -d 30              # 30-second focus track
mc ai model                             # List available models
mc ai list                              # List all generated tracks
mc ai replay 1                          # Replay track #1
mc ai remove 2                          # Delete track #2
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

For detailed prompt writing tips and recipes, see the [AI Playbook](AI_PLAYBOOK.md).

### Version Updates

When you update music-cli, you'll be notified if new radio stations are available:

```bash
mc radio update

# Options:
# [M] Merge     - Add new stations to your list (recommended)
# [O] Overwrite - Replace with new defaults (backs up old file)
# [K] Keep      - Keep your current stations unchanged
```

## Troubleshooting

### Daemon Issues

```bash
mc daemon status    # Check if running
mc daemon restart   # Restart if stuck

# Manual cleanup (Linux/macOS)
rm ~/.config/music-cli/music-cli.sock
rm ~/.config/music-cli/music-cli.pid

# Manual cleanup (Windows - PowerShell)
Remove-Item "$env:LOCALAPPDATA\music-cli\music-cli.pid"
```

### No Sound

1. Check FFmpeg is installed: `which ffplay` (Linux/macOS) or `where ffplay` (Windows)
2. Test manually: `ffplay -nodisp -autoexit /path/to/file.mp3`
3. Check volume: `mc vol`

### Radio Not Playing

1. Check URL accessibility: `curl -I <stream-url>`
2. Try a different station: `mc radio`
3. Check your network connection

### AI Mode Not Working

```bash
# Check if AI dependencies are installed
python -c "import transformers; import torch; print('AI ready!')"

# Install if missing
pip install 'coder-music-cli[ai]'

# Check available models
mc ai model
```

**Memory requirements:**
- Minimum 8GB RAM for smaller models
- 16GB recommended for larger models (`musicgen-large`, `bark`)
- LRU cache limits in-memory usage (default: 2 models)

## Tips

- **Autostart**: Add `mc daemon start` to your shell profile
- **Aliases**: `alias mplay='mc play'`
- **Focus**: `mc play -M focus` is the fastest way into a coding session
- **History grep**: `grep focus ~/.config/music-cli/history.jsonl`
- **Suppress color**: `mc --no-color status` or set `NO_COLOR=1`
