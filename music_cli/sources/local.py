"""Local MP3 file source."""

import random
from pathlib import Path

from ..player.base import TrackInfo


class LocalSource:
    """Handles local MP3 file playback."""

    SUPPORTED_EXTENSIONS = {".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus"}

    def __init__(self, music_dir: Path | None = None):
        """Initialize with optional music directory."""
        if music_dir is None:
            # Default to ~/Music
            music_dir = Path("~/Music").expanduser()
        self.music_dir = music_dir

    def get_track(self, path: str) -> TrackInfo | None:
        """Get track info for a specific file path.

        Playback is confined to ``music_dir``: the requested path is
        fully resolved (following symlinks) and must land inside the
        configured music directory. Anything outside it — including a
        symlink inside ``music_dir`` pointing elsewhere — returns
        ``None``. This prevents local IPC clients from making the
        daemon open arbitrary audio files on the filesystem.
        Out-of-tree playback is intentionally not supported (no opt-in).
        """
        file_path = Path(path)

        if not file_path.is_absolute():
            # Prefer a match relative to the current working directory;
            # resolve it now so the result doesn't depend on cwd staying
            # the same for the rest of the call chain (e.g. across the
            # daemon's IPC boundary). Fall back to the configured music dir.
            if file_path.exists():
                file_path = file_path.resolve()
            else:
                file_path = self.music_dir / file_path

        # Resolve before the boundary check so a symlink inside
        # music_dir cannot smuggle in a target outside of it.
        file_path = file_path.resolve()
        boundary = self.music_dir.resolve()

        if not file_path.is_relative_to(boundary):
            return None

        if not file_path.exists():
            return None

        if file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            return None

        return TrackInfo(
            source=str(file_path),
            source_type="local",
            title=file_path.stem,
            metadata={"filename": file_path.name},
        )

    def scan_directory(self, directory: Path | None = None) -> list[Path]:
        """Scan a directory for music files."""
        if directory is None:
            directory = self.music_dir

        if not directory.exists():
            return []

        files: list[Path] = []
        for ext in self.SUPPORTED_EXTENSIONS:
            files.extend(directory.rglob(f"*{ext}"))

        return sorted(files)

    def get_random_track(self, directory: Path | None = None) -> TrackInfo | None:
        """Get a random track from the directory."""
        files = self.scan_directory(directory)
        if not files:
            return None

        chosen = random.choice(files)
        return self.get_track(str(chosen))

    def list_tracks(self, directory: Path | None = None, limit: int = 50) -> list[TrackInfo]:
        """List tracks in a directory."""
        files = self.scan_directory(directory)
        tracks = []

        for f in files[:limit]:
            track = self.get_track(str(f))
            if track:
                tracks.append(track)

        return tracks
