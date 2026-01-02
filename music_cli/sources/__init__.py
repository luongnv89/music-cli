"""Music source modules for music-cli."""

from .local import LocalSource
from .radio import RadioSource
from .youtube import YouTubeSource, is_youtube_available, is_youtube_url

__all__ = ["LocalSource", "RadioSource", "YouTubeSource", "is_youtube_available", "is_youtube_url"]
