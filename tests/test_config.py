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

    def test_new_ai_models_are_available_in_existing_configs(self, tmp_path: Path) -> None:
        """Existing users receive newly supported built-in AI models in memory."""
        (tmp_path / "config.toml").write_text(
            """
[ai]
 default_model = "musicgen-small"

[ai.models.musicgen-small]
 hf_model_id = "facebook/musicgen-small"
 model_type = "musicgen"
 enabled = true
""".lstrip()
        )

        config = Config(config_dir=tmp_path)

        assert "minimax-music3" in config.list_ai_models(enabled_only=True)
        assert config.validate_ai_model("minimax-music3") is True
        assert config.get_ai_models_config().get_model("minimax-music3") is not None

    def test_ai_model_overrides_merge_recursively(self, tmp_path: Path) -> None:
        """Built-in capabilities survive partial nested model overrides."""
        (tmp_path / "config.toml").write_text(
            """
[ai.models.audioldm-s-full-v2]
description = "my AudioLDM"

[ai.models.audioldm-s-full-v2.extra_params]
guidance_scale = 4.0

[ai.models.custom-model]
hf_model_id = "example/custom-model"
model_type = "musicgen"
extra_params = { custom_flag = true }
""".lstrip()
        )

        config = Config(config_dir=tmp_path)

        partial = config.get_ai_model_config("audioldm-s-full-v2")
        assert partial is not None
        assert partial["hf_model_id"] == "cvssp/audioldm-s-full-v2"
        assert partial["model_type"] == "audioldm"
        assert partial["extra_params"] == {
            "num_inference_steps": 10,
            "guidance_scale": 4.0,
        }

        custom = config.get_ai_model_config("custom-model")
        assert custom == {
            "hf_model_id": "example/custom-model",
            "model_type": "musicgen",
            "extra_params": {"custom_flag": True},
        }

    def test_ai_model_full_override_wins(self, tmp_path: Path) -> None:
        """Explicit values in a complete built-in model override take precedence."""
        (tmp_path / "config.toml").write_text(
            """
[ai.models.audioldm-s-full-v2]
hf_model_id = "example/override"
model_type = "custom"
description = "override"
expected_size_gb = 9.0
default_duration = 20
max_duration = 40
min_duration = 3
tokens_per_second = 12
enabled = false
supports_lyrics = true
requires_lyrics = true

[ai.models.audioldm-s-full-v2.extra_params]
num_inference_steps = 99
guidance_scale = 8.0
""".lstrip()
        )

        config = Config(config_dir=tmp_path)
        model = config.get_ai_model_config("audioldm-s-full-v2")

        assert model == {
            "hf_model_id": "example/override",
            "model_type": "custom",
            "description": "override",
            "expected_size_gb": 9.0,
            "default_duration": 20,
            "max_duration": 40,
            "min_duration": 3,
            "tokens_per_second": 12,
            "enabled": False,
            "supports_lyrics": True,
            "requires_lyrics": True,
            "extra_params": {"num_inference_steps": 99, "guidance_scale": 8.0},
        }

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
