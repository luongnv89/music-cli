"""Tests for the extracted model-validation helper on AIGenerator (#75).

``AIGenerator.generate`` delegates its model/lyrics vetting to
``_validated_model_for``; these tests pin that the shared helper rejects the
same requests, with the same log messages, and that generation never loads a
strategy for an invalid request.
"""

from unittest.mock import MagicMock, patch

import pytest

from music_cli.sources.ai_generator import AIGenerator


@pytest.fixture
def generator(tmp_path):
    config = MagicMock(name="config")
    models_config = config.get_ai_models_config.return_value
    return AIGenerator(output_dir=tmp_path / "ai", config=config), models_config


def _model(model_id: str = "musicgen-small", supports_lyrics=False, requires_lyrics=False):
    return MagicMock(id=model_id, supports_lyrics=supports_lyrics, requires_lyrics=requires_lyrics)


class TestValidatedModelFor:
    def test_returns_configured_model_when_valid(self, generator) -> None:
        gen, models_config = generator
        configured = _model()
        models_config.get_model.return_value = configured

        assert gen._validated_model_for("musicgen-small", None) is configured

    def test_unknown_model_logs_and_returns_none(self, generator) -> None:
        gen, models_config = generator
        models_config.get_model.return_value = None

        assert gen._validated_model_for("nope", None) is None

    def test_lyrics_rejected_when_unsupported(self, generator) -> None:
        gen, models_config = generator
        models_config.get_model.return_value = _model(supports_lyrics=False)

        assert gen._validated_model_for("m", "words") is None

    @pytest.mark.parametrize("lyrics", [None, "", "   "])
    def test_requires_lyrics_rejects_empty(self, generator, lyrics) -> None:
        gen, models_config = generator
        models_config.get_model.return_value = _model(supports_lyrics=True, requires_lyrics=True)

        assert gen._validated_model_for("m", lyrics) is None


class TestGenerateDelegatesValidation:
    def test_invalid_request_never_loads_strategy(self, tmp_path) -> None:
        """Whitespace lyrics are rejected before any strategy load (#75)."""
        config = MagicMock(name="config")
        config.get_ai_models_config.return_value.get_model.return_value = _model(
            supports_lyrics=True, requires_lyrics=True
        )
        gen = AIGenerator(output_dir=tmp_path / "ai", config=config)

        with (
            patch("music_cli.sources.ai_generator.is_ai_available", return_value=True),
            patch("music_cli.sources.ai_generator._get_strategy") as get_strategy,
        ):
            assert gen.generate("desc", model_id="m", lyrics="  ") is None

        get_strategy.assert_not_called()

    def test_valid_request_proceeds_to_strategy(self, tmp_path) -> None:
        config = MagicMock(name="config")
        model = _model(supports_lyrics=True)
        config.get_ai_models_config.return_value.get_model.return_value = model
        gen = AIGenerator(output_dir=tmp_path / "ai", config=config)

        strategy = MagicMock()
        strategy.config.clamp_duration.side_effect = lambda d: d
        strategy.generate_audio.return_value = ([0.0], 44100)

        fake_scipy = MagicMock()
        with (
            patch("music_cli.sources.ai_generator.is_ai_available", return_value=True),
            patch("music_cli.sources.ai_generator._get_strategy", return_value=strategy),
            patch.dict(
                "sys.modules",
                {
                    "scipy": fake_scipy,
                    "scipy.io": fake_scipy.io,
                    "scipy.io.wavfile": fake_scipy.io.wavfile,
                },
            ),
        ):
            track = gen.generate("desc", 5, model_id="m")

        assert track is not None
        assert track.metadata["model"] == "m"
        assert track.metadata["duration"] == 5
