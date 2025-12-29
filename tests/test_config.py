"""Tests for configuration module."""

from pathlib import Path

from music_cli.config import Config


class TestConfig:
    """Tests for Config class."""

    def test_config_creates_directory(self, tmp_path: Path) -> None:
        """Test that config creates directory if it doesn't exist."""
        config_dir = tmp_path / "test-config"
        config = Config(config_dir=config_dir)

        assert config_dir.exists()
        assert config.config_file.exists()
        assert config.radios_file.exists()

    def test_config_default_values(self, tmp_path: Path) -> None:
        """Test that config has sensible defaults."""
        config = Config(config_dir=tmp_path)

        assert config.get("player.backend") == "ffplay"
        assert config.get("player.volume") == 80
        assert config.get("context.enabled") is True

    def test_config_get_with_default(self, tmp_path: Path) -> None:
        """Test getting config value with default."""
        config = Config(config_dir=tmp_path)

        assert config.get("nonexistent.key", "default") == "default"
        assert config.get("nonexistent.key") is None

    def test_config_set_and_get(self, tmp_path: Path) -> None:
        """Test setting and getting config values."""
        config = Config(config_dir=tmp_path)

        config.set("player.volume", 50)
        assert config.get("player.volume") == 50

    def test_radios_parsing(self, tmp_path: Path) -> None:
        """Test parsing of radio stations file."""
        config = Config(config_dir=tmp_path)

        # Default radios should be loaded
        radios = config.get_radios()
        assert len(radios) > 0

        # Each radio should be a (name, url) tuple
        for name, url in radios:
            assert isinstance(name, str)
            assert isinstance(url, str)

    def test_mood_radio_mapping(self, tmp_path: Path) -> None:
        """Test mood to radio URL mapping."""
        config = Config(config_dir=tmp_path)

        # Default moods should have URLs
        focus_url = config.get_mood_radio("focus")
        assert focus_url is not None
        assert focus_url.startswith("http")

        # Unknown mood should return None
        assert config.get_mood_radio("unknown_mood") is None

    def test_time_radio_mapping(self, tmp_path: Path) -> None:
        """Test time period to radio URL mapping."""
        config = Config(config_dir=tmp_path)

        # Default time periods should have URLs
        morning_url = config.get_time_radio("morning")
        assert morning_url is not None
        assert morning_url.startswith("http")

        # Unknown time period should return None
        assert config.get_time_radio("unknown_time") is None
