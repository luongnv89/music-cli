"""Configuration management for music-cli."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import tomli_w

from . import __version__

logger = logging.getLogger(__name__)


class Config:
    """Manages music-cli configuration files and directories."""

    DEFAULT_CONFIG = {
        "version": __version__,
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

    # Default radio stations content
    DEFAULT_RADIOS = """# Radio stations for music-cli
# Add one URL per line. Lines starting with # are comments.
# Format: URL or "name|URL"

# ========== ENGLISH ==========

# Chill/Lo-fi
ChillHop|https://streams.ilovemusic.de/iloveradio17.mp3
Groove Salad [SomaFM]|http://ice1.somafm.com/groovesalad-128-mp3
Drone Zone [SomaFM]|http://ice1.somafm.com/dronezone-128-mp3
Space Station Soma|http://ice1.somafm.com/spacestation-128-mp3
Hirschmilch Chillout|http://hirschmilch.de:7000/chillout.mp3

# Electronic
Deep House|https://streams.ilovemusic.de/iloveradio14.mp3
DEF CON Radio [SomaFM]|http://ice1.somafm.com/defcon-128-mp3
Beat Blender [SomaFM]|http://ice1.somafm.com/beatblender-128-mp3

# Pop/Hits
Top Hits|https://streams.ilovemusic.de/iloveradio1.mp3
80s Hits|https://streams.ilovemusic.de/iloveradio4.mp3

# Rock
Rock Radio|https://streams.ilovemusic.de/iloveradio3.mp3
Metal [SomaFM]|http://ice1.somafm.com/metal-128-mp3

# Jazz
Jazz [SomaFM]|http://ice1.somafm.com/secretagent-128-mp3

# Classical
Classical|http://stream.srg-ssr.ch/m/rsc_de/mp3_128
BBC Radio 3|http://stream.live.vc.bbcmedia.co.uk/bbc_radio_three

# ========== FRENCH ==========

# French Pop
FIP Radio|http://icecast.radiofrance.fr/fip-midfi.mp3
France Inter|http://icecast.radiofrance.fr/franceinter-midfi.mp3
France Musique|http://icecast.radiofrance.fr/francemusique-midfi.mp3
FIP Rock|http://icecast.radiofrance.fr/fiprock-midfi.mp3
FIP Jazz|http://icecast.radiofrance.fr/fipjazz-midfi.mp3
FIP Electro|http://icecast.radiofrance.fr/fipelectro-midfi.mp3
Mouv|http://icecast.radiofrance.fr/mouv-midfi.mp3

# ========== SPANISH ==========

# Latin/Salsa
Salsa Radio|http://157.230.221.44:2002/stream/1/
Tropical 100 Salsa|http://tropical100.net:8008/stream/1/
SalsaMexico|http://colombiawebs.com.co:8106/stream/1/
Los 40 Principales|https://playerservices.streamtheworld.com/api/livestream-redirect/LOS40.mp3

# Spanish Pop/Rock
Radio Maria Spain|http://dreamsiteradiocp.com:8060/stream/1/
Cadena SER|https://playerservices.streamtheworld.com/api/livestream-redirect/CADENASER.mp3

# ========== ITALIAN ==========

