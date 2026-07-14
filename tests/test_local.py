"""Tests for music_cli.sources.local."""

from music_cli.sources.local import LocalSource


class TestGetTrackCwdFirst:
    """get_track should check CWD before falling back to music_dir."""

    def test_relative_path_found_in_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        song = tmp_path / "song.mp3"
        song.touch()
        source = LocalSource(music_dir=tmp_path / "nonexistent")
        track = source.get_track("song.mp3")
        assert track is not None
        assert track.source == str(song.resolve())

    def test_relative_path_not_in_cwd_falls_back_to_music_dir(self, tmp_path):
        music_dir = tmp_path / "music"
        music_dir.mkdir()
        song = music_dir / "song.mp3"
        song.touch()
        source = LocalSource(music_dir=music_dir)
        track = source.get_track("song.mp3")
        assert track is not None
        assert track.source == str(song)

    def test_absolute_path_still_works(self, tmp_path):
        song = tmp_path / "song.mp3"
        song.touch()
        source = LocalSource(music_dir=tmp_path / "music")
        track = source.get_track(str(song))
        assert track is not None
        assert track.source == str(song)

    def test_cwd_takes_priority_over_music_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cwd_song = tmp_path / "song.mp3"
        cwd_song.touch()
        music_dir = tmp_path / "music"
        music_dir.mkdir()
        music_song = music_dir / "song.mp3"
        music_song.touch()
        source = LocalSource(music_dir=music_dir)
        track = source.get_track("song.mp3")
        assert track is not None
        assert track.source == str(cwd_song.resolve())

    def test_invalid_path_returns_none(self, tmp_path):
        source = LocalSource(music_dir=tmp_path)
        track = source.get_track("nonexistent.mp3")
        assert track is None

    def test_unsupported_extension_returns_none(self, tmp_path):
        f = tmp_path / "file.txt"
        f.touch()
        source = LocalSource(music_dir=tmp_path)
        track = source.get_track(str(f))
        assert track is None
