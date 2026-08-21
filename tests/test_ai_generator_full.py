"""AIGenerator and strategy-selection tests (issue #72 — coverage raise).

scipy is optional, so a stub ``scipy.io.wavfile`` module is injected for the
generation happy path; model availability is patched at the module boundary so
no AI extra is required.
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest

import music_cli.sources.ai_generator as ai_generator_module
from music_cli.sources.ai_generator import (
    LOOP_INSTRUCTION,
    AIGenerator,
    GenerationRequest,
    _get_strategy,
    _get_strategy_cache,
    get_ai_install_instructions,
    is_ai_available,
)
from music_cli.sources.ai_models import AIModelsConfig
from music_cli.sources.ai_models.model_config import ModelConfig


@pytest.fixture(autouse=True)
def reset_availability_cache(monkeypatch: pytest.MonkeyPatch):
    """Keep the module-level availability flag isolated per test."""
    monkeypatch.setattr(ai_generator_module, "_AI_AVAILABLE", None)


def models_config() -> AIModelsConfig:
    return AIModelsConfig.from_dict(
        {
            "default_model": "musicgen-small",
            "models": {
                "musicgen-small": {
                    "hf_model_id": "facebook/musicgen-small",
                    "model_type": "musicgen",
                    "max_duration": 30,
                },
                "bark": {"hf_model_id": "suno/bark", "model_type": "bark"},
                "minimax-music3": {
                    "hf_model_id": "MiniMaxAI/MiniMax-Music3",
                    "model_type": "minimax_music3",
                    "supports_lyrics": True,
                    "requires_lyrics": True,
                },
            },
        }
    )


def install_fake_scipy(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Stub scipy.io.wavfile.write so generation can save without scipy."""
    scipy = ModuleType("scipy")
    scipy_io = ModuleType("scipy.io")
    wavfile = ModuleType("scipy.io.wavfile")
    write = Mock()
    wavfile.write = write  # type: ignore[attr-defined]
    scipy.io = scipy_io  # type: ignore[attr-defined]
    scipy_io.wavfile = wavfile  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "scipy", scipy)
    monkeypatch.setitem(sys.modules, "scipy.io", scipy_io)
    monkeypatch.setitem(sys.modules, "scipy.io.wavfile", wavfile)
    return write


def make_strategy() -> MagicMock:
    strategy = MagicMock()
    config = ModelConfig(
        id="musicgen-small",
        hf_model_id="facebook/musicgen-small",
        model_type="musicgen",
        max_duration=30,
    )
    strategy.config = config
    strategy.generate_audio.return_value = (
        np.zeros(16, dtype=np.int16),
        32000,
    )
    return strategy


class TestIsAiAvailable:
    def test_unavailable_without_extras(self) -> None:
        # The dev venv has no torch/scipy/transformers.
        assert is_ai_available() is False

    def test_available_with_stubbed_extras(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "scipy", ModuleType("scipy"))
        monkeypatch.setitem(sys.modules, "torch", ModuleType("torch"))
        transformers = ModuleType("transformers")
        transformers.AutoProcessor = object  # type: ignore[attr-defined]
        transformers.MusicgenForConditionalGeneration = object  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "transformers", transformers)
        assert is_ai_available() is True

    def test_musicgen_absence_falls_back_to_diffusers(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "scipy", ModuleType("scipy"))
        monkeypatch.setitem(sys.modules, "torch", ModuleType("torch"))
        # transformers exists but lacks MusicGen symbols (transformers 5.x split).
        monkeypatch.setitem(sys.modules, "transformers", ModuleType("transformers"))
        monkeypatch.setitem(sys.modules, "diffusers", ModuleType("diffusers"))
        assert is_ai_available() is True

    def test_result_is_cached(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "scipy", ModuleType("scipy"))
        monkeypatch.setitem(sys.modules, "torch", ModuleType("torch"))
        transformers = ModuleType("transformers")
        transformers.AutoProcessor = object  # type: ignore[attr-defined]
        transformers.MusicgenForConditionalGeneration = object  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "transformers", transformers)
        assert is_ai_available() is True
        # Second call returns the cached flag without re-importing.
        assert is_ai_available() is True


