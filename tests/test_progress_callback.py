"""Tests for the HuggingFace download progress callback (issue #72 / F-TEST-005).

The module renders model-download progress either as a tqdm bar (interactive
TTY + tqdm installed) or as throttled log lines (headless runs). Both paths are
exercised here without importing the real tqdm: a stub module is injected into
``sys.modules`` so the lazy ``import tqdm`` inside the callback resolves.
"""

from __future__ import annotations

import logging
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest

from music_cli.sources.ai_models.progress_callback import (
    DownloadProgressCallback,
    configure_hf_progress,
    create_hf_progress_callback,
    with_progress,
)


class FakeTqdm:
    """Minimal tqdm stand-in recording construction and updates."""

    instances: list[FakeTqdm] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.n = 0
        self.refreshes = 0
        self.closed = False
        type(self).instances.append(self)

    def refresh(self) -> None:
        self.refreshes += 1

    def close(self) -> None:
        self.closed = True


@pytest.fixture()
def fake_tqdm_module(monkeypatch: pytest.MonkeyPatch) -> type[FakeTqdm]:
    """Inject a stub ``tqdm`` module whose ``tqdm`` symbol is FakeTqdm."""
    FakeTqdm.instances = []
    module = ModuleType("tqdm")
    module.tqdm = FakeTqdm  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tqdm", module)
    return FakeTqdm


class TestCanUseTqdm:
    def test_disabled_flag_short_circuits(self) -> None:
        cb = DownloadProgressCallback("model", disable=True)
        assert cb._use_tqdm is False

    def test_false_without_tqdm_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A None entry in sys.modules makes `import tqdm` raise ImportError.
        monkeypatch.setitem(sys.modules, "tqdm", None)
        cb = DownloadProgressCallback("model")
        assert cb._use_tqdm is False

    def test_false_when_stdout_is_not_a_tty(
        self, fake_tqdm_module: type[FakeTqdm], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "stdout", SimpleNamespace(isatty=lambda: False))
        cb = DownloadProgressCallback("model")
        assert cb._use_tqdm is False

    def test_false_when_stdout_has_no_isatty(
        self, fake_tqdm_module: type[FakeTqdm], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "stdout", SimpleNamespace())
        cb = DownloadProgressCallback("model")
        assert cb._use_tqdm is False

    def test_true_with_tqdm_and_tty(
        self, fake_tqdm_module: type[FakeTqdm], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "stdout", SimpleNamespace(isatty=lambda: True))
        cb = DownloadProgressCallback("model")
        assert cb._use_tqdm is True


class TestCallRouting:
    def test_disabled_call_is_a_no_op(self) -> None:
        cb = DownloadProgressCallback("model", disable=True)
        with (
            patch.object(cb, "_update_tqdm") as upd_tqdm,
            patch.object(cb, "_update_log") as upd_log,
        ):
            cb(100, 200)
        upd_tqdm.assert_not_called()
        upd_log.assert_not_called()

    def test_non_positive_total_is_ignored(self) -> None:
        cb = DownloadProgressCallback("model")
        with (
            patch.object(cb, "_update_tqdm") as upd_tqdm,
            patch.object(cb, "_update_log") as upd_log,
        ):
            cb(100, 0)
            cb(100, -5)
        upd_tqdm.assert_not_called()
        upd_log.assert_not_called()

    def test_routes_to_tqdm_path(self) -> None:
        cb = DownloadProgressCallback("model")
        cb._use_tqdm = True
        with patch.object(cb, "_update_tqdm") as upd_tqdm:
            cb(10, 20, "ignored-positional", extra="ignored-kw")
        upd_tqdm.assert_called_once_with(10, 20)

    def test_routes_to_log_path(self) -> None:
        cb = DownloadProgressCallback("model")
        cb._use_tqdm = False
        with patch.object(cb, "_update_log") as upd_log:
            cb(10, 20)
        upd_log.assert_called_once_with(10, 20)


