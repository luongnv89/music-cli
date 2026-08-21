"""HuggingFace cache utility tests (issue #72 — coverage raise).

``huggingface_hub`` is an optional extra, so the module degrades to
``HF_HUB_AVAILABLE = False``; the available paths are exercised by patching the
module-level flags and scan/download functions.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import music_cli.hf_cache as hf_cache_module
from music_cli.hf_cache import (
    CacheInfo,
    delete_model,
    download_model,
    format_size,
    get_hf_cache_dir,
    get_model_cache_info,
    is_available,
    is_model_downloaded,
    scan_all_cached_models,
)


@pytest.fixture()
def hf_unavailable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(hf_cache_module, "HF_HUB_AVAILABLE", False)
    return hf_unavailable


@pytest.fixture()
def hf_available(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(hf_cache_module, "HF_HUB_AVAILABLE", True)
    return hf_available


class TestFormatSize:
    @pytest.mark.parametrize(
        ("size_bytes", "expected"),
        [
            (512, "512 B"),
            (2048, "2.0 KB"),
            (5 * 1024 * 1024, "5.0 MB"),
            (3 * 1024**3, "3.0 GB"),
        ],
    )
    def test_formatting_buckets(self, size_bytes: int, expected: str) -> None:
        assert format_size(size_bytes) == expected


class TestAvailability:
    def test_is_available_reflects_flag(self, hf_available) -> None:
        assert is_available() is True

    def test_get_cache_dir_unavailable(self, hf_unavailable) -> None:
        assert get_hf_cache_dir() is None

    def test_get_cache_dir_success(self, hf_available, monkeypatch) -> None:
        monkeypatch.setattr(
            hf_cache_module,
            "scan_cache_dir",
            lambda: SimpleNamespace(cache_dir="/hf-home/cache"),
        )
        assert get_hf_cache_dir() == Path("/hf-home/cache")

    def test_get_cache_dir_scan_failure_returns_none(
        self, hf_available, monkeypatch, caplog
    ) -> None:
        def boom():
            raise RuntimeError("no cache")

        monkeypatch.setattr(hf_cache_module, "scan_cache_dir", boom)
        with caplog.at_level(logging.DEBUG):
            assert get_hf_cache_dir() is None


def make_repo(repo_id: str, repo_type: str = "model", size: int = 1024**3):
    return SimpleNamespace(
        repo_id=repo_id,
        repo_type=repo_type,
        size_on_disk=size,
        last_accessed=datetime(2026, 1, 1, tzinfo=None),
        repo_path=Path(f"/hf-home/cache/{repo_id}"),
        revisions=[SimpleNamespace(commit_hash="abc123")],
    )


class TestScanAllCachedModels:
    def test_unavailable_returns_empty(self, hf_unavailable) -> None:
        assert scan_all_cached_models() == {}

    def test_scans_and_filters_to_models_only(self, hf_available, monkeypatch) -> None:
        model_repo = make_repo("facebook/musicgen-small")
        dataset_repo = make_repo("some/dataset", repo_type="dataset")
        cache_info = SimpleNamespace(repos=[model_repo, dataset_repo])
        monkeypatch.setattr(hf_cache_module, "scan_cache_dir", lambda: cache_info)

        result = scan_all_cached_models()
        assert set(result) == {"facebook/musicgen-small"}
        info = result["facebook/musicgen-small"]
        assert isinstance(info, CacheInfo)
        assert info.size_gb == pytest.approx(1.0)
        assert info.repo_path == Path("/hf-home/cache/facebook/musicgen-small")

    def test_scan_failure_returns_empty(self, hf_available, monkeypatch, caplog) -> None:
        def boom():
            raise RuntimeError("cache corrupt")

        monkeypatch.setattr(hf_cache_module, "scan_cache_dir", boom)
        with caplog.at_level(logging.WARNING):
            assert scan_all_cached_models() == {}
        assert any("Failed to scan" in r.message for r in caplog.records)


class TestModelLookup:
    def test_get_model_cache_info_hit(self, monkeypatch) -> None:
        info = CacheInfo(
            hf_model_id="m",
            size_bytes=1,
            size_gb=0.0,
            last_accessed=None,
            repo_path=Path("/x"),
        )
        monkeypatch.setattr(
            hf_cache_module, "scan_all_cached_models", lambda: {"m": info}
        )
        assert get_model_cache_info("m") is info

    def test_get_model_cache_info_miss(self, monkeypatch) -> None:
        monkeypatch.setattr(hf_cache_module, "scan_all_cached_models", lambda: {})
        assert get_model_cache_info("ghost") is None
        assert is_model_downloaded("ghost") is False

    def test_is_model_downloaded_hit(self, monkeypatch) -> None:
        info = CacheInfo(
            hf_model_id="m",
            size_bytes=1,
            size_gb=0.0,
            last_accessed=None,
            repo_path=Path("/x"),
        )
        monkeypatch.setattr(
            hf_cache_module, "scan_all_cached_models", lambda: {"m": info}
        )
        assert is_model_downloaded("m") is True


class TestDownloadModel:
    def test_unavailable_logs_error_and_fails(
        self, hf_unavailable, caplog
    ) -> None:
        with caplog.at_level(logging.ERROR):
            assert download_model("facebook/musicgen-small") is False
        assert any("not available" in r.message for r in caplog.records)

    def test_download_success_passes_revision(self, hf_available, monkeypatch) -> None:
        calls = []

        def fake_snapshot(repo_id, revision=None):
            calls.append((repo_id, revision))
            return "/hf-home/snapshot"

        monkeypatch.setattr(hf_cache_module, "snapshot_download", fake_snapshot)
        assert (
            download_model("facebook/musicgen-small", revision="deadbeef") is True
        )
        assert calls == [("facebook/musicgen-small", "deadbeef")]

    def test_http_error_is_caught(self, hf_available, monkeypatch, caplog) -> None:
        def boom(repo_id, revision=None):
            raise hf_cache_module.HfHubHTTPError("429 slow down")

        monkeypatch.setattr(hf_cache_module, "snapshot_download", boom)
        with caplog.at_level(logging.ERROR):
            assert download_model("m") is False
        assert any("HTTP error" in r.message for r in caplog.records)

    def test_generic_error_is_caught(self, hf_available, monkeypatch) -> None:
        def boom(repo_id, revision=None):
            raise OSError("network down")

        monkeypatch.setattr(hf_cache_module, "snapshot_download", boom)
        assert download_model("m") is False


class TestDeleteModel:
    def test_unavailable_fails(self, hf_unavailable) -> None:
        assert delete_model("m") == (False, 0)

    def _install_cache(self, monkeypatch, repos):
        cache_info = SimpleNamespace(repos=repos)
        monkeypatch.setattr(hf_cache_module, "scan_cache_dir", lambda: cache_info)
        return cache_info

    def test_delete_executes_strategy_for_revisions(
        self, hf_available, monkeypatch, caplog
    ) -> None:
        repo = make_repo("facebook/musicgen-small", size=5 * 1024**2)
        executed = []
        strategy = SimpleNamespace(execute=lambda: executed.append(True))
        cache_info = SimpleNamespace(
            repos=[repo],
            delete_revisions=lambda *hashes: strategy,
        )
        monkeypatch.setattr(hf_cache_module, "scan_cache_dir", lambda: cache_info)

        with caplog.at_level(logging.INFO):
            success, freed = delete_model("facebook/musicgen-small")
        assert (success, freed) == (True, 5 * 1024**2)
        assert executed == [True]
        assert any("Deleted facebook/musicgen-small" in r.message for r in caplog.records)

    def test_delete_missing_model_warns(
        self, hf_available, monkeypatch, caplog
    ) -> None:
        self._install_cache(monkeypatch, [make_repo("other/model")])
        with caplog.at_level(logging.WARNING):
            assert delete_model("ghost/model") == (False, 0)
        assert any("not found in cache" in r.message for r in caplog.records)

    def test_delete_without_revisions_fails(
        self, hf_available, monkeypatch
    ) -> None:
        repo = make_repo("facebook/musicgen-small")
        repo.revisions = []
        self._install_cache(monkeypatch, [repo])
        assert delete_model("facebook/musicgen-small") == (False, 0)

    def test_delete_failure_is_caught(self, hf_available, monkeypatch) -> None:
        def boom():
            raise RuntimeError("permissions")

        monkeypatch.setattr(hf_cache_module, "scan_cache_dir", boom)
        assert delete_model("m") == (False, 0)
