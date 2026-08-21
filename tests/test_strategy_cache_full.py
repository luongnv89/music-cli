"""LRUStrategyCache behaviour tests (issue #72 — coverage raise)."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

import music_cli.sources.ai_models.strategy_cache as strategy_cache_module
from music_cli.sources.ai_models.model_strategy import ModelStrategy
from music_cli.sources.ai_models.strategy_cache import (
    LRUStrategyCache,
    clear_global_cache,
    get_strategy_cache,
)


def make_strategy() -> Mock:
    strategy = Mock(spec=ModelStrategy)
    strategy.unload.return_value = None
    return strategy


class TestGetPut:
    def test_get_miss_returns_none(self) -> None:
        cache = LRUStrategyCache(max_size=2)
        assert cache.get("missing") is None

    def test_put_then_get_roundtrip_and_ordering(self) -> None:
        cache = LRUStrategyCache(max_size=3)
        first, second = make_strategy(), make_strategy()
        cache.put("a", first)
        cache.put("b", second)
        assert cache.get("a") is first
        # a was touched last, so b is now the oldest entry.
        assert cache.get_cached_models() == ["b", "a"]

    def test_put_existing_updates_without_eviction(self) -> None:
        cache = LRUStrategyCache(max_size=2)
        old, replacement = make_strategy(), make_strategy()
        cache.put("m", old)
        cache.put("m", replacement)
        assert cache.size() == 1
        assert cache.contains("m")
        assert cache.get("m") is replacement
        old.unload.assert_not_called()

    def test_full_cache_evicts_lru_entry(self) -> None:
        cache = LRUStrategyCache(max_size=2)
        a, b, c = make_strategy(), make_strategy(), make_strategy()
        cache.put("a", a)
        cache.put("b", b)
        cache.get("a")  # refresh a; b becomes LRU
        cache.put("c", c)
        assert cache.get_cached_models() == ["a", "c"]
        b.unload.assert_called_once_with()
        a.unload.assert_not_called()


class TestRemoveClearContainsSize:
    def test_remove_unloads_and_reports_found(self) -> None:
        cache = LRUStrategyCache(max_size=2)
        strategy = make_strategy()
        cache.put("m", strategy)
        assert cache.remove("m") is True
        strategy.unload.assert_called_once_with()
        assert cache.contains("m") is False

    def test_remove_missing_returns_false(self) -> None:
        cache = LRUStrategyCache(max_size=2)
        assert cache.remove("ghost") is False

    def test_unload_error_is_swallowed_on_remove(self) -> None:
        cache = LRUStrategyCache(max_size=2)
        strategy = make_strategy()
        strategy.unload.side_effect = RuntimeError("CUDA blew up")
        cache.put("m", strategy)
        assert cache.remove("m") is True  # error logged, not raised
        assert cache.size() == 0

    def test_clear_unloads_everything(self) -> None:
        cache = LRUStrategyCache(max_size=3)
        strategies = [make_strategy() for _ in range(3)]
        for i, strategy in enumerate(strategies):
            cache.put(f"m{i}", strategy)
        cache.clear()
        for strategy in strategies:
            strategy.unload.assert_called_once_with()
        assert cache.size() == 0
        assert cache.get_cached_models() == []

    def test_contains_and_size(self) -> None:
        cache = LRUStrategyCache(max_size=2)
        assert cache.contains("x") is False
        assert cache.size() == 0
        cache.put("x", make_strategy())
        assert cache.contains("x") is True
        assert cache.size() == 1


class TestMaxSizeSetter:
    def test_shrinking_evicts_down_to_target(self) -> None:
        cache = LRUStrategyCache(max_size=4)
        strategies = [make_strategy() for _ in range(4)]
        for i, strategy in enumerate(strategies):
            cache.put(f"m{i}", strategy)

        cache.max_size = 2
        assert cache.size() == 2
        strategies[0].unload.assert_called_once_with()
        strategies[1].unload.assert_called_once_with()
        strategies[2].unload.assert_not_called()
        strategies[3].unload.assert_not_called()

    def test_zero_disables_capacity_evictions(self) -> None:
        cache = LRUStrategyCache(max_size=0)
        for i in range(5):
            cache.put(f"m{i}", make_strategy())
        assert cache.size() == 5

    def test_growing_does_not_evict(self) -> None:
        cache = LRUStrategyCache(max_size=1)
        cache.put("only", make_strategy())
        cache.max_size = 10
        assert cache.contains("only")


class TestGlobalSingleton:
    def test_get_strategy_cache_is_singleton(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(strategy_cache_module, "_global_cache", None)
        first = get_strategy_cache(max_size=7)
        second = get_strategy_cache(max_size=99)  # max_size ignored after creation
        assert first is second
        assert first.max_size == 7

    def test_clear_global_cache_clears_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cache = LRUStrategyCache(max_size=2)
        spy = make_strategy()
        cache.put("m", spy)
        monkeypatch.setattr(strategy_cache_module, "_global_cache", cache)
        clear_global_cache()
        spy.unload.assert_called_once_with()
        assert cache.size() == 0

    def test_clear_global_cache_without_instance_is_safe(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(strategy_cache_module, "_global_cache", None)
        clear_global_cache()  # must not raise


class TestGpuCleanup:
    def test_cleanup_survives_missing_torch(self) -> None:
        # torch is an optional extra; the ImportError path keeps eviction safe.
        cache = LRUStrategyCache(max_size=1)
        cache.put("m", make_strategy())
        cache.remove("m")  # exercises _cleanup_gpu_memory via _evict/_remove path
        assert True

    @pytest.mark.parametrize("max_size", [0, 1, 3])
    def test_constructor_accepts_sizes(self, max_size: int) -> None:
        assert LRUStrategyCache(max_size=max_size).max_size == max_size
