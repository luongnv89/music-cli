"""Local MP3 file source."""

import heapq
import os
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
        # Resolved dir -> (root mtime_ns at scan time, files found).
        self._scan_cache: dict[Path, tuple[int, list[Path]]] = {}

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

    def _scan_uncached(self, directory: Path) -> list[Path]:
        """Single recursive traversal collecting supported audio files.

        One ``os.walk`` pass filtered on a lowercased suffix replaces the
        per-extension ``rglob`` storm (F-PERF-001): six full traversals
        become one. Unreadable directories are skipped rather than fatal,
        matching the old ``rglob`` behaviour.
        """
        found: list[Path] = []
        supported = self.SUPPORTED_EXTENSIONS
        for root, _dirs, names in os.walk(directory, onerror=lambda _e: None):
            for name in names:
                if Path(name).suffix.lower() in supported:
                    found.append(Path(root) / name)
        return found

    def scan_directory(self, directory: Path | None = None) -> list[Path]:
        """Scan a directory for music files.

        Performs exactly one traversal and caches the result against the
        scanned directory's mtime, so repeated scans of an unchanged
        library (e.g. auto-play advancing at every track end) cost one
        ``stat`` instead of a full walk. The cache is keyed by resolved
        directory; only direct changes to that directory bump its mtime.
        Returns an unsorted copy — callers order results themselves.
        """
        if directory is None:
            directory = self.music_dir

        try:
            key = Path(directory).resolve()
            mtime_ns = key.stat().st_mtime_ns
        except OSError:
            return []

        cached = self._scan_cache.get(key)
        if cached is not None and cached[0] == mtime_ns:
            return list(cached[1])

        files = self._scan_uncached(key)
        self._scan_cache[key] = (mtime_ns, files)
        return list(files)

    def get_random_track(self, directory: Path | None = None) -> TrackInfo | None:
        """Get a random track from the directory."""
        files = self.scan_directory(directory)
        if not files:
            return None

        chosen = random.choice(files)
        return self.get_track(str(chosen))

    def list_tracks(self, directory: Path | None = None, limit: int = 50) -> list[TrackInfo]:
        """List tracks in a directory, sorted, limited during iteration."""
        if limit <= 0:
            return []

        # nsmallest keeps deterministic (sorted) order while stopping once
        # `limit` entries are known (F-PERF-007/005): no full sort of the
        # whole listing, and tracks are built straight from scan results
        # instead of re-stating every file through get_track().
        files = heapq.nsmallest(limit, self.scan_directory(directory))
        return [
            TrackInfo(
                source=str(f),
                source_type="local",
                title=f.stem,
                metadata={"filename": f.name},
            )
            for f in files
        ]
