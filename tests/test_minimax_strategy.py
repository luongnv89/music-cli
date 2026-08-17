"""Contract tests for the MiniMax Music 3 integration."""

import asyncio
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import numpy as np
import pytest

from music_cli.client import DaemonClient
from music_cli.config import Config
from music_cli.daemon import MusicDaemon
from music_cli.player.base import TrackInfo
from music_cli.sources.ai_generator import AIGenerator
from music_cli.sources.ai_models import ModelRegistry
from music_cli.sources.ai_models.minimax_strategy import MiniMaxMusic3Strategy
from music_cli.sources.ai_models.model_config import ModelConfig


def minimax_config() -> ModelConfig:
    return ModelConfig(
        id="minimax-music3",
        hf_model_id="MiniMaxAI/MiniMax-Music3",
        model_type="minimax_music3",
        supports_lyrics=True,
        requires_lyrics=True,
        min_duration=5,
        max_duration=300,
    )


def test_minimax_is_a_builtin_model(tmp_path) -> None:
    config = Config(config_dir=tmp_path)
    model = config.get_ai_models_config().get_model("minimax-music3")

    assert model is not None
    assert model.hf_model_id == "MiniMaxAI/MiniMax-Music3"
    assert model.model_type == "minimax_music3"
    assert model.supports_lyrics is True
    assert model.requires_lyrics is True
    assert isinstance(ModelRegistry.create_strategy(model), MiniMaxMusic3Strategy)


def test_missing_modular_pipeline_reports_dependency_error() -> None:
    module = ModuleType("diffusers")
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True))
    with patch.dict("sys.modules", {"diffusers": module, "torch": fake_torch}):
        with pytest.raises(ImportError, match="ModularPipeline"):
            MiniMaxMusic3Strategy(minimax_config()).load_model()


def test_load_model_requires_cuda() -> None:
    fake_diffusers = SimpleNamespace(ModularPipeline=Mock())
    fake_torch = SimpleNamespace(
        bfloat16=object(), cuda=SimpleNamespace(is_available=lambda: False)
    )

    with patch.dict("sys.modules", {"diffusers": fake_diffusers, "torch": fake_torch}):
        with pytest.raises(RuntimeError, match="CUDA-capable GPU"):
            MiniMaxMusic3Strategy(minimax_config()).load_model()


def test_load_model_uses_official_pipeline_contract() -> None:
    pipeline = Mock()
    pipeline.load_components = Mock()
    pipeline.to = Mock()
    modular_pipeline = Mock()
    modular_pipeline.from_pretrained.return_value = pipeline
    fake_diffusers = SimpleNamespace(ModularPipeline=modular_pipeline)
    fake_torch = SimpleNamespace(
        bfloat16=object(), cuda=SimpleNamespace(is_available=lambda: True)
    )

    with patch.dict("sys.modules", {"diffusers": fake_diffusers, "torch": fake_torch}):
        loaded, processor = MiniMaxMusic3Strategy(minimax_config()).load_model()

    assert loaded is pipeline
    assert processor is None
    modular_pipeline.from_pretrained.assert_called_once_with("MiniMaxAI/MiniMax-Music3")
    pipeline.load_components.assert_called_once_with(dtype=fake_torch.bfloat16)
    pipeline.to.assert_called_once_with("cuda")


def test_generate_audio_passes_lyrics_and_normalizes_audio() -> None:
    pipeline = Mock()
    pipeline.sampling_rate = 32000
    pipeline.return_value = [np.array([[-1.0, 0.0, 1.0], [0.5, -0.5, 0.0]])]
    strategy = MiniMaxMusic3Strategy(minimax_config())
    strategy._model = pipeline

    audio, sample_rate = strategy.generate_audio("warm acoustic pop", 60, lyrics="[Verse] hello")

    assert sample_rate == 32000
    assert audio.shape == (3, 2)
    assert audio.dtype == np.int16
    pipeline.assert_called_once_with(
        prompt="warm acoustic pop",
        lyrics="[Verse] hello",
        audio_duration=60.0,
        output="audios",
    )


def test_generate_audio_reads_diffusers_audio_output() -> None:
    pipeline = Mock()
    pipeline.sampling_rate = 32000
    pipeline.return_value = SimpleNamespace(audios=[np.zeros((2, 4), dtype=np.float32)])
    strategy = MiniMaxMusic3Strategy(minimax_config())
    strategy._model = pipeline

    audio, sample_rate = strategy.generate_audio("description", 5, lyrics="lyrics")

    assert sample_rate == 32000
    assert audio.shape == (4, 2)
    assert audio.dtype == np.int16


def test_daemon_client_preserves_empty_lyrics_for_validation() -> None:
    client = object.__new__(DaemonClient)
    with patch.object(client, "send_command", return_value={}) as send_command:
        client.ai_play(model="minimax-music3", lyrics="")

    assert send_command.call_args.args[1]["lyrics"] == ""


def test_generator_rejects_whitespace_lyrics_before_loading(tmp_path) -> None:
    generator = AIGenerator(output_dir=tmp_path / "generated", config=Config(config_dir=tmp_path))
    with (
        patch("music_cli.sources.ai_generator.is_ai_available", return_value=True),
        patch("music_cli.sources.ai_generator._get_strategy") as get_strategy,
    ):
        assert generator.generate("description", model_id="minimax-music3", lyrics="  ") is None

    get_strategy.assert_not_called()


def test_daemon_persists_effective_duration_and_lyrics(tmp_path) -> None:
    daemon = object.__new__(MusicDaemon)
    daemon.config = Config(config_dir=tmp_path)
    daemon.ai_tracks = MagicMock()
    daemon.history = MagicMock()
    daemon.player = MagicMock()
    daemon.player.play = AsyncMock(return_value=True)
    daemon.temporal = MagicMock()
    daemon.temporal.get_time_period.return_value.value = "afternoon"
    daemon._current_mood = None
    generated = TrackInfo(
        source=str(tmp_path / "minimax.wav"),
        source_type="ai",
        title="AI track",
        metadata={"model": "minimax-music3", "duration": 5},
    )
    generator = MagicMock()
    generator.generate.return_value = generated

    with (
        patch("music_cli.sources.ai_generator.is_ai_available", return_value=True),
        patch("music_cli.sources.ai_generator.AIGenerator", return_value=generator),
    ):
        response = asyncio.run(
            daemon._cmd_ai_play(
                {
                    "model": "minimax-music3",
                    "prompt": "description",
                    "duration": 2,
                    "lyrics": "lyrics",
                }
            )
        )

    assert response["status"] == "playing"
    saved = daemon.ai_tracks.add_track.call_args.kwargs
    assert saved["duration"] == 5
    assert saved["lyrics"] == "lyrics"


def test_daemon_rejects_whitespace_lyrics_before_generation(tmp_path) -> None:
    daemon = object.__new__(MusicDaemon)
    daemon.config = Config(config_dir=tmp_path)
    with patch("music_cli.sources.ai_generator.is_ai_available", return_value=True):
        response = asyncio.run(
            daemon._cmd_ai_play(
                {"model": "minimax-music3", "prompt": "description", "lyrics": "  "}
            )
        )

    assert response == {"error": "Model 'minimax-music3' requires non-empty lyrics"}


def test_generate_audio_requires_non_empty_lyrics() -> None:
    strategy = MiniMaxMusic3Strategy(minimax_config())
    strategy._model = Mock()

    with pytest.raises(ValueError, match="non-empty lyrics"):
        strategy.generate_audio("description", 60, lyrics="  ")
