# Contributing to music-cli

Thank you for your interest in contributing! music-cli is an open-source project and welcomes contributions of all kinds — bug reports, feature ideas, documentation improvements, and code.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Branching Strategy](#branching-strategy)
- [Commit Conventions](#commit-conventions)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing Requirements](#testing-requirements)
- [Reporting Issues](#reporting-issues)

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold its standards. Please report unacceptable behavior to [luongnv89@gmail.com](mailto:luongnv89@gmail.com).

---

## Getting Started

1. **Fork** the repository on GitHub
2. **Clone** your fork locally
3. **Set up** the development environment (see below)
4. **Create a branch** for your changes
5. **Submit a pull request** when ready

---

## Development Setup

### Prerequisites

- Python 3.10+
- FFmpeg (`brew install ffmpeg` / `sudo apt install ffmpeg` / `choco install ffmpeg`)
- Git

### Install

```bash
git clone https://github.com/luongnv89/music-cli
cd music-cli

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Linux/macOS
# or: venv\Scripts\activate     # Windows

# Install with all dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Optional extras

```bash
pip install -e ".[ai]"       # AI music generation (PyTorch ~5GB)
pip install -e ".[youtube]"  # YouTube streaming (yt-dlp ~10MB)
```

### Verify setup

```bash
music-cli --help
pytest
```

---

## Branching Strategy

All contributions go through feature branches. Branch from `main`:

| Branch prefix | Purpose |
|---|---|
| `feat/` | New feature |
| `fix/` | Bug fix |
| `docs/` | Documentation only |
| `refactor/` | Code refactor, no behaviour change |
| `test/` | Tests only |
| `chore/` | Tooling, CI, deps |

```bash
git checkout main
git pull origin main
git checkout -b feat/my-feature
```

---

## Commit Conventions

This project uses [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short summary>

[optional body]

[optional footer]
```

**Types:** `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`, `perf`, `brand`

**Examples:**

```
feat(sources): add SoundCloud streaming support
fix(daemon): prevent zombie process on unexpected exit
docs(readme): update installation instructions
chore(deps): bump yt-dlp to 2024.12.0
```

**Rules:**
- Use the imperative mood: "add feature" not "added feature"
- Keep the summary under 72 characters
- Reference issues in the footer: `Closes #42`

---

## Pull Request Process

1. **Open a draft PR** early if you want feedback on the approach
2. **Fill in the PR template** completely
3. **Link related issues** using `Fixes #N` or `Closes #N`
4. **Ensure CI passes** — all checks must be green before review
5. **Request a review** from a maintainer
6. **Address feedback** in new commits (do not force-push during review)
7. **Squash on merge** is used — your commits will be squashed to one

### Red `main` is an incident

A red `main` blocks all merges until fixed. If `ci.yml` on `main` is red, treat it
as a stop-the-line incident, not the status quo: nobody merges new work, and the
first priority is restoring green (revert, fix, or a fast-follow repair). PRs may
still open against `main`, but they do not merge until `main` is green again.

### PR checklist (also in the template)

- [ ] Code follows the style guidelines
- [ ] Self-reviewed the diff
- [ ] Tests added / updated
- [ ] Documentation updated if behaviour changed
- [ ] CI checks pass

---

## Coding Standards

### Formatting & Linting

The project uses [Black](https://black.readthedocs.io/) + [Ruff](https://docs.astral.sh/ruff/) with a 100-character line length. Pre-commit hooks run these automatically.

```bash
black music_cli/          # Format
ruff check music_cli/ --fix  # Lint + auto-fix
mypy music_cli/           # Type check
bandit -c pyproject.toml -r music_cli/  # Security scan
pre-commit run --all-files  # All checks at once
```

### Type hints

All public functions should have type annotations:

```python
def get_track(self, path: str) -> TrackInfo | None: ...
async def play(self, track: TrackInfo) -> bool: ...
```

### Docstrings

Use Google-style docstrings for public APIs:

```python
def get_mood_radio(self, mood: str) -> str | None:
    """Get radio stream URL for a given mood.

    Args:
        mood: Mood tag (focus, happy, relaxed, …).

    Returns:
        Stream URL, or None if no station is configured for that mood.
    """
```

### Error handling

Prefer specific exceptions; avoid bare `except`:

```python
try:
    result = risky_operation()
except (FileNotFoundError, PermissionError) as e:
    logger.warning("Operation failed: %s", e)
    return None
```

---

## Testing Requirements

New code should come with tests. The test suite uses [pytest](https://pytest.org).

```bash
pytest                                          # Run all tests
pytest --cov=music_cli --cov-report=term-missing  # With coverage
pytest tests/test_config.py -v                  # Single file
```

**Guidelines:**

- Place tests in `tests/` mirroring the package structure
- Use `tmp_path` fixture for file-system operations
- Mock external processes (`ffplay`, sockets) — do not rely on live audio
- Aim to keep or improve the existing coverage

---

## Reporting Issues

- **Bugs** — use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md)
- **Features** — use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md)
- **Security** — see [SECURITY.md](SECURITY.md) — **do not open public issues for vulnerabilities**
- **Questions** — open a [Discussion](https://github.com/luongnv89/music-cli/discussions)

---

Thank you for contributing! 🎵
