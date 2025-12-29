# Development Guide

Guide for contributing to music-cli.

## Setup

### Prerequisites

- Python 3.9+
- FFmpeg
- Git

### Clone & Install

```bash
git clone https://github.com/luongnv89/music-cli
cd music-cli

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

# Install with dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

## Project Structure

```
music-cli/
├── music_cli/
│   ├── __init__.py         # Package version
│   ├── __main__.py          # Module entry point
│   ├── cli.py               # Click CLI commands
│   ├── client.py            # Socket client
│   ├── config.py            # Configuration management
│   ├── daemon.py            # Background daemon
│   ├── history.py           # Playback history
│   ├── context/
│   │   ├── mood.py          # Mood-based selection
│   │   └── temporal.py      # Time-based selection
│   ├── player/
│   │   ├── base.py          # Abstract player
│   │   └── ffplay.py        # FFplay implementation
│   └── sources/
│       ├── local.py         # Local files
│       ├── radio.py         # Radio streams
│       └── ai_generator.py  # MusicGen (optional)
├── tests/
│   ├── test_config.py
│   ├── test_context.py
│   └── test_history.py
├── docs/
│   ├── architecture.md
│   ├── development.md
│   └── user-guide.md
├── .github/workflows/
│   ├── ci.yml
│   └── release.yml
├── pyproject.toml
├── .pre-commit-config.yaml
└── README.md
```

## Development Workflow

### Running Locally

```bash
# Run CLI directly
python -m music_cli --help
music-cli play

# Run daemon in foreground (for debugging)
python -m music_cli.daemon
```

### Code Quality

```bash
# Format code
black music_cli/

# Lint
ruff check music_cli/ --fix

# Type check
mypy music_cli/

# Security scan
bandit -c pyproject.toml -r music_cli/

# All checks via pre-commit
pre-commit run --all-files
```

### Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=music_cli --cov-report=term-missing

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
pip install dist/music_cli-0.1.0-py3-none-any.whl
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

3. Add CLI command in `cli.py`:
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

- Black with 100-char line length
- Ruff for imports and linting

### Type Hints

Use type hints for function signatures:
```python
def get_track(self, path: str) -> TrackInfo | None:
    ...

async def play(self, track: TrackInfo) -> bool:
    ...
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

- **ci.yml**: Runs on push/PR
  - Lint (Black, Ruff, mypy, Bandit)
  - Test (Python 3.9-3.12, macOS + Linux)
  - Build verification

- **release.yml**: Runs on version tags
  - Build package
  - Create GitHub release
  - (Optional) Publish to PyPI

### Creating a Release

```bash
# Update version in music_cli/__init__.py
# Commit changes
git add -A && git commit -m "Bump version to 0.2.0"

# Create and push tag
git tag v0.2.0
git push origin main --tags
```

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
pre-commit run black --all-files

# Skip hooks (emergency only)
git commit --no-verify
```
