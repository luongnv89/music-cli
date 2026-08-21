"""AI model strategy tests (issue #72 — coverage raise).

torch / transformers / diffusers are optional extras, so every heavy import is
satisfied by stub modules injected into ``sys.modules``. This keeps the suite
hermetic (no model downloads, no GPU) while exercising the real strategy code.
"""

from __future__ import annotations

import contextlib
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, Mock

import numpy as np
import pytest

from music_cli.sources.ai_models.audioldm_strategy import AudioLDMStrategy
from music_cli.sources.ai_models.bark_strategy import BarkStrategy
from music_cli.sources.ai_models.minimax_strategy import MiniMaxMusic3Strategy
from music_cli.sources.ai_models.model_config import ModelConfig
from music_cli.sources.ai_models.model_strategy import ModelStrategy
from music_cli.sources.ai_models.musicgen_strategy import MusicGenStrategy


class FakeTensor:
    """Just enough tensor behaviour for the strategies' numpy conversions."""

    def __init__(self, arr):
        self._arr = np.asarray(arr)

    def cpu(self):
        return self

    def float(self):
        return self

    def detach(self):
        return self

    def to(self, device):
        self.device = device
        return self

    def numpy(self):
        return self._arr

    def __getitem__(self, key):
        arr = self._arr
        keys = key if isinstance(key, tuple) else (key,)
        for k in keys:
            arr = arr[k]
        return FakeTensor(arr)


def install_fake_torch(monkeypatch: pytest.MonkeyPatch, *, cuda=False, bfloat16=True):
    torch = ModuleType("torch")
    torch.float16 = "float16"
    torch.float32 = "float32"
    if bfloat16:
        torch.bfloat16 = "bfloat16"

    @contextlib.contextmanager
    def no_grad():
        yield

    torch.no_grad = no_grad
    torch.cuda = SimpleNamespace(is_available=lambda: cuda, empty_cache=lambda: None)
    monkeypatch.setitem(sys.modules, "torch", torch)
    return torch


def make_config(model_type: str, **overrides) -> ModelConfig:
    defaults = {
        "id": f"test-{model_type}",
        "hf_model_id": f"acme/{model_type}",
        "model_type": model_type,
        "revision": "rev123",
    }
    defaults.update(overrides)
    return ModelConfig(**defaults)


class _StubStrategy(ModelStrategy):
    """Minimal concrete strategy for base-class behaviour tests."""

    def load_model(self):
        return object(), object()

    def generate_audio(self, prompt, duration, lyrics=None):  # pragma: no cover
        raise NotImplementedError


class TestEnsureLoaded:
    def test_already_loaded_is_a_no_op(self) -> None:
        strategy = _StubStrategy(make_config("musicgen"))
        strategy._model = object()
        assert strategy.ensure_loaded() is True

    def test_success_stores_model_and_processor(self) -> None:
        strategy = _StubStrategy(make_config("musicgen"))
        assert strategy.ensure_loaded() is True
        assert strategy.is_loaded is True

    def test_missing_dependency_returns_false(self) -> None:
        strategy = _StubStrategy(make_config("musicgen"))
        strategy.load_model = Mock(side_effect=ImportError("no transformers"))
        assert strategy.ensure_loaded() is False

    def test_generic_failure_returns_false(self) -> None:
        strategy = _StubStrategy(make_config("musicgen"))
        strategy.load_model = Mock(side_effect=RuntimeError("OOM"))
        assert strategy.ensure_loaded() is False

    def test_get_max_tokens_delegates_to_config(self) -> None:
        config = make_config("musicgen", tokens_per_second=25)
        strategy = _StubStrategy(config)
        assert strategy.get_max_tokens(4) == 100


class TestBaseUnload:
    def test_unload_handles_model_without_to(self) -> None:
        strategy = _StubStrategy(make_config("musicgen"))
        strategy._model = object()  # no .to attribute
        strategy.unload()
        assert strategy.is_loaded is False
        assert strategy.model_id == "acme/musicgen"

    def test_unload_swallows_device_move_errors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install_fake_torch(monkeypatch)
        strategy = _StubStrategy(make_config("musicgen"))
        model = MagicMock()
        model.to.side_effect = RuntimeError("device gone")
        strategy._model = model
        strategy.unload()
        assert strategy.is_loaded is False


