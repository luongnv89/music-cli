"""Radio streaming source."""

import random

from ..config import get_config
from ..player.base import TrackInfo
from .youtube import is_youtube_available


def _is_youtube_url(url: str) -> bool:
    """Check if URL is a YouTube URL."""
    return "youtube.com" in url or "youtu.be" in url


class RadioSource:
    """Handles radio stream playback."""

    def __init__(self):
        """Initialize radio source."""
        self.config = get_config()
        self._youtube_available: bool | None = None

    def _check_youtube(self) -> bool:
        """Lazy check for YouTube availability."""
        if self._youtube_available is None:
            self._youtube_available = is_youtube_available()
        return self._youtube_available

    def get_stations(self) -> list[tuple[str, str]]:
        """Get list of (name, url) tuples for all configured stations.

        YouTube stations are filtered out if yt-dlp is not installed.
        """
        stations = self.config.get_radios()
        if not self._check_youtube():
            stations = [(name, url) for name, url in stations if not _is_youtube_url(url)]
        return stations

    def get_track(self, url: str, name: str | None = None) -> TrackInfo:
        """Create a track info for a radio stream."""
        if name is None:
            # Try to find name in config
            for station_name, station_url in self.get_stations():
                if station_url == url:
                    name = station_name
                    break
            if name is None:
                name = url

        return TrackInfo(
            source=url,
            source_type="radio",
            title=name,
            metadata={"stream_url": url},
        )

    def get_station_by_name(self, name: str) -> TrackInfo | None:
        """Get a station by its name (case-insensitive partial match)."""
        name_lower = name.lower()

        for station_name, url in self.get_stations():
            if name_lower in station_name.lower():
                return self.get_track(url, station_name)

        return None

    def get_station_by_index(self, index: int) -> TrackInfo | None:
        """Get a station by its index (1-based)."""
        stations = self.get_stations()
        if 1 <= index <= len(stations):
            name, url = stations[index - 1]
            return self.get_track(url, name)
        return None

    def get_random_station(self) -> TrackInfo | None:
        """Get a random station."""
        stations = self.get_stations()
        if not stations:
            return None

        name, url = random.choice(stations)
        return self.get_track(url, name)

    def get_mood_station(self, mood: str) -> TrackInfo | None:
        """Get a station for a specific mood."""
        url = self.config.get_mood_radio(mood)
        if url:
            return self.get_track(url, f"{mood.capitalize()} Radio")
        return None

    def get_time_station(self, time_period: str) -> TrackInfo | None:
        """Get a station for a time period (morning/afternoon/evening/night)."""
        url = self.config.get_time_radio(time_period)
        if url:
            return self.get_track(url, f"{time_period.capitalize()} Radio")
        return None

    def list_stations(self) -> list[dict]:
        """List all stations with their indices."""
        stations = []
        for i, (name, url) in enumerate(self.get_stations(), 1):
            stations.append(
                {
                    "index": i,
                    "name": name,
                    "url": url,
                }
            )
        return stations
