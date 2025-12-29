"""Music source modules for music-cli."""

from .local import LocalSource
from .radio import RadioSource

__all__ = ["LocalSource", "RadioSource"]
