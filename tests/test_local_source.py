"""Tests for LocalSource relative-path resolution (issue #18)."""

from music_cli.sources.local import LocalSource


class TestGetTrackRelativePaths:
    """get_track() should check the current working directory before
    falling back to the configured music directory."""

    def test_relative_path_in_cwd_outside_music_dir_rejected(self, tmp_path, monkeypatch):
        """Issue #46: playback is confined to music_dir, so a cwd match
        outside the boundary is rejected even though the file exists."""
        cwd = tmp_path / "cwd"
        music_dir = tmp_path / "music"
        cwd.mkdir()
        music_dir.mkdir()
        (cwd / "song.mp3").touch()
        monkeypatch.chdir(cwd)

        source = LocalSource(music_dir=music_dir)
        track = source.get_track("song.mp3")

        assert track is None

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
        assert track.source == str((music_dir / "song.mp3").resolve())

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
        music_dir = cwd
        cwd.mkdir()
        (cwd / "song.mp3").touch()
        monkeypatch.chdir(cwd)

        source = LocalSource(music_dir=music_dir)
        track = source.get_track("song.mp3")

        assert track.source == str((cwd / "song.mp3").resolve())

    def test_absolute_path_inside_music_dir_unaffected(self, tmp_path):
        music_dir = tmp_path / "music"
        music_dir.mkdir()
        f = music_dir / "song.mp3"
        f.touch()

        source = LocalSource(music_dir=music_dir)
        track = source.get_track(str(f))

        assert track is not None
        assert track.source == str(f.resolve())

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


class TestGetTrackBoundaryConfined:
    """get_track() must confine playback to the music directory (issue #46)."""

    def test_absolute_path_outside_music_dir_returns_none(self, tmp_path):
        music_dir = tmp_path / "music"
        outside = tmp_path / "outside"
        music_dir.mkdir()
        outside.mkdir()
        f = outside / "secret.mp3"
        f.touch()

        source = LocalSource(music_dir=music_dir)

        assert source.get_track(str(f)) is None

    def test_symlink_inside_music_dir_pointing_outside_rejected(self, tmp_path):
        music_dir = tmp_path / "music"
        outside = tmp_path / "outside"
        music_dir.mkdir()
        outside.mkdir()
        target = outside / "secret.mp3"
        target.touch()
        link = music_dir / "escape.mp3"
        link.symlink_to(target)

        source = LocalSource(music_dir=music_dir)

        assert source.get_track(str(link)) is None

    def test_relative_escape_via_parent_traversal_rejected(self, tmp_path, monkeypatch):
        music_dir = tmp_path / "music"
        outside = tmp_path / "outside"
        music_dir.mkdir()
        outside.mkdir()
        (outside / "secret.mp3").touch()
        monkeypatch.chdir(music_dir)

        source = LocalSource(music_dir=music_dir)

        assert source.get_track("../outside/secret.mp3") is None

    def test_path_inside_music_dir_still_playable(self, tmp_path):
        music_dir = tmp_path / "music"
        music_dir.mkdir()
        f = music_dir / "song.mp3"
        f.touch()

        source = LocalSource(music_dir=music_dir)
        track = source.get_track(str(f))

        assert track is not None
        assert track.source == str(f.resolve())

    def test_missing_path_inside_music_dir_returns_none(self, tmp_path):
        music_dir = tmp_path / "music"
        music_dir.mkdir()

        source = LocalSource(music_dir=music_dir)

        assert source.get_track(str(music_dir / "missing.mp3")) is None
