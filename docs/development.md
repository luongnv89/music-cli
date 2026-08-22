# Development Guide

Guide for contributing to music-cli.

Related docs: [Agent setup](AGENT_SETUP.md) · [Brand kit](brand-kit.md) ·
[Troubleshooting](troubleshooting.md) · [Decisions log](DECISIONS.md)

## Setup

### Prerequisites

- Python 3.12+ (`pyproject.toml:10`)
- FFmpeg
- Git

### Clone & Install

```bash
git clone https://github.com/luongnv89/music-cli
cd music-cli

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or: .venv\Scripts\activate  # Windows

# Install with dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

`scripts/validate-dev-setup.sh --check` verifies these preconditions
(`.venv`, `ffplay`, pinned tool versions, editable install) without running the
test suite.

## Project Structure

```
music-cli/
├── music_cli/
│   ├── __init__.py            # Package version (`__version__`)
│   ├── __main__.py            # Module entry point
│   ├── cli/                   # Click CLI package (one module per command group)
│   │   ├── app.py             # Click group + global flags (--no-color)
│   │   ├── playback.py        # play/pause/resume/stop/next/vol/status
│   │   ├── radio.py           # radio subcommands
│   │   ├── youtube.py         # yt replay-history subcommands
│   │   ├── ai.py / ai_models.py  # ai generation and model management
│   │   ├── history.py / misc.py / daemon_cmds.py / runtime.py / common.py
│   ├── client.py              # IPC client
│   ├── daemon.py              # Background daemon
│   ├── daemon_handlers.py     # Daemon command handlers (@handles registry)
│   ├── ipc_framing.py         # JSON message framing over IPC
│   ├── config.py              # Configuration management + default stations/models
│   ├── history.py             # Playback history (JSONL)
│   ├── youtube_history.py     # YouTube replay history
│   ├── ai_tracks.py           # AI track metadata store
│   ├── hf_cache.py            # HuggingFace cache helpers
│   ├── model_manager.py       # Model download/delete/default management
│   ├── context/               # mood.py, temporal.py — smart selection
│   ├── player/                # base.py, ffplay.py — playback backends
│   ├── sources/               # local.py, radio.py, youtube.py, ai_generator.py
│   │   └── ai_models/         # Per-model generation strategies + registry
│   └── platform/              # paths.py, ipc.py, player_control.py
├── tests/                     # ~37 pytest modules (tests/test_*.py)
├── docs/
├── .github/workflows/ci.yml   # lint/audit/test/build/pre-commit/shellcheck
├── .github/workflows/release.yml
├── pyproject.toml
├── .pre-commit-config.yaml
└── README.md
```

## Development Workflow

### Running Locally

```bash
# Run CLI directly
python -m music_cli --help
mc play

# Run daemon in foreground (for debugging)
python -m music_cli.daemon
```

### Code Quality

```bash
# Format code (Ruff formatter — Black is not used)
ruff format music_cli/

# Lint
ruff check music_cli/ --fix

# Type check
mypy music_cli/

# Security scan
bandit -c pyproject.toml -r music_cli/

# All checks via pre-commit
pre-commit run --all-files
```

Ruff is pinned to `0.16.4` and mypy to `2.3.1` in `pyproject.toml:70-71`,
matching the pre-commit hook revs in `.pre-commit-config.yaml:20-38`, so lint
results are identical locally, in hooks, and in CI.

### Testing

```bash
# Run all tests (command of record)
.venv/bin/pytest -q -p no:cacheprovider

# Coverage is always on: pyproject.toml addopts force
# --cov=music_cli --cov-report=term-missing --cov-fail-under=75 (pyproject.toml:130-136)

# Specific test file
pytest tests/test_config.py -v

# Specific test
pytest tests/test_config.py::TestConfig::test_config_creates_directory -v
```

### Building

```bash
# Build package
python -m build