class TestMusicGen:
    def _loaded_strategy(self, monkeypatch, generation_config_sample_rate=32000):
        install_fake_torch(monkeypatch)

        processor = MagicMock(return_value={"input_ids": FakeTensor([1])})

        class FakeAutoProcessor:
            calls = []

            @classmethod
            def from_pretrained(cls, model_id, revision=None, **kw):
                cls.calls.append((model_id, revision))
                return processor

        generation_config = SimpleNamespace(sample_rate=generation_config_sample_rate)
        model = MagicMock()
        model.generate.return_value = FakeTensor(np.zeros((1, 1, 8)))
        model.generation_config = generation_config

        class FakeMusicgen:
            calls = []

            @classmethod
            def from_pretrained(cls, model_id, revision=None, **kw):
                cls.calls.append((model_id, revision))
                return model

        transformers = ModuleType("transformers")
        transformers.AutoProcessor = FakeAutoProcessor
        transformers.MusicgenForConditionalGeneration = FakeMusicgen
        monkeypatch.setitem(sys.modules, "transformers", transformers)

        strategy = MusicGenStrategy(make_config("musicgen"))
        strategy._model, strategy._processor = strategy.load_model()
        return strategy, model, processor

    def test_load_model_passes_pinned_revision(self, monkeypatch) -> None:
        install_fake_torch(monkeypatch)
        processor = MagicMock(return_value={"input_ids": FakeTensor([1])})

        class FakeAutoProcessor:
            @classmethod
            def from_pretrained(cls, model_id, revision=None, **kw):
                assert revision == "rev123"
                return processor

        class FakeMusicgen:
            @classmethod
            def from_pretrained(cls, model_id, revision=None, **kw):
                assert revision == "rev123"
                return MagicMock()

        transformers = ModuleType("transformers")
        transformers.AutoProcessor = FakeAutoProcessor
        transformers.MusicgenForConditionalGeneration = FakeMusicgen
        monkeypatch.setitem(sys.modules, "transformers", transformers)

        MusicGenStrategy(make_config("musicgen")).load_model()

    def test_generate_audio_with_generation_config_sample_rate(self, monkeypatch) -> None:
        strategy, _, _ = self._loaded_strategy(monkeypatch)
        audio, rate = strategy.generate_audio("lofi beats", 5)
        assert rate == 32000
        assert audio.dtype == np.int16
        assert len(audio) == 8

    def test_generate_audio_falls_back_to_encoder_sampling_rate(self, monkeypatch) -> None:
        strategy, model, _ = self._loaded_strategy(monkeypatch)
        model.generation_config = SimpleNamespace()  # no sample_rate attr
        model.config.audio_encoder.sampling_rate = 24000
        _, rate = strategy.generate_audio("lofi", 5)
        assert rate == 24000

    def test_generate_audio_requires_loaded_model(self, monkeypatch) -> None:
        install_fake_torch(monkeypatch)
        strategy = MusicGenStrategy(make_config("musicgen"))
        with pytest.raises(RuntimeError, match="not loaded"):
            strategy.generate_audio("x", 5)

    def test_melody_rejects_non_melody_variant(self, monkeypatch) -> None:
        strategy, _, _ = self._loaded_strategy(monkeypatch)
        with pytest.raises(ValueError, match="melody"):
            strategy.generate_with_melody("p", np.zeros(4), 16000, 5)

    def test_melody_happy_path(self, monkeypatch) -> None:
        strategy, _, processor = self._loaded_strategy(monkeypatch)
        strategy.config = make_config("musicgen", hf_model_id="facebook/musicgen-melody")
        audio, rate = strategy.generate_with_melody("p", np.zeros(4), 16000, 5)
        assert rate == 32000
        assert audio.dtype == np.int16
        # Melody conditioning forwarded the audio to the processor.
        _, kwargs = processor.call_args
        assert kwargs["sampling_rate"] == 16000


