"""Complementary LocalSource tests (issue #72 — coverage raise)."""

from __future__ import annotations

from pathlib import Path

import pytest

from music_cli.sources.local import LocalSource


@pytest.fixture()
def music_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "Music"
    directory.mkdir()
    (directory / "song.mp3").write_bytes(b"fake")
    (directory / "album" / "track.flac").parent.mkdir()
    (directory / "album" / "track.flac").write_bytes(b"fake")
    (directory / "notes.txt").write_text("not music")
    return directory


class TestDefaults:
    def test_default_music_dir_is_home_music(self) -> None:
        source = LocalSource()
        assert source.music_dir == Path("~/Music").expanduser()


class TestGetTrack:
    def test_rejects_unsupported_extension(self, tmp_path: Path) -> None:
        notes = tmp_path / "notes.txt"
        notes.write_text("x")
        upper = tmp_path / "notes.UPPER"
        upper.write_text("x")
        source = LocalSource(music_dir=tmp_path)
        assert source.get_track(str(notes)) is None
        # Extension comparison is case-insensitive.
        assert source.get_track(str(upper)) is None


class TestScanDirectory:
    def test_missing_directory_returns_empty(self, tmp_path: Path) -> None:
        source = LocalSource(music_dir=tmp_path)
        assert source.scan_directory(tmp_path / "absent") == []

    def test_scan_finds_supported_files_sorted(self, music_dir: Path) -> None:
        source = LocalSource(music_dir=music_dir)
        found = source.scan_directory()
        assert found == sorted(found)  # deterministic ordering
        names = [f.name for f in found]
        assert "song.mp3" in names
        assert "track.flac" in names
        assert "notes.txt" not in names


class TestRandomAndList:
    def test_random_track_empty_directory(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        source = LocalSource(music_dir=empty)
        assert source.get_random_track() is None

    def test_random_track_picks_supported_file(self, music_dir: Path) -> None:
        source = LocalSource(music_dir=music_dir)
        track = source.get_random_track()
        assert track is not None
        assert track.source_type == "local"
        assert track.title in {"song", "track"}  # either supported file is valid

    def test_list_tracks_respects_limit_and_skips_invalid(self, music_dir: Path) -> None:
        source = LocalSource(music_dir=music_dir)
        tracks = source.list_tracks(limit=1)
        assert len(tracks) == 1

        all_tracks = source.list_tracks(limit=50)
        # Only supported extensions become TrackInfo objects.
        assert {t.title for t in all_tracks} == {"song", "track"}
