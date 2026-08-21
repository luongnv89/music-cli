"""YouTubeSource tests (issue #72 — coverage raise).

yt-dlp is an optional extra; a stub module is injected into ``sys.modules`` so
extraction is exercised without network access.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from music_cli.sources.youtube import (
    YouTubeSource,
    _clean_url,
    is_youtube_available,
    is_youtube_url,
)


class TestAvailability:
    def test_unavailable_without_extra(self) -> None:
        assert is_youtube_available() is False


class TestUrlCleaning:
    def test_backslashes_removed(self) -> None:
        assert _clean_url("https://youtu\\.be/abc") == "https://youtu.be/abc"

    def test_clean_url_is_applied_before_matching(self) -> None:
        assert is_youtube_url("https://www.youtube.com/watch\\?v=abc") is True


class TestIsYoutubeUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "youtube.com/watch?v=abc&t=30",
            "https://youtu.be/xyz",
            "https://youtube.com/shorts/shortid",
            "https://music.youtube.com/watch?v=music",
        ],
    )
    def test_matches(self, url: str) -> None:
        assert is_youtube_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://vimeo.com/12345",
            "https://example.com/watch?v=1",
            "not a url",
        ],
    )
    def test_rejects_non_youtube(self, url: str) -> None:
        assert is_youtube_url(url) is False


def install_fake_yt_dlp(monkeypatch: pytest.MonkeyPatch, extract_result):
    """Inject a stub yt_dlp whose YoutubeDL context yields ``extract_result``."""
    ydl = MagicMock()
    ydl.extract_info.return_value = extract_result

    class FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return ydl

        def __exit__(self, *exc):
            return False

    module = ModuleType("yt_dlp")
    module.YoutubeDL = FakeYoutubeDL  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yt_dlp", module)
    return ydl


class TestGetTrack:
    def test_invalid_url_returns_none(self) -> None:
        assert YouTubeSource().get_track("https://vimeo.com/1") is None

    def test_direct_stream_url_used(self, monkeypatch) -> None:
        info = {
            "url": "https://stream.example/audio",
            "title": "Song",
            "uploader": "Artist",
            "duration": 123,
            "id": "vid1",
        }
        install_fake_yt_dlp(monkeypatch, info)

        track = YouTubeSource().get_track("https://youtu.be/vid1")
        assert track is not None
        assert track.source == "https://stream.example/audio"
        assert track.source_type == "youtube"
        assert track.title == "Song"
        assert track.artist == "Artist"
        assert track.duration == 123.0
        assert track.metadata["video_id"] == "vid1"

    def test_falls_back_to_best_audio_format(self, monkeypatch) -> None:
        info = {
            "title": "No direct URL",
            "formats": [
                {"vcodec": "h264", "acodec": "aac", "abr": 128, "url": "video-only"},
                {"vcodec": "none", "acodec": None, "abr": 96, "url": "no-codec"},
                {"vcodec": "none", "acodec": "mp3", "abr": 64, "url": "low"},
                {"vcodec": "none", "acodec": "opus", "abr": 160, "url": "high"},
                {"vcodec": "none", "acodec": "aac", "url": "unknown-abr"},
            ],
        }
        install_fake_yt_dlp(monkeypatch, info)

        track = YouTubeSource().get_track("https://youtu.be/vid2")
        assert track is not None
        # Highest known audio bitrate wins; entries without abr sort last.
        assert track.source == "high"

    def test_no_extractable_stream_returns_none(self, monkeypatch) -> None:
        info = {"title": "Empty", "formats": [{"vcodec": "h264", "acodec": "aac"}]}
        install_fake_yt_dlp(monkeypatch, info)
        assert YouTubeSource().get_track("https://youtu.be/vid3") is None

    def test_failed_extraction_returns_none(self, monkeypatch) -> None:
        install_fake_yt_dlp(monkeypatch, None)
        assert YouTubeSource().get_track("https://youtu.be/vid4") is None

    def test_extraction_error_returns_none(self, monkeypatch) -> None:
        ydl = MagicMock()
        ydl.extract_info.side_effect = OSError("network gone")

        class FakeYoutubeDL:
            def __init__(self, opts):
                pass

            def __enter__(self):
                return ydl

            def __exit__(self, *exc):
                return False

        module = ModuleType("yt_dlp")
        module.YoutubeDL = FakeYoutubeDL  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "yt_dlp", module)

        assert YouTubeSource().get_track("https://youtu.be/vid5") is None

    def test_missing_dependency_reraises_import_error(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "yt_dlp", None)
        with pytest.raises(ImportError, match="yt-dlp"):
            YouTubeSource().get_track("https://youtu.be/vid6")


class TestChannelFallback:
    def test_artist_falls_back_to_channel(self, monkeypatch) -> None:
        info = {
            "url": "https://stream.example/x",
            "title": "T",
            "channel": "Some Channel",
        }
        install_fake_yt_dlp(monkeypatch, info)
        track = YouTubeSource().get_track("https://youtu.be/vid7")
        assert track is not None
        assert track.artist == "Some Channel"


def test_lazy_module_is_cached_on_instance(monkeypatch) -> None:
    install_fake_yt_dlp(monkeypatch, None)
    source = YouTubeSource()
    handle = source._ensure_yt_dlp()
    assert source._yt_dlp is sys.modules["yt_dlp"]
    # Second call reuses the cached module handle.
    assert source._ensure_yt_dlp() is handle