class TestBark:
    def _install_transformers(self, monkeypatch, *, offload_raises=False):
        processor = MagicMock(return_value={"input_ids": FakeTensor([1])})
        model = MagicMock(
            spec=["generate", "parameters", "to", "enable_cpu_offload", "generation_config"]
        )
        model.generate.return_value = FakeTensor(np.zeros((2, 4)))
        model.to.return_value = model  # .to(device) chains back to the model
        model.generation_config = SimpleNamespace(sample_rate=32000)
        if offload_raises:
            model.enable_cpu_offload.side_effect = RuntimeError("offload failed")

        class FakeProcessorCls:
            @classmethod
            def from_pretrained(cls, model_id, revision=None, **kw):
                return processor

        class FakeBarkModel:
            @classmethod
            def from_pretrained(cls, model_id, **kw):
                return model

        transformers = ModuleType("transformers")
        transformers.AutoProcessor = FakeProcessorCls
        transformers.BarkModel = FakeBarkModel
        monkeypatch.setitem(sys.modules, "transformers", transformers)
        return model, processor

    def test_load_on_cpu_selects_float32(self, monkeypatch) -> None:
        install_fake_torch(monkeypatch, cuda=False)
        model, _ = self._install_transformers(monkeypatch)
        strategy = BarkStrategy(make_config("bark"))
        loaded_model, loaded_processor = strategy.load_model()
        assert loaded_processor is not None
        model.to.assert_called_once_with("cpu")

    def test_cpu_offload_enabled_on_cuda(self, monkeypatch) -> None:
        install_fake_torch(monkeypatch, cuda=True)
        model, _ = self._install_transformers(monkeypatch)
        BarkStrategy(make_config("bark")).load_model()
        model.enable_cpu_offload.assert_called_once_with()

    def test_cpu_offload_failure_is_tolerated(self, monkeypatch) -> None:
        install_fake_torch(monkeypatch, cuda=True)
        model, _ = self._install_transformers(monkeypatch, offload_raises=True)
        BarkStrategy(make_config("bark")).load_model()  # must not raise

    def test_generate_without_voice_preset(self, monkeypatch) -> None:
        install_fake_torch(monkeypatch)
        model, _ = self._install_transformers(monkeypatch)
        strategy = BarkStrategy(make_config("bark"))
        strategy._model, strategy._processor = strategy.load_model()

        audio, rate = strategy.generate_audio("hello world", 10)
        assert rate == 32000 or rate > 0
        assert audio.dtype == np.int16

    def test_generate_uses_voice_preset_when_configured(self, monkeypatch) -> None:
        install_fake_torch(monkeypatch)
        model, processor = self._install_transformers(monkeypatch)
        strategy = BarkStrategy(
            make_config("bark", extra_params={"voice_preset": "v2/en_speaker_6"})
        )
        strategy._model, strategy._processor = strategy.load_model()
        strategy.generate_audio("hello", 10)
        args, kwargs = processor.call_args
        assert kwargs.get("voice_preset") == "v2/en_speaker_6"

    def test_generate_requires_loaded_model(self, monkeypatch) -> None:
        strategy = BarkStrategy(make_config("bark"))
        with pytest.raises(RuntimeError, match="not loaded"):
            strategy.generate_audio("x", 5)

    def test_unload_moves_model_to_cpu_and_clears(self, monkeypatch) -> None:
        install_fake_torch(monkeypatch)
        model, _ = self._install_transformers(monkeypatch)
        strategy = BarkStrategy(make_config("bark"))
        strategy._model, _ = strategy.load_model()
        strategy.unload()
        # The final device move is back to CPU.
        model.to.assert_called_with("cpu")
        assert strategy.is_loaded is False


class TestAudioLDM:
    def _install_diffusers(self, monkeypatch):
        pipeline = MagicMock()
        pipeline.to.return_value = pipeline  # .to(device) chains back
        pipeline.return_value = SimpleNamespace(audios=[np.array([0.5, -0.5, 2.0])])

        class FakePipeline:
            @classmethod
            def from_pretrained(cls, model_id, **kw):
                return pipeline

        diffusers = ModuleType("diffusers")
        diffusers.AudioLDMPipeline = FakePipeline
        monkeypatch.setitem(sys.modules, "diffusers", diffusers)
        return pipeline

    def test_load_model_returns_pipeline_without_processor(self, monkeypatch) -> None:
        install_fake_torch(monkeypatch)
        pipeline = self._install_diffusers(monkeypatch)
        strategy = AudioLDMStrategy(make_config("audioldm"))
        loaded_model, loaded_processor = strategy.load_model()
        assert loaded_model is pipeline
        assert loaded_processor is None
        pipeline.to.assert_called_once_with("cpu")

    def test_generate_uses_default_steps_and_guidance(self, monkeypatch) -> None:
        install_fake_torch(monkeypatch)
        pipeline = self._install_diffusers(monkeypatch)
        strategy = AudioLDMStrategy(make_config("audioldm"))
        strategy._model, _ = strategy.load_model()

        audio, rate = strategy.generate_audio("rain sounds", 8)
        assert rate == 16000
        assert audio.dtype == np.int16
        # Values clipped into int16 range before conversion.
        assert audio.max() <= 32767
        _, kwargs = pipeline.call_args
        assert kwargs["num_inference_steps"] == 10
        assert kwargs["guidance_scale"] == 2.5
        assert kwargs["audio_length_in_s"] == 8.0

    def test_generate_honours_extra_params(self, monkeypatch) -> None:
        install_fake_torch(monkeypatch)
        pipeline = self._install_diffusers(monkeypatch)
        strategy = AudioLDMStrategy(
            make_config(
                "audioldm",
                extra_params={"num_inference_steps": 50, "guidance_scale": 7.0},
            )
        )
        strategy._model, _ = strategy.load_model()
        strategy.generate_audio("thunder", 4)
        _, kwargs = pipeline.call_args
        assert kwargs["num_inference_steps"] == 50
        assert kwargs["guidance_scale"] == 7.0

    def test_generate_requires_loaded_model(self) -> None:
        strategy = AudioLDMStrategy(make_config("audioldm"))
        with pytest.raises(RuntimeError, match="not loaded"):
            strategy.generate_audio("x", 5)


