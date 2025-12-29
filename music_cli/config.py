"""Configuration management for music-cli."""

import logging
import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import tomli_w

logger = logging.getLogger(__name__)


class Config:
    """Manages music-cli configuration files and directories."""

    DEFAULT_CONFIG = {
        "player": {
            "backend": "ffplay",
            "volume": 80,
        },
        "daemon": {
            "socket_path": "~/.config/music-cli/music-cli.sock",
            "pid_file": "~/.config/music-cli/music-cli.pid",
        },
        "context": {
            "enabled": True,
            "use_ai": False,  # Requires optional AI dependencies
        },
        "mood_radio_map": {
            "focus": "https://streams.ilovemusic.de/iloveradio17.mp3",
            "happy": "https://streams.ilovemusic.de/iloveradio1.mp3",
            "sad": "https://streams.ilovemusic.de/iloveradio5.mp3",
            "excited": "https://streams.ilovemusic.de/iloveradio2.mp3",
        },
        "time_radio_map": {
            "morning": "https://streams.ilovemusic.de/iloveradio17.mp3",
            "afternoon": "https://streams.ilovemusic.de/iloveradio1.mp3",
            "evening": "https://streams.ilovemusic.de/iloveradio5.mp3",
            "night": "https://streams.ilovemusic.de/iloveradio9.mp3",
        },
    }

    def __init__(self, config_dir: Path | None = None):
        """Initialize config with optional custom directory."""
        if config_dir is None:
            config_dir = Path("~/.config/music-cli").expanduser()
        self.config_dir = config_dir
        self.config_file = self.config_dir / "config.toml"
        self.radios_file = self.config_dir / "radios.txt"
        self.history_file = self.config_dir / "history.jsonl"
        self.socket_path = self.config_dir / "music-cli.sock"
        self.pid_file = self.config_dir / "music-cli.pid"
        self._config: dict[str, Any] = {}
        self._ensure_config_dir()
        self._load_config()

    def _ensure_config_dir(self) -> None:
        """Create config directory and default files if they don't exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

        if not self.config_file.exists():
            self._write_default_config()

        if not self.radios_file.exists():
            self._write_default_radios()

        if not self.history_file.exists():
            self.history_file.touch()

    def _write_default_config(self) -> None:
        """Write default configuration file."""
        with self.config_file.open("wb") as f:
            tomli_w.dump(self.DEFAULT_CONFIG, f)

    def _write_default_radios(self) -> None:
        """Write default radio stations file."""
        default_radios = """# Radio stations for music-cli
# Add one URL per line. Lines starting with # are comments.
# Format: URL or "name|URL"

# Chill/Lo-fi
ChillHop|https://streams.ilovemusic.de/iloveradio17.mp3

# Electronic
Deep House|https://streams.ilovemusic.de/iloveradio14.mp3

# Pop
Top Hits|https://streams.ilovemusic.de/iloveradio1.mp3

# Rock
Rock Radio|https://streams.ilovemusic.de/iloveradio3.mp3

# Classical
Classical|http://stream.srg-ssr.ch/m/rsc_de/mp3_128
"""
        self.radios_file.write_text(default_radios)

    def _load_config(self) -> None:
        """Load configuration from file."""
        try:
            with self.config_file.open("rb") as f:
                self._config = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError) as e:
            logger.warning(f"Failed to load config from {self.config_file}: {e}")
            self._config = self.DEFAULT_CONFIG.copy()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value using dot notation (e.g., 'player.volume')."""
        keys = key.split(".")
        value: Any = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """Set a config value using dot notation and save."""
        keys = key.split(".")
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
        self.save()

    def save(self) -> None:
        """Save current configuration to file."""
        with self.config_file.open("wb") as f:
            tomli_w.dump(self._config, f)

    def get_radios(self) -> list[tuple[str, str]]:
        """Load radio stations from radios.txt.

        Returns list of (name, url) tuples.
        """
        radios: list[tuple[str, str]] = []
        if not self.radios_file.exists():
            return radios

        for line in self.radios_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" in line:
                name, url = line.split("|", 1)
                radios.append((name.strip(), url.strip()))
            else:
                radios.append((line, line))
        return radios

    def get_mood_radio(self, mood: str) -> str | None:
        """Get radio URL for a specific mood."""
        mood_map = self.get("mood_radio_map", {})
        return mood_map.get(mood.lower())

    def get_time_radio(self, time_period: str) -> str | None:
        """Get radio URL for a time period (morning/afternoon/evening/night)."""
        time_map = self.get("time_radio_map", {})
        return time_map.get(time_period.lower())


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get the global config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config