class TestStrategyCacheHelper:
    def test_updates_max_size_when_config_changed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cache = SimpleNamespace(max_size=5)
        monkeypatch.setattr(
            "music_cli.config.get_config",
            lambda: SimpleNamespace(get_ai_cache_max_models=lambda: 3),
        )
        monkeypatch.setattr(
            "music_cli.sources.ai_models.get_strategy_cache",
            lambda max_size=2: cache,
        )
        result = _get_strategy_cache()
        assert result is cache
        assert cache.max_size == 3


class TestGetStrategy:
    def _config(self) -> SimpleNamespace:
        cfg = SimpleNamespace(get_ai_models_config=lambda: models_config())
        return cfg

    def test_unknown_model_returns_none(self, monkeypatch) -> None:
        cache = SimpleNamespace(
            get=lambda _: None,
            get_cached_models=lambda: [],
            put=lambda *_: None,
        )
        monkeypatch.setattr(ai_generator_module, "_get_strategy_cache", lambda: cache)
        monkeypatch.setattr("music_cli.config.get_config", self._config)
        assert _get_strategy("ghost") is None

    def test_ensure_loaded_failure_returns_none(self, monkeypatch) -> None:
        failing = Mock()
        failing.is_loaded = False
        failing.ensure_loaded.return_value = False
        monkeypatch.setattr(
            ai_generator_module,
            "_get_strategy_cache",
            lambda: SimpleNamespace(
                get=lambda _: None,
                get_cached_models=lambda: [],
                put=lambda *_: None,
            ),
        )
        monkeypatch.setattr("music_cli.config.get_config", self._config)
        monkeypatch.setattr(
            "music_cli.sources.ai_models.ModelRegistry.create_strategy",
            lambda _cfg: failing,
        )
        assert _get_strategy("musicgen-small") is None
        failing.ensure_loaded.assert_called_once_with()

    def test_value_error_returns_none(self, monkeypatch) -> None:
        monkeypatch.setattr(
            ai_generator_module,
            "_get_strategy_cache",
            lambda: SimpleNamespace(
                get=lambda _: None,
                get_cached_models=lambda: [],
                put=lambda *_: None,
            ),
        )
        monkeypatch.setattr("music_cli.config.get_config", self._config)

        def raise_value_error(_cfg):
            raise ValueError("bad model type")

        monkeypatch.setattr(
            "music_cli.sources.ai_models.ModelRegistry.create_strategy",
            raise_value_error,
        )
        assert _get_strategy("musicgen-small") is None

    def test_unexpected_error_returns_none(self, monkeypatch) -> None:
        monkeypatch.setattr(
            ai_generator_module,
            "_get_strategy_cache",
            lambda: SimpleNamespace(
                get=lambda _: None,
                get_cached_models=lambda: [],
                put=lambda *_: None,
            ),
        )
        monkeypatch.setattr("music_cli.config.get_config", self._config)

        def raise_oops(_cfg):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "music_cli.sources.ai_models.ModelRegistry.create_strategy",
            raise_oops,
        )
        assert _get_strategy("musicgen-small") is None

    def test_minimax_eviction_falls_back_to_registry_config(self, monkeypatch) -> None:
        """Cached strategies without their own config use the registry type."""
        cached = Mock(spec=["is_loaded", "ensure_loaded"])  # no .config attribute
        cached.is_loaded = False
        created = Mock()
        created.is_loaded = False
        created.ensure_loaded.return_value = True
        removed = []
        cache = SimpleNamespace(
            get=lambda mid: cached if mid == "bark" else None,
            get_cached_models=lambda: ["bark"],
            remove=lambda mid: removed.append(mid),
            put=lambda *_: None,
        )
        monkeypatch.setattr(ai_generator_module, "_get_strategy_cache", lambda: cache)
        monkeypatch.setattr("music_cli.config.get_config", self._config)
        monkeypatch.setattr(
            "music_cli.sources.ai_models.ModelRegistry.create_strategy",
            lambda _cfg: created,
        )

        result = _get_strategy("minimax-music3")
        assert result is created
        assert removed == ["bark"]  # minimax target evicts incompatible cache

    def test_non_minimax_pair_is_not_evicted(self, monkeypatch) -> None:
        cached_cfg = ModelConfig(id="bark", hf_model_id="suno/bark", model_type="bark")
        cached = Mock(spec=["is_loaded", "ensure_loaded"])
        cached.is_loaded = False
        cached.config = cached_cfg
        created = Mock()
        created.ensure_loaded.return_value = True
        removed = []
        cache = SimpleNamespace(
            get=lambda mid: cached if mid == "bark" else None,
            get_cached_models=lambda: ["bark"],
            remove=lambda mid: removed.append(mid),
            put=lambda *_: None,
        )
        monkeypatch.setattr(ai_generator_module, "_get_strategy_cache", lambda: cache)
        monkeypatch.setattr("music_cli.config.get_config", self._config)
        monkeypatch.setattr(
            "music_cli.sources.ai_models.ModelRegistry.create_strategy",
            lambda _cfg: created,
        )

        _get_strategy("musicgen-small")  # neither side is minimax
        assert removed == []