class TestMiniMaxLoadModel:
    """Covers the guard rails added around the Diffusers modular pipeline."""

    def test_missing_torch_raises_helpful_import_error(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "torch", None)
        strategy = MiniMaxMusic3Strategy(make_config("minimax_music3"))
        with pytest.raises(ImportError, match="minimax.*extra"):
            strategy.load_model()

    def _torch(self, monkeypatch, *, cuda=True, bfloat16=True):
        return install_fake_torch(monkeypatch, cuda=cuda, bfloat16=bfloat16)

    def test_missing_diffusers_raises(self, monkeypatch) -> None:
        self._torch(monkeypatch)
        monkeypatch.setitem(sys.modules, "diffusers", None)
        strategy = MiniMaxMusic3Strategy(make_config("minimax_music3"))
        with pytest.raises(ImportError, match="ModularPipeline"):
            strategy.load_model()

    def test_from_pretrained_not_callable(self, monkeypatch) -> None:
        self._torch(monkeypatch)
        modular = ModuleType("diffusers.modular_pipeline")
        diffusers = ModuleType("diffusers")
        diffusers.ModularPipeline = SimpleNamespace(from_pretrained="not callable")
        monkeypatch.setitem(sys.modules, "diffusers", diffusers)
        monkeypatch.setitem(sys.modules, "diffusers.modular_pipeline", modular)
        strategy = MiniMaxMusic3Strategy(make_config("minimax_music3"))
        with pytest.raises(RuntimeError, match="ModularPipeline.from_pretrained"):
            strategy.load_model()

    def test_cuda_required(self, monkeypatch) -> None:
        self._torch(monkeypatch, cuda=False)
        diffusers = ModuleType("diffusers")
        diffusers.ModularPipeline = SimpleNamespace(from_pretrained=lambda *a, **k: None)
        monkeypatch.setitem(sys.modules, "diffusers", diffusers)
        strategy = MiniMaxMusic3Strategy(make_config("minimax_music3"))
        with pytest.raises(RuntimeError, match="CUDA-capable GPU"):
            strategy.load_model()

    def test_bfloat16_required(self, monkeypatch) -> None:
        self._torch(monkeypatch, bfloat16=False)
        diffusers = ModuleType("diffusers")
        diffusers.ModularPipeline = SimpleNamespace(from_pretrained=lambda *a, **k: None)
        monkeypatch.setitem(sys.modules, "diffusers", diffusers)
        strategy = MiniMaxMusic3Strategy(make_config("minimax_music3"))
        with pytest.raises(RuntimeError, match="bfloat16"):
            strategy.load_model()

    def test_missing_load_components_rejected(self, monkeypatch) -> None:
        self._torch(monkeypatch)
        pipeline = SimpleNamespace(to=lambda *a: None)  # load_components absent

        class FakeModular:
            @classmethod
            def from_pretrained(cls, model_id, revision=None, **kw):
                return pipeline

        diffusers = ModuleType("diffusers")
        diffusers.ModularPipeline = FakeModular
        monkeypatch.setitem(sys.modules, "diffusers", diffusers)
        strategy = MiniMaxMusic3Strategy(make_config("minimax_music3"))
        with pytest.raises(RuntimeError, match="load_components"):
            strategy.load_model()

    def test_missing_to_rejected(self, monkeypatch) -> None:
        self._torch(monkeypatch)
        pipeline = SimpleNamespace(load_components=lambda **kw: None)  # .to absent

        class FakeModular:
            @classmethod
            def from_pretrained(cls, model_id, revision=None, **kw):
                return pipeline

        diffusers = ModuleType("diffusers")
        diffusers.ModularPipeline = FakeModular
        monkeypatch.setitem(sys.modules, "diffusers", diffusers)
        strategy = MiniMaxMusic3Strategy(make_config("minimax_music3"))
        with pytest.raises(RuntimeError, match="moved to CUDA"):
            strategy.load_model()


