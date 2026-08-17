"""Regression tests for lazy AI model imports.

These tests verify that importing core ai_models types (ModelConfig,
AIModelsConfig, ModelRegistry, ModelStrategy, LRUStrategyCache) does not
require numpy or any other AI extra — concrete strategy classes are only
imported when actually instantiated.

GitHub issue: #27
"""

import subprocess
import sys

from types import ModuleType
from unittest.mock import patch

import pytest


def _make_numpy_blocker() -> ModuleType:
    """Return a sys.meta_path finder that blocks numpy imports."""

    class _NumpyBlocker:
        def find_module(self, name: str, path=None):
            if name == "numpy" or name.startswith("numpy."):
                return self
            return None

        def load_module(self, name: str):
            raise ModuleNotFoundError(
                f"No module named '{name}' (blocked for lazy-import testing)"
            )

    return _NumpyBlocker()


class TestLazyImportsNoNumpy:
    """Verify core ai_models imports work without numpy."""

    def test_model_config_imports_without_numpy(self) -> None:
        """ModelConfig can be imported without numpy."""
        blocker = _make_numpy_blocker()
        with patch.object(__import__("sys"), "meta_path", [blocker] + __import__("sys").meta_path):
            from music_cli.sources.ai_models.model_config import ModelConfig, AIModelsConfig

            cfg = ModelConfig(
                id="test",
                hf_model_id="test/model",
                model_type="musicgen",
            )
            assert cfg.id == "test"
            assert AIModelsConfig.from_dict({"default_model": "test", "models": {"test": cfg.to_dict()}})

    def test_model_strategy_imports_without_numpy(self) -> None:
        """ModelStrategy (ABC) can be imported without numpy."""
        blocker = _make_numpy_blocker()
        with patch.object(__import__("sys"), "meta_path", [blocker] + __import__("sys").meta_path):
            from music_cli.sources.ai_models.model_strategy import ModelStrategy

            assert ModelStrategy.__bases__

    def test_strategy_cache_imports_without_numpy(self) -> None:
        """LRUStrategyCache can be imported without numpy."""
        blocker = _make_numpy_blocker()
        with patch.object(__import__("sys"), "meta_path", [blocker] + __import__("sys").meta_path):
            from music_cli.sources.ai_models.strategy_cache import (
                LRUStrategyCache,
                get_strategy_cache,
                clear_global_cache,
            )

            cache = LRUStrategyCache(max_size=2)
            assert cache.size() == 0

    def test_ai_models_init_without_numpy(self) -> None:
        """Importing from ai_models.__init__ works without numpy."""
        blocker = _make_numpy_blocker()
        with patch.object(__import__("sys"), "meta_path", [blocker] + __import__("sys").meta_path):
            from music_cli.sources.ai_models import (
                AIModelsConfig,
                ModelConfig,
                ModelRegistry,
                ModelStrategy,
                LRUStrategyCache,
                clear_global_cache,
                get_strategy_cache,
            )

            assert ModelConfig
            assert AIModelsConfig
            assert ModelRegistry
            assert ModelStrategy
            assert LRUStrategyCache


class TestLazyStrategyRegistration:
    """Verify strategies are registered lazily when needed.

    These tests use subprocess to ensure a clean Python process
    where strategy classes have not been pre-imported.
    """

    def _run_import_test(self, code: str) -> tuple[int, str, str]:
        """Run a Python snippet in a fresh subprocess."""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, result.stdout, result.stderr

    def test_strategies_not_registered_at_module_load(self) -> None:
        """ModelRegistry._strategies is empty immediately after import."""
        code = """
from music_cli.sources.ai_models.model_registry import ModelRegistry

# Access _strategies directly — no method call triggers registration
assert ModelRegistry._strategies == {}, f"Expected empty, got {ModelRegistry._strategies}"
print("OK: strategies not registered at module load")
"""
        rc, stdout, stderr = self._run_import_test(code)
        assert rc == 0, f"Subprocess failed: {stderr}"
        assert "OK: strategies not registered at module load" in stdout

    def test_strategies_registered_on_create_strategy(self) -> None:
        """Calling create_strategy triggers lazy registration."""
        code = """
from music_cli.sources.ai_models.model_config import ModelConfig
from music_cli.sources.ai_models.model_registry import ModelRegistry

# Verify empty before
assert ModelRegistry._strategies == {}, f"Expected empty, got {ModelRegistry._strategies}"

config = ModelConfig(
    id="musicgen-small",
    hf_model_id="facebook/musicgen-small",
    model_type="musicgen",
)
strategy = ModelRegistry.create_strategy(config)
assert strategy is not None
assert "musicgen" in ModelRegistry._strategies
print("OK: strategies registered after create_strategy")
"""
        rc, stdout, stderr = self._run_import_test(code)
        assert rc == 0, f"Subprocess failed: {stderr}"
        assert "OK: strategies registered after create_strategy" in stdout

    def test_strategies_registered_on_get_supported_types(self) -> None:
        """Calling get_supported_types triggers lazy registration."""
        code = """
from music_cli.sources.ai_models.model_registry import ModelRegistry

# Verify empty before
assert ModelRegistry._strategies == {}, f"Expected empty, got {ModelRegistry._strategies}"

types = ModelRegistry.get_supported_types()
assert "musicgen" in types
assert "audioldm" in types
assert "bark" in types
assert "minimax_music3" in types
print("OK: strategies registered after get_supported_types")
"""
        rc, stdout, stderr = self._run_import_test(code)
        assert rc == 0, f"Subprocess failed: {stderr}"
        assert "OK: strategies registered after get_supported_types" in stdout

    def test_strategies_registered_on_is_supported(self) -> None:
        """Calling is_supported triggers lazy registration."""
        code = """
from music_cli.sources.ai_models.model_registry import ModelRegistry

# Verify empty before
assert ModelRegistry._strategies == {}, f"Expected empty, got {ModelRegistry._strategies}"

assert ModelRegistry.is_supported("musicgen") is True
assert ModelRegistry.is_supported("nonexistent") is False
print("OK: strategies registered after is_supported")
"""
        rc, stdout, stderr = self._run_import_test(code)
        assert rc == 0, f"Subprocess failed: {stderr}"
        assert "OK: strategies registered after is_supported" in stdout
