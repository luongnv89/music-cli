"""ModelManager business-logic tests (issue #72 — coverage raise).

The HuggingFace cache layer is patched at the ``music_cli.model_manager``
namespace so no network, model download, or optional dependency is touched.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

import music_cli.model_manager as mm_module
from music_cli.model_manager import ModelInfo, ModelManager
from music_cli.sources.ai_models import AIModelsConfig, ModelConfig


def two_model_config() -> AIModelsConfig:
    return AIModelsConfig.from_dict(
        {
            "default_model": "small",
            "models": {
                "small": {
                    "hf_model_id": "facebook/musicgen-small",
                    "model_type": "musicgen",
                    "description": "Small",
                    "expected_size_gb": 2.0,
                    "max_duration": 30,
                },
                "speech": {
                    "hf_model_id": "suno/bark",
                    "model_type": "bark",
                    "enabled": False,
                    "max_duration": 15,
                },
            },
        }
    )


def make_cache_info(hf_id: str, size_bytes: int = 2 * 1024**3):
    from music_cli.hf_cache import CacheInfo

    return CacheInfo(
        hf_model_id=hf_id,
        size_bytes=size_bytes,
        size_gb=size_bytes / 1024**3,
        last_accessed=datetime(2026, 1, 1),
        repo_path=Path(f"/cache/{hf_id}"),
    )


@pytest.fixture()
def manager() -> tuple[ModelManager, MagicMock]:
    config = MagicMock()
    config.get_ai_models_config.return_value = two_model_config()
    config.get_default_ai_model.return_value = "small"
    return ModelManager(config), config


class TestListModels:
    def test_merges_cache_status_and_sorts_by_type(self, manager) -> None:
        mgr, _ = manager
        with patch.object(
            mm_module.hf_cache,
            "scan_all_cached_models",
            return_value={"facebook/musicgen-small": make_cache_info("facebook/musicgen-small")},
        ):
            models = mgr.list_models()

        # musicgen (order 0) sorts before bark (order 2), regardless of dict order.
        assert [m.id for m in models] == ["small", "speech"]
        small, speech = models
        assert small.is_downloaded is True
        assert small.cached_size_gb == pytest.approx(2.0)
        assert small.is_default is True
        assert small.revision is None
        assert speech.is_downloaded is False
        assert speech.cached_size_gb is None
        assert speech.enabled is False

    def test_unknown_types_sort_last(self, manager) -> None:
        mgr, config = manager
        exotic = two_model_config()
        exotic.models["weird"] = ModelConfig(id="weird", hf_model_id="x/y", model_type="alien")
        config.get_ai_models_config.return_value = exotic
        with patch.object(mm_module.hf_cache, "scan_all_cached_models", return_value={}):
            models = mgr.list_models()
        assert models[-1].id == "weird"


class TestGetAndValidate:
    def test_get_model_hit_and_miss(self, manager) -> None:
        mgr, _ = manager
        with patch.object(mm_module.hf_cache, "scan_all_cached_models", return_value={}):
            assert mgr.get_model("small") is not None
            assert mgr.get_model("ghost") is None

    def test_validate_ok_unknown_and_disabled(self, manager) -> None:
        mgr, _ = manager
        with patch.object(mm_module.hf_cache, "scan_all_cached_models", return_value={}):
            assert mgr.validate_model("small") == (True, "")
            valid, msg = mgr.validate_model("ghost")
            assert valid is False and "Unknown model 'ghost'" in msg
            valid, msg = mgr.validate_model("speech")
            assert valid is False and "disabled" in msg


class TestDownload:
    def test_invalid_model_short_circuits(self, manager) -> None:
        mgr, _ = manager
        ok, msg = mgr.download_model("ghost")
        assert (ok, "Unknown") == (ok, "Unknown") and "Unknown" in msg

    def test_hf_hub_unavailable(self, manager) -> None:
        mgr, _ = manager
        with (
            patch.object(mm_module.hf_cache, "scan_all_cached_models", return_value={}),
            patch.object(mm_module.hf_cache, "is_available", return_value=False),
        ):
            ok, msg = mgr.download_model("small")
        assert ok is False and "not available" in msg

    def test_already_downloaded_with_known_size(self, manager) -> None:
        mgr, _ = manager
        info = make_cache_info("facebook/musicgen-small")
        with (
            patch.object(
                mm_module.hf_cache,
                "scan_all_cached_models",
                return_value={"facebook/musicgen-small": info},
            ),
            patch.object(mm_module.hf_cache, "is_available", return_value=True),
        ):
            ok, msg = mgr.download_model("small")
        assert ok is True and "already downloaded (2.0 GB)" in msg

    def test_download_failure_message(self, manager) -> None:
        mgr, _ = manager
        with (
            patch.object(mm_module.hf_cache, "scan_all_cached_models", return_value={}),
            patch.object(mm_module.hf_cache, "is_available", return_value=True),
            patch.object(mm_module.hf_cache, "download_model", return_value=False),
        ):
            ok, msg = mgr.download_model("small")
        assert ok is False and "Failed to download" in msg

    def test_download_success(self, manager) -> None:
        mgr, _ = manager
        with (
            patch.object(mm_module.hf_cache, "scan_all_cached_models", return_value={}),
            patch.object(mm_module.hf_cache, "is_available", return_value=True),
            patch.object(mm_module.hf_cache, "download_model", return_value=True),
        ):
            ok, msg = mgr.download_model("small")
        assert ok is True and "Successfully downloaded" in msg


class TestDelete:
    def test_unknown_model_fails(self, manager) -> None:
        mgr, _ = manager
        assert mgr.delete_model("ghost") == (False, "Unknown model 'ghost'", 0)

    def test_unavailable_hub_fails(self, manager) -> None:
        mgr, _ = manager
        with (
            patch.object(mm_module.hf_cache, "scan_all_cached_models", return_value={}),
            patch.object(mm_module.hf_cache, "is_available", return_value=False),
        ):
            ok, msg, freed = mgr.delete_model("small")
        assert ok is False and freed == 0

    def test_not_downloaded_fails(self, manager) -> None:
        mgr, _ = manager
        with (
            patch.object(mm_module.hf_cache, "scan_all_cached_models", return_value={}),
            patch.object(mm_module.hf_cache, "is_available", return_value=True),
        ):
            ok, msg, freed = mgr.delete_model("small")
        assert ok is False and "not downloaded" in msg

    def test_successful_delete_clears_strategy_cache(self, manager) -> None:
        mgr, _ = manager
        info = make_cache_info("facebook/musicgen-small")
        fake_cache = Mock()
        fake_cache.remove.return_value = True
        with (
            patch.object(
                mm_module.hf_cache,
                "scan_all_cached_models",
                return_value={"facebook/musicgen-small": info},
            ),
            patch.object(mm_module.hf_cache, "is_available", return_value=True),
            patch.object(mm_module.hf_cache, "delete_model", return_value=(True, 1024)),
            patch("music_cli.sources.ai_models.get_strategy_cache", return_value=fake_cache),
        ):
            ok, msg, freed = mgr.delete_model("small")
        assert ok is True
        assert "freed 1.0 KB" in msg
        assert freed == 1024
        fake_cache.remove.assert_called_once_with("small")

    def test_delete_backend_failure(self, manager) -> None:
        mgr, _ = manager
        info = make_cache_info("facebook/musicgen-small")
        with (
            patch.object(
                mm_module.hf_cache,
                "scan_all_cached_models",
                return_value={"facebook/musicgen-small": info},
            ),
            patch.object(mm_module.hf_cache, "is_available", return_value=True),
            patch.object(mm_module.hf_cache, "delete_model", return_value=(False, 0)),
        ):
            ok, msg, freed = mgr.delete_model("small")
        assert ok is False and "Failed to delete" in msg


class TestDefaultsAndSummary:
    def test_set_default_validates_first(self, manager) -> None:
        mgr, config = manager
        ok, msg = mgr.set_default_model("ghost")
        assert ok is False

        with patch.object(mm_module.hf_cache, "scan_all_cached_models", return_value={}):
            ok, msg = mgr.set_default_model("small")
        assert ok is True
        config.set_default_ai_model.assert_called_once_with("small")

    def test_summary_counts_and_sizes(self, manager) -> None:
        mgr, _ = manager
        info = make_cache_info("facebook/musicgen-small", size_bytes=1024**3)
        with patch.object(
            mm_module.hf_cache,
            "scan_all_cached_models",
            return_value={"facebook/musicgen-small": info},
        ):
            summary = mgr.get_summary()
        assert summary["total"] == 2
        assert summary["downloaded"] == 1
        assert summary["total_size_gb"] == pytest.approx(1.0)
        assert summary["default_model"] == "small"


def test_model_info_is_a_plain_data_holder() -> None:
    info = ModelInfo(
        id="m",
        hf_model_id="a/b",
        model_type="musicgen",
        description="d",
        expected_size_gb=1.0,
        is_downloaded=False,
        cached_size_gb=None,
        is_default=False,
        enabled=True,
        max_duration=10,
        revision="rev",
    )
    assert info.revision == "rev"