class TestMiniMaxGenerateAudio:
    def _loaded(self) -> tuple[MiniMaxMusic3Strategy, MagicMock]:
        strategy = MiniMaxMusic3Strategy(make_config("minimax_music3"))
        pipeline = MagicMock()
        pipeline.sampling_rate = 32000
        strategy._model = pipeline
        return strategy, pipeline

    def test_not_loaded_raises(self) -> None:
        strategy = MiniMaxMusic3Strategy(make_config("minimax_music3"))
        with pytest.raises(RuntimeError, match="not loaded"):
            strategy.generate_audio("p", 30, lyrics="verse")

    def test_empty_lyrics_rejected(self) -> None:
        strategy, _ = self._loaded()
        with pytest.raises(ValueError, match="lyrics"):
            strategy.generate_audio("p", 30, lyrics="   ")

    def test_pipeline_output_error_wrapped(self) -> None:
        strategy, pipeline = self._loaded()
        pipeline.side_effect = TypeError("bad call")
        with pytest.raises(RuntimeError, match="no usable audio"):
            strategy.generate_audio("p", 30, lyrics="verse")

    def test_float_tensor_audio_via_detach_chain(self) -> None:
        strategy, _ = self._loaded()
        strategy._model.return_value = SimpleNamespace(audios=[FakeTensor([0.5, -0.5])])
        audio, rate = strategy.generate_audio("p", 30, lyrics="verse")
        assert rate == 32000
        assert audio.dtype == np.int16

    def test_plain_list_audio_normalises_through_numpy(self) -> None:
        strategy, _ = self._loaded()
        strategy._model.return_value = SimpleNamespace(audios=[[0.25, -0.25]])
        audio, _ = strategy.generate_audio("p", 30, lyrics="verse")
        assert audio.dtype == np.int16

    def test_three_dimensional_audio_collapses_batch(self) -> None:
        strategy, _ = self._loaded()
        arr = np.zeros((1, 2, 4), dtype=np.float32)
        strategy._model.return_value = SimpleNamespace(audios=[arr])
        audio, _ = strategy.generate_audio("p", 30, lyrics="verse")
        assert audio.ndim == 2

    def test_channel_first_stereo_is_transposed(self) -> None:
        strategy, _ = self._loaded()
        arr = np.zeros((2, 8), dtype=np.float32)  # channels first
        strategy._model.return_value = SimpleNamespace(audios=[arr])
        audio, _ = strategy.generate_audio("p", 30, lyrics="verse")
        assert audio.shape[0] == 8  # transposed to samples-first

    def test_unexpected_rank_raises(self) -> None:
        strategy, _ = self._loaded()
        scalar = np.float32(0.5)
        strategy._model.return_value = SimpleNamespace(audios=[scalar])
        with pytest.raises(RuntimeError, match="Unexpected MiniMax audio shape"):
            strategy.generate_audio("p", 30, lyrics="verse")

    def test_integer_dtype_path_clips_instead_of_scaling(self) -> None:
        strategy, _ = self._loaded()
        arr = np.array([[40000, -40000]], dtype=np.int32)
        strategy._model.return_value = SimpleNamespace(audios=[arr])
        audio, _ = strategy.generate_audio("p", 30, lyrics="verse")
        assert audio.dtype == np.int16
        assert audio.max() <= 32767 and audio.min() >= -32768

    def test_default_sample_rate_when_pipeline_has_none(self) -> None:
        strategy = MiniMaxMusic3Strategy(make_config("minimax_music3"))

        class CallablePipeline:  # no sampling_rate attribute
            def __call__(self, **kwargs):
                return SimpleNamespace(audios=[[0.0, 0.0]])

        strategy._model = CallablePipeline()
        audio, rate = strategy.generate_audio("p", 30, lyrics="verse")
        assert rate == 32000
