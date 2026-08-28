"""Tests for music_cli.studio.taste — abstract playlist analysis (issue #144, P6.1).

Verifies that ``from_playlist`` returns a :class:`TasteProfile` containing
*only* abstract numeric attributes — no artist or track names leak into the
output.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from music_cli.studio.taste import (
    TasteProfile,
    _extract_dynamic_range,
    _extract_key,
    _extract_loudness,
    _extract_tempo,
    _guess_format,
    _parse_m3u,
    _parse_pls,
    from_playlist,
)

# ---------------------------------------------------------------------------
# helpers — sample ffprobe output
# ---------------------------------------------------------------------------


def _make_probe(
    tempo: float | None = None,
    key: str | None = None,
    r128_range: float | None = None,
    r128_loudness: float | None = None,
) -> dict:
    """Build a minimal ffprobe JSON dict with the given metadata."""
    tags: dict = {}
    if tempo is not None:
        tags["tempo"] = str(tempo)
    if key is not None:
        tags["key"] = key
    if r128_range is not None:
        tags["r128_range"] = str(r128_range)
    if r128_loudness is not None:
        tags["r128_loudness"] = str(r128_loudness)
    return {
        "format": {
            "tags": tags,
        },
        "streams": [
            {
                "codec_type": "audio",
                "tags": dict(tags),
            }
        ],
    }


# ---------------------------------------------------------------------------
# TasteProfile round-trip
# ---------------------------------------------------------------------------


class TestTasteProfileRoundTrip:
    def test_to_dict_and_back(self):
        profile = TasteProfile(
            tempo_histogram=[1, 2, 3],
            key_distribution={"C": 0.5, "Am": 0.5},
            mean_dynamic_range_db=12.5,
            mean_loudness_db=-14.0,
            track_count=2,
        )
        data = profile.to_dict()
        restored = TasteProfile.from_dict(data)
        assert restored.tempo_histogram == [1, 2, 3]
        assert restored.key_distribution == {"C": 0.5, "Am": 0.5}
        assert restored.mean_dynamic_range_db == 12.5
        assert restored.mean_loudness_db == -14.0
        assert restored.track_count == 2

    def test_empty_profile(self):
        profile = TasteProfile()
        data = profile.to_dict()
        assert data["tempo_histogram"] == []
        assert data["key_distribution"] == {}
        assert data["mean_dynamic_range_db"] == 0.0
        assert data["mean_loudness_db"] == 0.0
        assert data["track_count"] == 0

    def test_no_string_fields(self):
        """A TasteProfile must never contain string fields naming tracks/artists."""
        profile = TasteProfile()
        data = profile.to_dict()
        for key, value in data.items():
            assert not isinstance(value, str), f"field {key} is a string"


# ---------------------------------------------------------------------------
# Playlist parsing
# ---------------------------------------------------------------------------


class TestParseM3U:
    def test_simple(self):
        text = "#EXTM3U\n#EXTINF:180,Artist - Track\n/absolute/path.mp3\nrelative/path.wav\n"
        paths = _parse_m3u(text)
        assert paths == ["/absolute/path.mp3", "relative/path.wav"]

    def test_empty(self):
        assert _parse_m3u("") == []

    def test_metadata_only(self):
        text = "#EXTM3U\n#EXTINF:120,Some Artist\n"
        assert _parse_m3u(text) == []


class TestParsePLS:
    def test_simple(self):
        text = "[playlist]\nFile1=http://example.com/a.mp3\nFile2=http://example.com/b.mp3\n"
        paths = _parse_pls(text)
        assert paths == ["http://example.com/a.mp3", "http://example.com/b.mp3"]

    def test_no_files(self):
        assert _parse_pls("[playlist]\nVersion=2\n") == []


class TestGuessFormat:
    def test_m3u(self):
        assert _guess_format(Path("x.m3u")) == "m3u"

    def test_m3u8(self):
        assert _guess_format(Path("x.m3u8")) == "m3u"

    def test_pls(self):
        assert _guess_format(Path("x.pls")) == "pls"

    def test_unknown(self):
        assert _guess_format(Path("x.txt")) == "m3u"


# ---------------------------------------------------------------------------
# Attribute extraction from ffprobe output
# ---------------------------------------------------------------------------


class TestExtractTempo:
    def test_found(self):
        probe = _make_probe(tempo=120.0)
        assert _extract_tempo(probe) == 120.0

    def test_not_found(self):
        assert _extract_tempo({}) is None


class TestExtractKey:
    def test_major(self):
        probe = _make_probe(key="C")
        assert _extract_key(probe) == "C"

    def test_minor(self):
        probe = _make_probe(key="Am")
        assert _extract_key(probe) == "Am"

    def test_invalid_key(self):
        probe = _make_probe(key="Xy")
        assert _extract_key(probe) is None


class TestExtractDynamicRange:
    def test_found(self):
        probe = _make_probe(r128_range=10.5)
        assert _extract_dynamic_range(probe) == 10.5

    def test_not_found(self):
        assert _extract_dynamic_range({}) is None


class TestExtractLoudness:
    def test_found(self):
        probe = _make_probe(r128_loudness=-14.0)
        assert _extract_loudness(probe) == -14.0

    def test_not_found(self):
        assert _extract_loudness({}) is None


# ---------------------------------------------------------------------------
# Integration: from_playlist with mocked ffprobe
# ---------------------------------------------------------------------------


class TestFromPlaylist:
    """End-to-end tests with a mocked ffprobe subprocess."""

    @pytest.fixture
    def sample_m3u(self, tmp_path: Path) -> Path:
        """Create a minimal M3U playlist referencing non-existent files."""
        p = tmp_path / "playlist.m3u"
        p.write_text("#EXTM3U\ntrack1.mp3\ntrack2.mp3\n", encoding="utf-8")
        return p

    def test_no_files_probed(self, sample_m3u: Path):
        """When no audio files exist, the profile has zero tracks."""
        profile = from_playlist(sample_m3u)
        assert profile.track_count == 0
        assert profile.tempo_histogram == [0] * 10
        assert profile.key_distribution == {}
        assert profile.mean_dynamic_range_db == 0.0
        assert profile.mean_loudness_db == 0.0

    def test_profile_has_no_track_names(self, sample_m3u: Path):
        """The profile must not contain any string fields."""
        profile = from_playlist(sample_m3u)
        data = profile.to_dict()
        for value in data.values():
            assert not isinstance(value, str), f"found string field: {value}"

    def test_with_mocked_ffprobe(self, tmp_path: Path) -> None:
        """Simulate two probed files and verify aggregation."""
        # Create the playlist and actual files so existence checks pass
        playlist = tmp_path / "test.m3u"
        playlist.write_text("#EXTM3U\ntest.mp3\ntest2.mp3\n", encoding="utf-8")
        (tmp_path / "test.mp3").touch()
        (tmp_path / "test2.mp3").touch()

        # Mock ffprobe to return valid metadata
        probe1 = _make_probe(tempo=120.0, key="C", r128_range=12.0, r128_loudness=-14.0)
        probe2 = _make_probe(tempo=120.0, key="C", r128_range=10.0, r128_loudness=-16.0)

        call_count = 0

        def _mock_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                result = mock.Mock(returncode=0, stdout=json.dumps(probe1), stderr="")
            else:
                result = mock.Mock(returncode=0, stdout=json.dumps(probe2), stderr="")
            return result

        with mock.patch("subprocess.run", side_effect=_mock_run):
            profile = from_playlist(playlist)

        assert profile.track_count == 2
        # Both tracks at 120 BPM → bin 6 (120-130)
        assert profile.tempo_histogram[6] == 2
        assert profile.key_distribution == {"C": 1.0}
        assert profile.mean_dynamic_range_db == 11.0
        assert profile.mean_loudness_db == -15.0

    def test_nonexistent_playlist(self, tmp_path: Path):
        bad = tmp_path / "missing.m3u"
        with pytest.raises(OSError, match="not found"):
            from_playlist(bad)

    def test_pls_format(self, tmp_path: Path) -> None:
        playlist = tmp_path / "test.pls"
        playlist.write_text(
            "[playlist]\nFile1=http://example.com/a.mp3\nFile2=http://example.com/b.mp3\n",
            encoding="utf-8",
        )
        profile = from_playlist(playlist)
        assert profile.track_count == 0  # files don't exist on disk

    def test_tempo_histogram_bins(self, tmp_path: Path) -> None:
        """Verify tempo histogram bins span 60-160 BPM in 10-BPM steps."""
        playlist = tmp_path / "bins.m3u"
        playlist.write_text("#EXTM3U\nb.mp3\n", encoding="utf-8")
        (tmp_path / "b.mp3").touch()

        def _mock_run(cmd, **kwargs):
            probe = _make_probe(tempo=155.0, key="Am")
            return mock.Mock(returncode=0, stdout=json.dumps(probe), stderr="")

        with mock.patch("subprocess.run", side_effect=_mock_run):
            profile = from_playlist(playlist)

        # 155 BPM → bin 9 (150-160)
        assert profile.tempo_histogram[9] == 1
        assert profile.tempo_histogram[8] == 0  # 140-150 is empty
