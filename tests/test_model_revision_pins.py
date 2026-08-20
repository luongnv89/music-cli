"""Tests for pinned HuggingFace model revisions in the model registry."""

import re
from unittest.mock import Mock

from music_cli import hf_cache
from music_cli.sources.ai_models.model_config import (
    DEFAULT_AI_MODELS_CONFIG,
    AIModelsConfig,
    ModelConfig,
)

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def test_every_registered_model_pins_a_commit_sha() -> None:
    """All registry models must pin a full 40-char commit SHA revision."""
    for model_id, data in DEFAULT_AI_MODELS_CONFIG["models"].items():
        revision = data.get("revision")
        assert revision, f"Model '{model_id}' has no pinned revision"
        assert SHA_RE.match(revision), f"Model '{model_id}' revision is not a SHA: {revision}"


def test_model_config_roundtrips_revision() -> None:
    config = ModelConfig(
        id="musicgen-small",
        hf_model_id="facebook/musicgen-small",
        model_type="musicgen",
        revision="4c8334b02c6ec4e8664a91979669a501ec497792",
    )
    data = config.to_dict()
    assert data["revision"] == "4c8334b02c6ec4e8664a91979669a501ec497792"

    restored = ModelConfig.from_dict("musicgen-small", data)
    assert restored.revision == "4c8334b02c6ec4e8664a91979669a501ec497792"


def test_model_config_revision_defaults_to_none() -> None:
    restored = ModelConfig.from_dict(
        "custom", {"hf_model_id": "example/custom", "model_type": "musicgen"}
    )
    assert restored.revision is None


def test_registry_configs_expose_pinned_revisions() -> None:
    parsed = AIModelsConfig.from_dict(DEFAULT_AI_MODELS_CONFIG)
    for model_id, config in parsed.models.items():
        assert config.revision and SHA_RE.match(config.revision), (
            f"Parsed model '{model_id}' lost its pinned revision"
        )


def test_download_model_forwards_registry_revision(monkeypatch) -> None:
    snapshot_download = Mock()
    monkeypatch.setattr(hf_cache, "HF_HUB_AVAILABLE", True)
    monkeypatch.setattr(hf_cache, "snapshot_download", snapshot_download)

    parsed = AIModelsConfig.from_dict(DEFAULT_AI_MODELS_CONFIG)
    config = parsed.get_model("musicgen-small")
    assert config is not None

    assert hf_cache.download_model(config.hf_model_id, revision=config.revision) is True
    snapshot_download.assert_called_once_with(
        repo_id="facebook/musicgen-small",
        revision="4c8334b02c6ec4e8664a91979669a501ec497792",
    )
