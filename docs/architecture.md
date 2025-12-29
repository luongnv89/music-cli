# Architecture

music-cli uses a daemon-based architecture for persistent background playback with CLI control.

## System Overview

```mermaid
graph TB
    subgraph "User Interface"
        CLI[music-cli CLI]
    end

    subgraph "Daemon Process"
        D[MusicDaemon]
        P[FFplayPlayer]
        H[History]
    end

    subgraph "Music Sources"
        L[LocalSource]
        R[RadioSource]
        AI[AIGenerator]
    end

    subgraph "Context Engine"
        T[TemporalContext]
        M[MoodContext]
    end

    subgraph "External"
        FF[ffplay]
        RS[Radio Streams]
        MG[MusicGen Model]
    end

    CLI -->|Unix Socket| D
    D --> P
    D --> H
    D --> L
    D --> R
    D --> AI
    D --> T
    D --> M
    P --> FF
    R --> RS
    AI -.->|Optional| MG
```

## Component Architecture

### Core Components

| Component | Module | Responsibility |
|-----------|--------|----------------|
| CLI | `cli.py` | User commands, daemon lifecycle |
| Client | `client.py` | Socket communication with daemon |
| Daemon | `daemon.py` | Background process, command routing |
| Player | `player/` | Audio playback via ffplay |
| Sources | `sources/` | Music content providers |
| Context | `context/` | Smart music selection |
| History | `history.py` | Playback logging |
| Config | `config.py` | Settings management |

### Daemon Architecture

```mermaid
sequenceDiagram
    participant User
    participant CLI
    participant Socket
    participant Daemon
    participant Player
    participant Source

    User->>CLI: music-cli play --mood focus
    CLI->>CLI: ensure_daemon()
    CLI->>Socket: connect()
    CLI->>Socket: {"command": "play", "args": {...}}
    Socket->>Daemon: handle_client()
    Daemon->>Source: get_mood_station("focus")
    Source-->>Daemon: TrackInfo
    Daemon->>Player: play(track)
    Player->>Player: spawn ffplay
    Daemon->>Daemon: log_history()
    Daemon-->>Socket: {"status": "playing", "track": {...}}
    Socket-->>CLI: response
    CLI-->>User: Playing: Focus Radio
```

## Data Flow

### Playback Modes

```mermaid
flowchart LR
    subgraph Input
        CMD[Command]
    end

    subgraph Mode Selection
        LOCAL[Local Files]
        RADIO[Radio Streams]
        AI[AI Generation]
        CTX[Context-Aware]
        HIST[History Replay]
    end

    subgraph Processing
        SRC[Source Resolver]
        TRACK[TrackInfo]
    end

    subgraph Output
        PLAYER[FFplay]
        LOG[History Log]
    end

    CMD --> LOCAL & RADIO & AI & CTX & HIST
    LOCAL & RADIO & AI & CTX & HIST --> SRC
    SRC --> TRACK
    TRACK --> PLAYER
    TRACK --> LOG
```

### Context-Aware Selection

```mermaid
flowchart TD
    START[Play Request] --> MOOD{Mood Set?}
    MOOD -->|Yes| MOOD_MAP[Mood Radio Map]
    MOOD -->|No| TIME[Get Time Period]
    TIME --> TIME_MAP[Time Radio Map]
    MOOD_MAP --> TRACK[Select Track]
    TIME_MAP --> TRACK
    TRACK --> PLAY[Start Playback]
```

## IPC Protocol

Communication uses JSON over Unix sockets:

### Request Format
```json
{
  "command": "play|stop|pause|resume|status|...",
  "args": {
    "mode": "local|radio|ai|context|history",
    "source": "path/url/name",
    "mood": "focus|happy|sad|...",
    "auto": true
  }
}
```

### Response Format
```json
{
  "status": "playing|paused|stopped",
  "track": {
    "source": "/path/or/url",
    "source_type": "local|radio|ai",
    "title": "Track Name"
  },
  "error": "Error message if failed"
}
```

## File Structure

```
~/.config/music-cli/
├── config.toml      # User settings
├── radios.txt       # Radio station URLs
├── history.jsonl    # Playback history
├── music-cli.sock   # Unix socket (runtime)
└── music-cli.pid    # Daemon PID (runtime)
```

## Dependencies

### Required
- Python 3.9+
- FFmpeg (ffplay)
- click, tomli-w

### Optional (AI Mode)
- PyTorch
- transformers
- audiocraft (MusicGen)

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Daemon + Socket | Persistent playback, fast command response |
| ffplay backend | Lightweight, supports streaming, widely available |
| JSON-lines history | Human-readable, easy to parse/grep |
| TOML config | Clean syntax, Python 3.11+ native support |
| Optional AI | Graceful degradation, large dependency (~5GB) |
