"""YouTube audio streaming source.

This module provides YouTube audio extraction and streaming capabilities.
Requires yt-dlp to be installed (optional dependency).
"""

import logging
import re
from urllib.parse import urlparse

from ..player.base import TrackInfo

logger = logging.getLogger(__name__)

# YouTube hosts compared against the parsed URL hostname (#84, F-BUG-016).
# A leading "www." is stripped before comparison, so it is not listed here.
YOUTUBE_HOSTS = frozenset({"youtube.com", "youtu.be", "music.youtube.com", "m.youtube.com"})

# Copy/paste corruption escapes punctuation with backslashes ("youtu\.be",
# "watch\?v="). Strip only those; backslashes elsewhere belong to the URL.
_PASTE_ESCAPE_RE = re.compile(r"\\(?=[.?&=%-])")


def is_youtube_available() -> bool:
    """Check if yt-dlp is installed and available."""
    try:
        import yt_dlp  # noqa: F401

        return True
    except ImportError:
        return False


def _clean_url(url: str) -> str:
    """Undo copy/paste corruption without altering legitimate URLs.

    Only backslashes that precede characters commonly mangled by escaping
    (``. ? & = % -``) are removed (#84, F-BUG-021). A backslash anywhere else
    is part of the URL and is left untouched.

    Args:
        url: The potentially corrupted URL string

    Returns:
        URL with paste-corruption backslashes removed
    """
    return _PASTE_ESCAPE_RE.sub("", url)


def is_youtube_url(url: str) -> bool:
    """Check if the given string is a valid YouTube URL."""
    # Clean the URL first to repair any copy/paste corruption
    candidate = _clean_url(url).strip()
    if not candidate:
        return False
    parsed = urlparse(candidate)
    if not parsed.scheme:
        parsed = urlparse(f"https://{candidate}")
    host = parsed.hostname
    if not host:
        return False
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host in YOUTUBE_HOSTS


class YouTubeSource:
    """Handles YouTube audio streaming.

    Uses yt-dlp to extract audio stream URLs from YouTube videos,
    which can then be played directly by ffplay.
    """

    def __init__(self):
        """Initialize YouTube source."""
        self._yt_dlp = None

    def _ensure_yt_dlp(self):
        """Lazy load yt-dlp module."""
        if self._yt_dlp is None:
            try:
                import yt_dlp

                self._yt_dlp = yt_dlp
            except ImportError as e:
                raise ImportError(
                    "yt-dlp is required for YouTube playback. "
                    "Install with: pip install 'coder-music-cli[youtube]'"
                ) from e
        return self._yt_dlp

    def get_track(self, url: str) -> TrackInfo | None:
        """Extract audio stream from a YouTube URL.

        Args:
            url: YouTube video URL

        Returns:
            TrackInfo with direct audio stream URL, or None if extraction fails
        """
        # Clean the URL first to remove any backslashes that may be introduced during copy/paste
        url = _clean_url(url)

        if not is_youtube_url(url):
            logger.warning(f"Invalid YouTube URL: {url}")
            return None

        try:
            yt_dlp = self._ensure_yt_dlp()

            ydl_opts = {
                "format": "bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "extract_flat": False,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                if not info:
                    logger.error(f"Failed to extract info from: {url}")
                    return None

                # Get the direct stream URL
                stream_url = info.get("url")

                # If no direct URL, try to find best audio format
                if not stream_url and "formats" in info:
                    audio_formats = [
                        f
                        for f in info["formats"]
                        if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")
                    ]
                    if audio_formats:
                        # Sort by audio bitrate and get the best
                        audio_formats.sort(key=lambda x: x.get("abr", 0) or 0, reverse=True)
                        stream_url = audio_formats[0].get("url")

                if not stream_url:
                    logger.error(f"Could not extract stream URL from: {url}")
                    return None

                # Extract metadata
                title = info.get("title", "Unknown")
                artist = info.get("uploader") or info.get("channel")
                duration = info.get("duration")

                return TrackInfo(
                    source=stream_url,
                    source_type="youtube",
                    title=title,
                    artist=artist,
                    duration=float(duration) if duration else None,
                    metadata={
                        "youtube_url": url,
                        "video_id": info.get("id"),
                        "thumbnail": info.get("thumbnail"),
                        "channel": info.get("channel"),
                        "channel_id": info.get("channel_id"),
                        "view_count": info.get("view_count"),
                        "upload_date": info.get("upload_date"),
                    },
                )

        except ImportError:
            raise
        except Exception as e:
            logger.error(f"Error extracting YouTube audio: {e}")
            return None