# Italian Radio
Radio Italia|http://radioitalia.net/stream/1/
RTL 102.5|http://streamingp.shoutcast.com/RTL1025?lang=*
Radio 105|https://icecast.unitedradio.it/Radio105.mp3
Virgin Radio Italy|https://icecast.unitedradio.it/Virgin.mp3
Radio Deejay|https://icecast.unitedradio.it/RadioDeejay.mp3
RDS Radio|http://stream.rds.it:8000/rds64k.mp3
Radio Capital|https://icecast.unitedradio.it/Capital.mp3
"""

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
        self.ai_music_dir = self.config_dir / "ai_music"
        self._config: dict[str, Any] = {}
        self._ensure_config_dir()
        self._load_config()

    def _ensure_config_dir(self) -> None:
        """Create config directory and default files if they don't exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.ai_music_dir.mkdir(parents=True, exist_ok=True)

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
        self.radios_file.write_text(self.DEFAULT_RADIOS)

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

    def get_radio_by_index(self, index: int) -> tuple[str, str] | None:
        """Get a radio station by its 1-based index.

        Returns (name, url) tuple or None if index is invalid.
        """
        radios = self.get_radios()
        if 1 <= index <= len(radios):
            return radios[index - 1]
        return None

    def add_radio(self, name: str, url: str) -> None:
        """Add a new radio station to the radios.txt file."""
        with self.radios_file.open("a") as f:
            f.write(f"{name}|{url}\n")

    def remove_radio(self, index: int) -> tuple[str, str] | None:
        """Remove a radio station by its 1-based index.

        Returns the removed (name, url) tuple or None if index is invalid.
        """
        if not self.radios_file.exists():
            return None

        lines = self.radios_file.read_text().splitlines()
        radios = self.get_radios()

        if not (1 <= index <= len(radios)):
            return None

        removed = radios[index - 1]

        # Find and remove the corresponding line
        radio_count = 0
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                radio_count += 1
                if radio_count == index:
                    continue  # Skip this line (remove it)
            new_lines.append(line)

        self.radios_file.write_text("\n".join(new_lines) + "\n" if new_lines else "")
        return removed

    def get_mood_radio(self, mood: str) -> str | None:
        """Get radio URL for a specific mood."""
        mood_map = self.get("mood_radio_map", {})
        return mood_map.get(mood.lower())

    def get_time_radio(self, time_period: str) -> str | None:
        """Get radio URL for a time period (morning/afternoon/evening/night)."""
        time_map = self.get("time_radio_map", {})
        return time_map.get(time_period.lower())

    def get_installed_version(self) -> str | None:
        """Get the version stored in config file."""
        return self.get("version")

    def needs_update(self) -> bool:
        """Check if config was created with an older version."""
        installed = self.get_installed_version()
        if installed is None:
            return True
        return installed != __version__

    def update_version(self) -> None:
        """Update the stored version to current."""
        self.set("version", __version__)

    def get_default_radio_urls(self) -> "set[str]":  # type: ignore[valid-type]  # noqa: UP037
        """Get set of URLs from default radios."""
        urls: set[str] = set()
        for line in self.DEFAULT_RADIOS.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" in line:
                _, url = line.split("|", 1)
                urls.add(url.strip())
            else:
                urls.add(line)
        return urls

    def get_user_radio_urls(self) -> "set[str]":  # type: ignore[valid-type]  # noqa: UP037
        """Get set of URLs from user's radios.txt."""
        urls: set[str] = set()
        if not self.radios_file.exists():
            return urls
        for line in self.radios_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" in line:
                _, url = line.split("|", 1)
                urls.add(url.strip())
            else:
                urls.add(line)
        return urls

    def get_new_default_stations(self) -> list[tuple[str, str]]:
        """Get stations that are in defaults but not in user's file.

        Returns list of (name, url) tuples for new stations.
        """
        user_urls = self.get_user_radio_urls()
        new_stations = []
        for line in self.DEFAULT_RADIOS.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" in line:
                name, url = line.split("|", 1)
                if url.strip() not in user_urls:  # type: ignore[attr-defined]
                    new_stations.append((name.strip(), url.strip()))
            elif line not in user_urls:  # type: ignore[attr-defined]
                new_stations.append((line, line))
        return new_stations

    def merge_radios(self) -> int:
        """Merge new default stations into user's radios.txt.

        Returns number of stations added.
        """
        new_stations = self.get_new_default_stations()
        if not new_stations:
            return 0

        # Append new stations to existing file
        with self.radios_file.open("a") as f:
            f.write("\n# ========== NEW STATIONS (added in update) ==========\n\n")
            for name, url in new_stations:
                if name != url:
                    f.write(f"{name}|{url}\n")
                else:
                    f.write(f"{url}\n")

        return len(new_stations)

    def overwrite_radios(self) -> None:
        """Replace user's radios.txt with defaults (backs up old file)."""
        if self.radios_file.exists():
            backup = self.radios_file.with_suffix(".txt.backup")
            self.radios_file.rename(backup)
        self._write_default_radios()

    def backup_radios_path(self) -> Path:
        """Get the path where radios backup would be stored."""
        return self.radios_file.with_suffix(".txt.backup")


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get the global config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config
