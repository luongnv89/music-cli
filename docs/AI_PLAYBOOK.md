# AI Music Generation Playbook

Complete guide to using `mc ai` commands for generating music, sounds, and speech.

## Table of Contents

- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [Model Selection Guide](#model-selection-guide)
- [Model Management](#model-management)
- [Generating Audio](#generating-audio)
- [Use Case Recipes](#use-case-recipes)
- [Track Management](#track-management)
- [Storage & Configuration](#storage--configuration)
- [Tips & Best Practices](#tips--best-practices)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

Generate your first AI track in 3 steps:

```bash
# 1. Install AI dependencies (~5GB: PyTorch + Transformers + Diffusers)
pip install 'coder-music-cli[ai]'

# 2. Generate music (downloads model on first run)
mc ai play -p "relaxing piano music"

# 3. View your generated tracks
mc ai list
```

That's it! The default model (`musicgen-small`) will be downloaded automatically on first use.

---

## Prerequisites

### Installation

```bash
# Install with AI support
pip install 'coder-music-cli[ai]'

# Or upgrade existing installation
pip install --upgrade 'coder-music-cli[ai]'
```

### System Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| Disk Space | ~5 GB | ~10 GB (for multiple models) |
| RAM | 8 GB | 16 GB |
| GPU | Not required | CUDA-compatible (faster generation) |

### Verify Installation

```bash
# Check if AI dependencies are installed
python -c "import transformers; import torch; print('AI ready!')"

# List available models
mc ai model
```

---

## Model Selection Guide

mc supports **9 AI models** across 3 families. Choose based on your use case:

### MusicGen Models (Music Generation)

Best for: **Background music, ambient tracks, genre-specific music**

| Model | Size | Duration | Best For |
|-------|------|----------|----------|
| `musicgen-small` | ~2 GB | 5-60s | Quick generation, good quality (default) |
| `musicgen-medium` | ~3.5 GB | 5-60s | Balanced quality and speed |
| `musicgen-large` | ~7 GB | 5-45s | Highest quality music |
| `musicgen-melody` | ~3.5 GB | 5-60s | Melody-conditioned generation |

**Example prompts:**
- "lo-fi hip hop beats for studying"
- "ambient electronic music with synth pads"
- "jazz piano trio with soft drums"
- "classical orchestral background music"

### AudioLDM Models (Sound Effects & Ambient Audio)

Best for: **Nature sounds, ambient soundscapes, sound effects**

| Model | Size | Duration | Best For |
|-------|------|----------|----------|
| `audioldm-s-full-v2` | ~1.5 GB | 2-30s | Sound effects (recommended) |
| `audioldm-m-full` | ~2 GB | 2-30s | Medium quality audio |
| `audioldm-l-full` | ~3 GB | 2-30s | High quality audio |

**Example prompts:**
- "gentle rain falling on a window"
- "coffee shop ambiance with chatter"
- "forest with birds singing and wind"
- "thunderstorm with heavy rain"
- "ocean waves on a beach"

### Bark Models (Speech Synthesis)

Best for: **Announcements, greetings, short narrations**

| Model | Size | Duration | Best For |
|-------|------|----------|----------|
| `bark` | ~5 GB | 2-15s | Best quality speech |
| `bark-small` | ~2 GB | 2-15s | Faster speech synthesis |

**Example prompts:**
- "Hello, welcome to your coding session"
- "Time for a break. Stand up and stretch."
- "Great job! You've been coding for an hour."

> **Note:** Bark has a token limit that restricts output to ~10-15 seconds maximum.

### Quick Selection Guide

| What You Need | Recommended Model |
|---------------|-------------------|
| Quick background music | `musicgen-small` |
| Best quality music | `musicgen-large` |
| Sound effects & ambiance | `audioldm-s-full-v2` |
| Quick speech | `bark-small` |
| Best speech quality | `bark` |

---

## Model Management

### View Available Models

```bash
# List all models with download status
mc ai model

# Same as above
mc ai model list
```

Output shows:
- Model name and type
- Download status (cached/not cached)
- Size on disk
- Duration limits

### Download Models

Models are downloaded automatically on first use, but you can pre-download them:

```bash
# Download a specific model
mc ai model download musicgen-medium

# Download multiple models
mc ai model download audioldm-s-full-v2
mc ai model download bark-small
```

### Delete Models

Free up disk space by removing unused models:

```bash
# Delete a specific model
mc ai model delete musicgen-large

# Check which models are cached
mc ai model
```

### Set Default Model

Change the default model for generation:

```bash
# Set a new default
mc ai model default musicgen-medium

# Verify
mc ai model
```

---

## Generating Audio

### Basic Generation

```bash
# Context-aware generation (uses time of day and mood)
mc ai play

# Generate with a custom prompt
mc ai play -p "jazz piano music"

# Specify duration (in seconds)
mc ai play -p "ambient music" -d 60

# Use a specific model
mc ai play -m musicgen-medium -p "electronic beats"

# Combine all options
mc ai play -m musicgen-large -p "orchestral epic music" -d 45
```

### Generation with Mood

```bash
# Available moods: focus, happy, sad, excited, relaxed, energetic, melancholic, peaceful
mc ai play --mood focus
mc ai play --mood relaxed -d 30
mc ai play --mood energetic -p "upbeat electronic"
```

### Generation Options Reference

| Option | Short | Description | Example |
|--------|-------|-------------|---------|
| `--prompt` | `-p` | Custom text prompt | `-p "jazz piano"` |
| `--duration` | `-d` | Duration in seconds | `-d 60` |
| `--model` | `-m` | Specific model to use | `-m musicgen-medium` |
| `--mood` | `-M` | Context mood | `-M focus` |

---

## Use Case Recipes

### Music for Coding

```bash
# Lo-fi beats for focus
mc ai play -p "lo-fi hip hop beats for studying" -d 60

# Ambient electronic
mc ai play -p "ambient electronic focus music" -m musicgen-medium

# Soft background jazz
mc ai play -p "soft piano jazz background music"

# Classical for concentration
mc ai play -p "calm classical piano music for concentration" -d 45

# Synthwave for energy
mc ai play -p "synthwave electronic with retro vibes" -m musicgen-large
```

### Sound Effects & Ambiance

```bash
# Rain sounds
mc ai play -m audioldm-s-full-v2 -p "gentle rain on window" -d 30

# Coffee shop
mc ai play -m audioldm-s-full-v2 -p "coffee shop ambiance with quiet chatter"

# Nature sounds
mc ai play -m audioldm-s-full-v2 -p "forest birds singing with gentle wind"

# Thunderstorm
mc ai play -m audioldm-s-full-v2 -p "thunderstorm with heavy rain"

# Ocean waves
mc ai play -m audioldm-s-full-v2 -p "calm ocean waves on sandy beach"

# Fireplace
mc ai play -m audioldm-s-full-v2 -p "crackling fireplace with wood burning"
```

### Speech Synthesis

```bash
# Welcome message
mc ai play -m bark-small -p "Hello! Welcome to your coding session."

# Break reminder
mc ai play -m bark -p "Time for a break. Stand up and stretch your legs."

# Motivational
mc ai play -m bark-small -p "Great progress! Keep up the good work."

# Session end
mc ai play -m bark -p "Session complete. Remember to save your work."
```

### Workflow Examples

#### Focus Session

```bash
# Start with focus music
mc ai play --mood focus -d 60

# Check what's playing
mc status

# Later, switch to rain sounds
mc ai play -m audioldm-s-full-v2 -p "gentle rain for focus"

# End session
mc stop
```

#### Pomodoro Timer with AI

```bash
# Work session - 25 min focus music
mc ai play -p "calm focus music" -d 300  # 5 min track, loops

# Break notification
mc ai play -m bark-small -p "Time for a five minute break"

# Break ambiance
mc ai play -m audioldm-s-full-v2 -p "nature forest sounds" -d 60
```

---

## Track Management

All generated tracks are saved and can be replayed.

### List Generated Tracks

```bash
# List all tracks (newest first)
mc ai
mc ai list
```

Output shows:
- Track number
- Prompt used
- Duration
- Model used
- Generation timestamp

### Replay a Track

```bash
# Replay track #1
mc ai replay 1

# Replay track #3
mc ai replay 3
```

> **Note:** If the audio file was deleted, replay will regenerate it using the original prompt.

### Remove a Track

```bash
# Remove track #2 (deletes audio file and metadata)
mc ai remove 2
```

---

## Storage & Configuration

### File Locations

| Platform | Config Directory |
|----------|------------------|
| Linux/macOS | `~/.config/music-cli/` |
| Windows | `%LOCALAPPDATA%\music-cli\` |

### AI-Related Files

| File/Directory | Purpose |
|----------------|---------|
| `ai_music/` | Generated audio files (WAV format) |
| `ai_tracks.json` | Track metadata (prompts, timestamps, models) |
| `config.toml` | AI configuration settings |

### Configuration Options

Edit `~/.config/music-cli/config.toml`:

```toml
[ai]
# Default model for generation
default_model = "musicgen-small"

[ai.cache]
# Maximum models to keep loaded in memory (LRU eviction)
max_models = 2

# Optional: Customize model parameters
[ai.models.audioldm-s-full-v2.extra_params]
num_inference_steps = 10  # More = better quality, slower
guidance_scale = 2.5      # How closely to follow prompt
```

### Disk Space Management

Check your model storage:

```bash
# See which models are downloaded
mc ai model

# Delete unused models
mc ai model delete musicgen-large
```

Typical storage requirements:
- Small models (~2 GB): musicgen-small, bark-small, audioldm-s-full-v2
- Medium models (~3.5 GB): musicgen-medium, musicgen-melody
- Large models (~5-7 GB): musicgen-large, bark

---

## Tips & Best Practices

### Writing Better Prompts

**Be Specific**
```bash
# Too vague
mc ai play -p "music"

# Better
mc ai play -p "soft acoustic guitar with gentle fingerpicking"
```

**Include Mood/Tempo**
```bash
mc ai play -p "upbeat cheerful pop music"
mc ai play -p "slow melancholic piano"
mc ai play -p "fast energetic electronic beats"
```

**Mention Instruments**
```bash
mc ai play -p "jazz with saxophone and double bass"
mc ai play -p "electronic with synth pads and arpeggios"
```

**Add Context**
```bash
mc ai play -p "ambient music for deep focus and concentration"
mc ai play -p "background music for coding at night"
```

### Resource Management

1. **Start with smaller models** - `musicgen-small`, `audioldm-s-full-v2`, `bark-small` are fast and efficient

2. **Pre-download models** - Avoid wait times during sessions:
   ```bash
   mc ai model download musicgen-small
   mc ai model download audioldm-s-full-v2
   ```

3. **Monitor memory** - The LRU cache keeps max 2 models loaded. Switching models may cause brief delays.

4. **Clean up old tracks** - Generated audio files accumulate:
   ```bash
   mc ai list          # Review tracks
   mc ai remove 5      # Remove unwanted
   ```

### Model Selection Tips

| Scenario | Recommendation |
|----------|----------------|
| First time / testing | `musicgen-small` (default) |
| Regular coding sessions | `musicgen-small` or `musicgen-medium` |
| Creating high-quality tracks | `musicgen-large` |
| Background nature sounds | `audioldm-s-full-v2` |
| Quick announcements | `bark-small` |
| Professional speech | `bark` |

---

## Troubleshooting

### AI Mode Not Working

```bash
# Check if dependencies are installed
python -c "import transformers; import torch; print('AI ready!')"

# If missing, install
pip install 'coder-music-cli[ai]'

# Check available models
mc ai model
```

### Model Download Issues

```bash
# Retry download
mc ai model download musicgen-small

# Check HuggingFace connectivity
python -c "from huggingface_hub import HfApi; HfApi().whoami()"
```

### Out of Memory

Symptoms: Generation fails or is very slow

Solutions:
1. Use smaller models (`musicgen-small`, `bark-small`)
2. Reduce `max_models` in config:
   ```toml
   [ai.cache]
   max_models = 1
   ```
3. Close other memory-intensive applications

### Generation Quality Issues

1. **Try longer prompts** - More detail usually helps
2. **Use larger models** - `musicgen-large` produces better results
3. **Adjust duration** - Very short or very long durations may affect quality

### Audio Not Playing

1. Check FFmpeg is installed: `which ffplay` (Linux/macOS) or `where ffplay` (Windows)
2. Check daemon is running: `mc daemon status`
3. Check volume: `mc vol`

---

## Command Reference

### AI Commands

| Command | Description |
|---------|-------------|
| `mc ai` | List all generated tracks |
| `mc ai list` | List all generated tracks |
| `mc ai play` | Generate and play audio |
| `mc ai replay <num>` | Replay track by number |
| `mc ai remove <num>` | Remove track and audio file |

### Model Commands

| Command | Description |
|---------|-------------|
| `mc ai model` | List all available models |
| `mc ai model list` | List all available models |
| `mc ai model download <model>` | Download a model |
| `mc ai model delete <model>` | Delete a cached model |
| `mc ai model default <model>` | Set default model |

### Play Options

| Option | Short | Description |
|--------|-------|-------------|
| `--prompt` | `-p` | Custom text prompt |
| `--duration` | `-d` | Duration in seconds |
| `--model` | `-m` | Model to use |
| `--mood` | `-M` | Generation mood |

---

## Next Steps

- Explore different models for your workflow
- Create a collection of favorite prompts
- Set up keyboard shortcuts or aliases for frequent commands
- Check out the [User Guide](user-guide.md) for other music-cli features