class TestAIGeneratorBasics:
    def test_default_output_dir_and_config(self) -> None:
        generator = AIGenerator()
        assert generator.output_dir.name == "music-cli-ai"

    def test_explicit_output_dir_created(self, tmp_path) -> None:
        out = tmp_path / "custom"
        generator = AIGenerator(output_dir=out, config=MagicMock())
        assert out.exists()
        assert generator.available is False  # extras absent in dev venv

    def test_get_default_model_and_list_passthrough(self) -> None:
        config = MagicMock()
        config.get_default_ai_model.return_value = "musicgen-small"
        generator = AIGenerator(output_dir=None, config=config)
        assert generator.get_default_model() == "musicgen-small"
        generator.list_models(enabled_only=False)
        config.list_ai_models.assert_called_once_with(enabled_only=False)


class TestGenerate:
    def _generator(self) -> tuple[AIGenerator, MagicMock]:
        config = MagicMock()
        config.get_default_ai_model.return_value = "musicgen-small"
        config.get_ai_models_config.return_value = models_config()
        return AIGenerator(output_dir=None, config=config), config

    def test_unavailable_returns_none(self, tmp_path) -> None:
        generator, _ = self._generator()
        with patch.object(ai_generator_module, "is_ai_available", return_value=False):
            assert generator.generate(GenerationRequest(prompt="beats")) is None

    @pytest.mark.parametrize("lyrics", [None, "", "   "])
    def test_requires_lyrics_models_reject_missing_lyrics(self, tmp_path, lyrics) -> None:
        generator, _ = self._generator()
        with patch.object(ai_generator_module, "is_ai_available", return_value=True):
            result = generator.generate(
                GenerationRequest(prompt="song", model_id="minimax-music3", lyrics=lyrics)
            )
        assert result is None

    def test_lyrics_rejected_on_non_supporting_model(self, tmp_path) -> None:
        generator, _ = self._generator()
        with patch.object(ai_generator_module, "is_ai_available", return_value=True):
            result = generator.generate(
                GenerationRequest(prompt="song", model_id="musicgen-small", lyrics="la")
            )
        assert result is None

    def test_unconfigured_model_rejected(self, tmp_path) -> None:
        generator, _ = self._generator()
        with patch.object(ai_generator_module, "is_ai_available", return_value=True):
            result = generator.generate(GenerationRequest(prompt="song", model_id="ghost-model"))
        assert result is None

    def test_failed_strategy_returns_none(self, tmp_path, monkeypatch) -> None:
        generator, _ = self._generator()
        with (
            patch.object(ai_generator_module, "is_ai_available", return_value=True),
            patch.object(ai_generator_module, "_get_strategy", return_value=None),
        ):
            assert generator.generate(GenerationRequest(prompt="beats")) is None

    def test_generation_happy_path(self, tmp_path, monkeypatch) -> None:
        generator, _ = self._generator()
        strategy = make_strategy()
        wav_write = install_fake_scipy(monkeypatch)

        with (
            patch.object(ai_generator_module, "is_ai_available", return_value=True),
            patch.object(ai_generator_module, "_get_strategy", return_value=strategy),
        ):
            track = generator.generate(
                GenerationRequest(prompt="lofi beats", duration=999, add_looping=True)
            )

        assert track is not None
        assert track.source_type == "ai"
        assert track.metadata["model"] == "musicgen-small"
        assert track.metadata["hf_model_id"] == "facebook/musicgen-small"
        assert track.metadata["lyrics"] is None
        # Duration clamped to the model's max_duration of 30.
        assert track.metadata["duration"] == 30
        # Looping instruction appended to the prompt handed to the strategy.
        prompt_arg = strategy.generate_audio.call_args[0][0]
        assert prompt_arg.endswith(LOOP_INSTRUCTION)
        # Audio written via the injected stub writer.
        wav_write.assert_called_once()

    def test_generation_without_looping_keeps_prompt(self, tmp_path, monkeypatch) -> None:
        generator, _ = self._generator()
        strategy = make_strategy()
        install_fake_scipy(monkeypatch)
        with (
            patch.object(ai_generator_module, "is_ai_available", return_value=True),
            patch.object(ai_generator_module, "_get_strategy", return_value=strategy),
        ):
            generator.generate(GenerationRequest(prompt="pure prompt", add_looping=False))
        prompt_arg = strategy.generate_audio.call_args[0][0]
        assert prompt_arg == "pure prompt"

    def test_generation_forwards_lyrics_kwarg(self, tmp_path, monkeypatch) -> None:
        generator, _ = self._generator()
        strategy = make_strategy()
        strategy.config.supports_lyrics = True
        install_fake_scipy(monkeypatch)
        with (
            patch.object(ai_generator_module, "is_ai_available", return_value=True),
            patch.object(ai_generator_module, "_get_strategy", return_value=strategy),
        ):
            generator.generate(
                GenerationRequest(prompt="song", model_id="minimax-music3", lyrics="verse one")
            )
        kwargs = strategy.generate_audio.call_args[1]
        assert kwargs == {"lyrics": "verse one"}

    def test_generation_failure_returns_none(self, tmp_path, monkeypatch) -> None:
        generator, _ = self._generator()
        strategy = make_strategy()
        strategy.generate_audio.side_effect = RuntimeError("GPU OOM")
        install_fake_scipy(monkeypatch)
        with (
            patch.object(ai_generator_module, "is_ai_available", return_value=True),
            patch.object(ai_generator_module, "_get_strategy", return_value=strategy),
        ):
            assert generator.generate(GenerationRequest(prompt="beats")) is None


