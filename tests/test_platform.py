"""Regression tests for the music_cli.platform public surface."""

import importlib

import music_cli.platform as platform_module


def test_all_exports_resolve() -> None:
    """Every name in __all__ must exist on the module (F-BUG-002)."""
    mod = importlib.import_module("music_cli.platform")
    for name in mod.__all__:
        assert hasattr(mod, name), f"__all__ entry {name!r} missing from module"


def test_media_controller_surface_removed() -> None:
    """The dead media-controller surface must not be exported or present."""
    assert "get_media_controller" not in platform_module.__all__
    assert not hasattr(platform_module, "get_media_controller")


def test_import_succeeds() -> None:
    """Importing the package must not raise (broken lazy imports)."""
    importlib.import_module("music_cli.platform")
