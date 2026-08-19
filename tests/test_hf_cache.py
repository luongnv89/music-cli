"""Tests for HuggingFace cache management utilities."""

from unittest.mock import Mock

from music_cli import hf_cache


def test_download_model_uses_supported_snapshot_download(monkeypatch) -> None:
    """Downloads should work with current huggingface_hub versions."""
    snapshot_download = Mock()
    monkeypatch.setattr(hf_cache, "HF_HUB_AVAILABLE", True)
    monkeypatch.setattr(hf_cache, "snapshot_download", snapshot_download)

    assert hf_cache.download_model("example/model") is True
    snapshot_download.assert_called_once_with(repo_id="example/model")


def test_download_model_returns_false_when_hub_is_unavailable(monkeypatch) -> None:
    """Missing optional Hub support should be reported without raising."""
    monkeypatch.setattr(hf_cache, "HF_HUB_AVAILABLE", False)

    assert hf_cache.download_model("example/model") is False