class TestGenerateForContext:
    def test_prompt_composition(self, tmp_path) -> None:
        config = MagicMock()
        config.get_default_ai_model.return_value = "m"
        generator = AIGenerator(output_dir=tmp_path / "o", config=config)

        captured = {}

        def fake_generate(request):
            captured["prompt"] = request.prompt
            return "track"

        with patch.object(generator, "generate", side_effect=fake_generate):
            generator.generate_for_context(mood_prompt="calm", temporal_prompt="morning")
            assert captured["prompt"] == "calm, morning"

            generator.generate_for_context(mood_prompt="energetic")
            assert captured["prompt"] == "energetic"

            generator.generate_for_context(temporal_prompt="night")
            assert captured["prompt"] == "night"

            generator.generate_for_context()
            assert captured["prompt"] == "ambient background music"


class TestCleanupAndHelpers:
    def test_cleanup_old_files_deletes_only_old(self, tmp_path) -> None:
        import os
        import time

        generator = AIGenerator(output_dir=tmp_path, config=MagicMock())
        old_file = tmp_path / "ai_music_old.wav"
        new_file = tmp_path / "ai_music_new.wav"
        old_file.write_bytes(b"old")
        new_file.write_bytes(b"new")
        two_days_ago = time.time() - 48 * 3600
        os.utime(old_file, (two_days_ago, two_days_ago))

        deleted = generator.cleanup_old_files(max_age_hours=24)
        assert deleted == 1
        assert not old_file.exists()
        assert new_file.exists()

    def test_cleanup_survives_unlink_errors(self, tmp_path, monkeypatch) -> None:
        generator = AIGenerator(output_dir=tmp_path, config=MagicMock())
        stale = tmp_path / "ai_music_stale.wav"
        stale.write_bytes(b"x")

        def refuse(self):
            raise OSError("busy")

        monkeypatch.setattr("pathlib.Path.unlink", refuse)
        assert generator.cleanup_old_files() == 0
        assert stale.exists()


def test_install_instructions_mention_both_extras() -> None:
    text = get_ai_install_instructions()
    assert "[ai]" in text
    assert "[minimax]" in text
