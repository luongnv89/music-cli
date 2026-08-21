"""RadioSource tests (issue #72 — coverage raise).

The config dependency is replaced with a stub so station lists are fully
controlled; YouTube availability is patched at the module boundary.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

import music_cli.sources.radio as radio_module
from music_cli.sources.radio import RadioSource, _is_youtube_url


@pytest.fixture()
def source() -> RadioSource:
    radio = RadioSource.__new__(RadioSource)  # skip __init__'s get_config()
    radio.config = Mock()
    radio.config.get_radios.return_value = [
        ("Jazz Groove", "https://stream.example/jazz"),
        ("YT Music", "https://youtube.com/watch?v=x"),
    ]
    radio.config.get_mood_radio.return_value = None
    radio.config.get_time_radio.return_value = None
    radio._youtube_available = None
    return radio


class TestIsYoutubeUrl:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://www.youtube.com/watch?v=abc", True),
            ("https://youtu.be/abc", True),
            ("https://stream.example/jazz", False),
        ],
    )
    def test_detection(self, url: str, expected: bool) -> None:
        assert _is_youtube_url(url) is expected


class TestGetStations:
    def test_youtube_stations_kept_when_available(self, source: RadioSource) -> None:
        with patch.object(radio_module, "is_youtube_available", return_value=True):
            assert len(source.get_stations()) == 2

    def test_youtube_stations_filtered_when_unavailable(self, source: RadioSource) -> None:
        with patch.object(radio_module, "is_youtube_available", return_value=False):
            stations = source.get_stations()
        assert [name for name, _ in stations] == ["Jazz Groove"]

    def test_availability_checked_only_once(self, source: RadioSource) -> None:
        with patch.object(radio_module, "is_youtube_available", return_value=True) as check:
            source.get_stations()
            source.get_stations()
        assert check.call_count == 1


class TestTrackResolution:
    def test_get_track_with_explicit_name(self, source: RadioSource) -> None:
        track = source.get_track("https://stream.example/jazz", "Jazz Groove")
        assert track.source_type == "radio"
        assert track.title == "Jazz Groove"
        assert track.metadata == {"stream_url": "https://stream.example/jazz"}

    def test_get_track_resolves_name_from_config(self, source: RadioSource) -> None:
        track = source.get_track("https://stream.example/jazz")
        assert track.title == "Jazz Groove"

    def test_get_track_unknown_url_falls_back_to_url(self, source: RadioSource) -> None:
        track = source.get_track("https://unknown.example/stream")
        assert track.title == "https://unknown.example/stream"

    def test_station_by_name_case_insensitive_partial(self, source: RadioSource) -> None:
        track = source.get_station_by_name("jazz")
        assert track is not None
        assert track.title == "Jazz Groove"

    def test_station_by_name_miss_returns_none(self, source: RadioSource) -> None:
        assert source.get_station_by_name("classical") is None

    def test_station_by_index_bounds(self, source: RadioSource) -> None:
        with patch.object(radio_module, "is_youtube_available", return_value=False):
            first = source.get_station_by_index(1)
            assert first is not None and first.title == "Jazz Groove"
            assert source.get_station_by_index(0) is None
            assert source.get_station_by_index(5) is None

    def test_random_station_from_non_empty_list(self, source: RadioSource) -> None:
        with patch.object(radio_module, "is_youtube_available", return_value=False):
            track = source.get_random_station()
        assert track is not None
        assert track.title == "Jazz Groove"  # only non-YouTube station

    def test_mood_station_found_and_missing(self, source: RadioSource) -> None:
        source.config.get_mood_radio.return_value = "https://mood.example/focus"
        track = source.get_mood_station("focus")
        assert track is not None
        assert track.title == "Focus Radio"

        source.config.get_mood_radio.return_value = None
        assert source.get_mood_station("sad") is None

    def test_time_station_found_and_missing(self, source: RadioSource) -> None:
        source.config.get_time_radio.return_value = "https://time.example/morning"
        track = source.get_time_station("morning")
        assert track is not None
        assert track.title == "Morning Radio"

        source.config.get_time_radio.return_value = None
        assert source.get_time_station("night") is None


class TestListStations:
    def test_indices_are_one_based(self, source: RadioSource) -> None:
        with patch.object(radio_module, "is_youtube_available", return_value=True):
            listing = source.list_stations()
        assert listing[0] == {
            "index": 1,
            "name": "Jazz Groove",
            "url": "https://stream.example/jazz",
        }
        assert listing[1]["index"] == 2
