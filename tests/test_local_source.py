"""Tests for LocalSource relative-path resolution (issue #18)."""

from music_cli.sources.local import LocalSource


class TestGetTrackRelativePaths:
    """get_track() should check the current working directory before
    falling back to the configured music directory."""

    def test_relative_path_found_in_cwd(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        music_dir = tmp_path / "music"
        cwd.mkdir()
        music_dir.mkdir()
        (cwd / "song.mp3").touch()
        monkeypatch.chdir(cwd)

        source = LocalSource(music_dir=music_dir)
        track = source.get_track("song.mp3")

        assert track is not None
        assert track.title == "song"
        assert track.source == str((cwd / "song.mp3").resolve())

    def test_relative_path_falls_back_to_music_dir(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        music_dir = tmp_path / "music"
        cwd.mkdir()
        music_dir.mkdir()
        (music_dir / "song.mp3").touch()
        monkeypatch.chdir(cwd)

        source = LocalSource(music_dir=music_dir)
        track = source.get_track("song.mp3")

        assert track is not None
        assert track.source == str(music_dir / "song.mp3")

    def test_relative_path_not_found_anywhere_returns_none(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        music_dir = tmp_path / "music"
        cwd.mkdir()
        music_dir.mkdir()
        monkeypatch.chdir(cwd)

        source = LocalSource(music_dir=music_dir)
        track = source.get_track("missing.mp3")

        assert track is None

    def test_cwd_match_takes_priority_over_music_dir(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        music_dir = tmp_path / "music"
        cwd.mkdir()
        music_dir.mkdir()
        (cwd / "song.mp3").touch()
        (music_dir / "song.mp3").touch()
        monkeypatch.chdir(cwd)

        source = LocalSource(music_dir=music_dir)
        track = source.get_track("song.mp3")

        assert track.source == str((cwd / "song.mp3").resolve())

    def test_absolute_path_unaffected(self, tmp_path):
        music_dir = tmp_path / "music"
        music_dir.mkdir()
        f = music_dir / "song.mp3"
        f.touch()

        source = LocalSource(music_dir=tmp_path / "other")
        track = source.get_track(str(f))

        assert track is not None
        assert track.source == str(f)

    def test_unsupported_extension_in_cwd_returns_none(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        music_dir = tmp_path / "music"
        cwd.mkdir()
        music_dir.mkdir()
        (cwd / "notes.txt").touch()
        monkeypatch.chdir(cwd)

        source = LocalSource(music_dir=music_dir)
        track = source.get_track("notes.txt")

        assert track is None
