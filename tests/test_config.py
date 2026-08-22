"""Tests for configuration module."""

import os
import stat
from pathlib import Path

import pytest

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


class TestConfigLoadFailureIsolation:
    """Regression tests for the shallow-copy defaults corruption bug (#45)."""

    def test_failed_load_does_not_alias_class_defaults(self, tmp_path: Path) -> None:
        """A corrupt config file must not alias Config.DEFAULT_CONFIG."""
        (tmp_path / "config.toml").write_text("this is [ not valid toml")
        cfg = Config(config_dir=tmp_path)
        assert cfg._config["player"] is not Config.DEFAULT_CONFIG["player"]

    def test_set_after_failed_load_leaves_defaults_intact(self, tmp_path: Path) -> None:
        """Writing through a fallback config must not poison class defaults."""
        (tmp_path / "config.toml").write_text("{{{broken")
        cfg = Config(config_dir=tmp_path)
        cfg.set("player.volume", 11)
        assert Config.DEFAULT_CONFIG["player"]["volume"] == 80
        assert cfg.get("player.volume") == 11


class TestConfigDirPermissions:
    """Config directories holding socket/PID/history must be owner-only (#48)."""

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
    def test_created_dirs_are_owner_only(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "cfg"
        cfg = Config(config_dir=config_dir)
        for directory in (cfg.config_dir, cfg.ai_music_dir, cfg.youtube_cache_dir):
            assert stat.S_IMODE(directory.stat().st_mode) == 0o700

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
    def test_existing_dirs_are_tightened(self, tmp_path: Path) -> None:
        """Directories created by older versions (0o755) get tightened."""
        config_dir = tmp_path / "cfg"
        config_dir.mkdir(mode=0o755)
        cfg = Config(config_dir=config_dir)
        for directory in (cfg.config_dir, cfg.ai_music_dir, cfg.youtube_cache_dir):
            assert stat.S_IMODE(directory.stat().st_mode) == 0o700


class TestAuthTokenStorage:
    """Daemon auth token is stored owner-only in the config dir (#47)."""

    def test_write_and_read_token_roundtrip(self, tmp_path: Path) -> None:
        cfg = Config(config_dir=tmp_path / "cfg")
        cfg.write_auth_token("secret-token")
        assert cfg.read_auth_token() == "secret-token"

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
    def test_token_file_is_owner_only(self, tmp_path: Path) -> None:
        cfg = Config(config_dir=tmp_path / "cfg")
        cfg.write_auth_token("secret-token")
        assert stat.S_IMODE(cfg.auth_token_file.stat().st_mode) == 0o600

    def test_read_missing_token_returns_none(self, tmp_path: Path) -> None:
        cfg = Config(config_dir=tmp_path / "cfg")
        assert cfg.read_auth_token() is None


class TestRadiosCache:
    """Parsed station list is memoised against radios.txt mtime (#83, F-PERF-004)."""

    @staticmethod
    def _count_radios_reads(
        monkeypatch: pytest.MonkeyPatch, radios_file: Path
    ) -> list[Path]:
        reads: list[Path] = []
        original_read_text = Path.read_text

        def counting_read_text(self: Path, *args: object, **kwargs: object) -> str:
            if self == radios_file:
                reads.append(self)
            return original_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(Path, "read_text", counting_read_text)
        return reads

    def test_repeated_lookups_in_one_play_read_radios_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A radio-mode play fans out over lookups but parses the file once."""
        config = Config(config_dir=tmp_path)
        config.radios_file.write_text(
            "# Chill\nJazz Groove|https://stream.example/jazz\n"
            "Blues|https://stream.example/blues\n"
        )
        reads = self._count_radios_reads(monkeypatch, config.radios_file)

        assert config.get_radios() == [
            ("Jazz Groove", "https://stream.example/jazz"),
            ("Blues", "https://stream.example/blues"),
        ]
        assert config.get_radio_by_index(2) == ("Blues", "https://stream.example/blues")
        assert config.get_station_by_name("JAZZ GROOVE") == (
            "Jazz Groove",
            "https://stream.example/jazz",
        )
        assert config.get_station_by_name("missing") is None
        assert config.get_radios() == config.get_radios()

        assert len(reads) == 1

    def test_single_play_through_radio_source_reads_at_most_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RadioSource lookups within one play hit radios.txt at most once."""
        from music_cli.sources.radio import RadioSource

        config = Config(config_dir=tmp_path)
        config.radios_file.write_text("Jazz Groove|https://stream.example/jazz\n")
        source = RadioSource()
        source.config = config
        source._youtube_available = True
        reads = self._count_radios_reads(monkeypatch, config.radios_file)

        track = source.get_station_by_index(1)
        assert track is not None and track.title == "Jazz Groove"
        by_name = source.get_station_by_name("groove")
        assert by_name is not None and by_name.source == "https://stream.example/jazz"

        assert len(reads) <= 1

    def test_edit_is_picked_up_on_next_call(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Editing radios.txt invalidates the cache on the next call."""
        config = Config(config_dir=tmp_path)
        radios_file = config.radios_file
        radios_file.write_text("Old Station|https://stream.example/old\n")
        assert config.get_radios() == [("Old Station", "https://stream.example/old")]

        radios_file.write_text("New Station|https://stream.example/new\n")
        stat_times = radios_file.stat()
        os.utime(radios_file, ns=(stat_times.st_atime_ns + 1_000_000,
                                  stat_times.st_mtime_ns + 1_000_000))

        assert config.get_radios() == [("New Station", "https://stream.example/new")]

    def test_missing_file_returns_empty_and_recovers(
        self, tmp_path: Path
    ) -> None:
        """A deleted radios.txt yields [] and recreation is seen again."""
        config = Config(config_dir=tmp_path)
        config.radios_file.write_text("Gone|https://stream.example/gone\n")
        assert len(config.get_radios()) == 1

        config.radios_file.unlink()
        assert config.get_radios() == []
        assert config.get_radios() == []

        config.radios_file.write_text("Back|https://stream.example/back\n")
        assert config.get_radios() == [("Back", "https://stream.example/back")]