class TestUpdateTqdm:
    def test_creates_bar_then_updates_it(self, fake_tqdm_module: type[FakeTqdm]) -> None:
        cb = DownloadProgressCallback("my-model")
        cb._use_tqdm = True

        cb._update_tqdm(512, 2048)
        assert len(FakeTqdm.instances) == 1
        bar = FakeTqdm.instances[0]
        assert bar.kwargs["total"] == 2048
        assert bar.kwargs["unit"] == "B"
        assert bar.kwargs["unit_scale"] is True
        assert bar.kwargs["unit_divisor"] == 1024
        assert bar.kwargs["desc"] == "Downloading my-model"
        assert bar.kwargs["leave"] is True
        assert bar.n == 512
        assert bar.refreshes == 1

        cb._update_tqdm(1024, 2048)
        assert len(FakeTqdm.instances) == 1  # reused, not recreated
        assert bar.n == 1024
        assert bar.refreshes == 2


class TestUpdateLog:
    def test_logs_at_ten_percent_intervals(self, caplog: pytest.LogCaptureFixture) -> None:
        cb = DownloadProgressCallback("my-model")
        mb = 1024 * 1024
        with caplog.at_level(logging.INFO, logger="music_cli.sources.ai_models.progress_callback"):
            cb._update_log(0, 10 * mb)  # 0% -> below first interval, silent
            assert not [r for r in caplog.records if "Downloading my-model" in r.message]

            cb._update_log(int(1.5 * mb), 10 * mb)  # 15% -> logs at watermark 10
            cb._update_log(int(1.6 * mb), 10 * mb)  # still < watermark+10, silent
            cb._update_log(int(2.5 * mb), 10 * mb)  # 25% -> logs at watermark 20
            records = [r for r in caplog.records if "Downloading my-model" in r.message]
        assert len(records) == 2
        assert "15%" in records[0].message
        assert "25%" in records[1].message
        assert "(1.5/10.0 MB)" in records[0].message

    def test_non_positive_total_returns_early(self) -> None:
        cb = DownloadProgressCallback("model")
        cb._last_logged_percent = 100
        cb._update_log(10, 0)
        assert cb._last_logged_percent == 100  # untouched


class TestCloseAndFactories:
    def test_close_closes_and_clears_bar(self, fake_tqdm_module: type[FakeTqdm]) -> None:
        cb = DownloadProgressCallback("model")
        cb._use_tqdm = True
        cb._update_tqdm(1, 10)
        bar = cb._pbar
        cb.close()
        assert bar is not None and bar.closed is True
        assert cb._pbar is None

    def test_close_without_bar_is_safe(self) -> None:
        DownloadProgressCallback("model").close()

    def test_create_hf_progress_callback(self) -> None:
        cb = create_hf_progress_callback("acme/model")
        assert isinstance(cb, DownloadProgressCallback)
        assert cb.model_name == "acme/model"


class TestConfigureHfProgress:
    def test_enable_removes_env_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        configure_hf_progress(enabled=True)
        import os

        assert "HF_HUB_DISABLE_PROGRESS_BARS" not in os.environ

    def test_disable_sets_env_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HF_HUB_DISABLE_PROGRESS_BARS", raising=False)
        configure_hf_progress(enabled=False)
        import os

        assert os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] == "1"


class TestWithProgress:
    def test_success_returns_result_and_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        sentinel = object()
        with caplog.at_level(logging.INFO, logger="music_cli.sources.ai_models.progress_callback"):
            result = with_progress("my-model", lambda: sentinel)
        assert result is sentinel
        messages = [r.message for r in caplog.records]
        assert any("Loading my-model..." in m for m in messages)
        assert any("loaded successfully" in m for m in messages)

    def test_failure_logs_error_and_reraises(self, caplog: pytest.LogCaptureFixture) -> None:
        def boom() -> None:
            raise RuntimeError("disk exploded")

        with (
            caplog.at_level(logging.ERROR, logger="music_cli.sources.ai_models.progress_callback"),
            pytest.raises(RuntimeError, match="disk exploded"),
        ):
            with_progress("my-model", boom)
        assert any("Failed to load my-model" in r.message for r in caplog.records)