# Check package
twine check dist/*

# Install locally built package
pip install dist/coder_music_cli-0.10.1-py3-none-any.whl
```

## Adding Features

### New Command

1. Add handler in `daemon.py`:
```python
async def _cmd_mycommand(self, args: dict) -> dict:
    """Handle my new command."""
    # Implementation
    return {"status": "ok"}
```

2. Register in `_process_command`:
```python
handlers = {
    # ...existing...
    "mycommand": self._cmd_mycommand,
}
```

3. Add the CLI command in the matching `music_cli/cli/` module:
```python
@main.command()
def mycommand():
    """My new command."""
    client = ensure_daemon()
    response = client.send_command("mycommand")
    click.echo(response)
```

### New Music Source

1. Create `sources/mysource.py`:
```python
from ..player.base import TrackInfo


class MySource:
    def get_track(self, query: str) -> TrackInfo | None:
        # Implementation
        return TrackInfo(
            source="...",
            source_type="mysource",
            title="...",
        )
```

2. Add to daemon's `_cmd_play`:
```python
elif mode == "mysource":
    track = self.my_source.get_track(source)
```

### New Player Backend

1. Create `player/myplayer.py` extending `Player`:
```python
from .base import Player, PlayerState, TrackInfo


class MyPlayer(Player):
    async def play(self, track: TrackInfo) -> bool:
        # Implementation
        pass

    async def stop(self) -> None:
        pass

    # ...other methods...
```

2. Update config to support backend selection.

## Code Style

### Formatting

- Ruff formatter with 100-char line length (`pyproject.toml:96-98`) — Black was removed
- Ruff for imports and linting (`pyproject.toml:100-111`)

### Type Hints

Use type hints for function signatures:
```python
def get_track(self, path: str) -> TrackInfo | None: ...


async def play(self, track: TrackInfo) -> bool: ...
```

### Docstrings

Use Google-style docstrings:
```python
def get_mood_radio(self, mood: str) -> str | None:
    """Get radio URL for a specific mood.

    Args:
        mood: The mood tag (focus, happy, sad, etc.)

    Returns:
        Stream URL or None if mood not found.
    """
```

### Error Handling

```python
# Specific exceptions
try:
    result = risky_operation()
except (FileNotFoundError, PermissionError) as e:
    logger.warning(f"Operation failed: {e}")
    return None

# Re-raise with context
except ConnectionError as e:
    raise ConnectionError("Daemon not responding") from e
```

## Testing Guidelines

### Test Structure

```python
class TestMyFeature:
    """Tests for MyFeature."""

    def test_basic_case(self, tmp_path: Path) -> None:
        """Test the basic use case."""
        # Arrange
        feature = MyFeature(config_dir=tmp_path)

        # Act
        result = feature.do_something()

        # Assert
        assert result.status == "ok"

    def test_edge_case(self) -> None:
        """Test edge case handling."""
        ...
```

### Fixtures

Use pytest fixtures for common setup:
```python
@pytest.fixture
def config(tmp_path):
    return Config(config_dir=tmp_path)


def test_with_config(config):
    assert config.get("player.volume") == 80
```

## CI/CD

### GitHub Actions

Two workflows live in `.github/workflows/`:

- **ci.yml**: runs on push/PR to main/master/develop, skipping `docs/**` and `*.md` (`ci.yml:6-16`)
  - **lint** — Ruff format check, Ruff lint, mypy, Bandit; no Black (`ci.yml:28-61`)
  - **audit** — pip-audit with `--strict` (`ci.yml:63-99`)
  - **test** — Python 3.12/3.13/3.14 on ubuntu/macos/windows; Windows+3.14 excluded; 75% coverage gate on ubuntu/py3.12 only (`ci.yml:101-179`)
  - **build** — `python -m build` + `twine check dist/*` (`ci.yml:181-202`)
  - **pre-commit** and **shellcheck** on `install.sh` (`ci.yml:210-238`)

- **release.yml**: runs on tags matching `v*` (`release.yml:6-9`)
  - Builds the package and creates a GitHub release attaching `dist/*` plus an `install.sh.sha256` checksum asset (`release.yml:53-64`)
  - PyPI publishing is present but fully commented out (`release.yml:66-84`) — releases go to GitHub only until it is enabled

### Creating a Release

```bash
# Update version in BOTH places:
#   music_cli/__init__.py (__version__) and pyproject.toml ([project].version)
# Commit changes
git add -A && git commit -m "Bump version to 0.11.0"

# Create and push tag — release.yml does the rest
git tag v0.11.0
git push origin main --tags
```

Note: no workflow verifies that the pushed tag matches `__version__`; keep the
three values in sync manually.

## Troubleshooting Development

### Daemon Not Stopping

```bash
# Find and kill process
ps aux | grep music_cli.daemon
kill <pid>

# Clean up files
rm ~/.config/music-cli/music-cli.sock
rm ~/.config/music-cli/music-cli.pid
```

### Tests Failing Locally

```bash
# Clean pytest cache
rm -rf .pytest_cache/

# Reinstall in dev mode
pip install -e ".[dev]"
```

### Pre-commit Failing

```bash
# Update hooks
pre-commit autoupdate

# Run specific hook
pre-commit run ruff-format --all-files

# Skip hooks (emergency only)
git commit --no-verify
```
