"""Shared audio node plumbing (issue #137, task P3.1).

Defines the :class:`NodeProtocol` every node exposes — ``generate``,
``probe``, ``lock``, ``unlock``, ``path`` — and :class:`BaseNode`, the
concrete download/probe/lock lifecycle that both :class:`MusicNode` and
:class:`SpeechNode` share. Audio is written into the project's ``nodes/``
directory; once a node renders successfully it locks itself so a locked
asset is never regenerated without an explicit :meth:`BaseNode.unlock`.

Like :mod:`music_cli.studio.schemas`, this module is stdlib-only: the GMI
adapter is duck-typed (async ``music3_generate`` / ``speech28_synthesize``
methods) and the downloader/probe are injectable, so tests replay a
recorded fixture with no network and no bare ``ffprobe``.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..trace import NODES_DIRNAME

#: Default ``ffprobe`` binary looked up on PATH.
DEFAULT_FFPROBE = "ffprobe"

#: Injectable audio downloader signature: ``(url, dest) -> bytes written``.
Downloader = Callable[[str, Path], Awaitable[int]]
#: Injectable probe runner signature: ``(path) -> probe dict``.
ProbeRunner = Callable[[Path], dict[str, Any]]


class NodeError(Exception):
    """The node could not generate, download, or probe its output."""


class NodeLockedError(NodeError):
    """The node is locked and must be unlocked before regenerating."""


@runtime_checkable
class NodeProtocol(Protocol):
    """The surface every studio node exposes."""

    @property
    def path(self) -> Path | None: ...

    async def generate(self, *args: Any, **kwargs: Any) -> Path: ...

    def probe(self) -> dict[str, Any]: ...

    def lock(self) -> None: ...

    def unlock(self) -> None: ...


class FfprobeProbe:
    """Probe runner that shells out to a real ``ffprobe`` binary."""

    def __init__(self, binary: str = DEFAULT_FFPROBE) -> None:
        self.binary = binary

    def __call__(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise NodeError(f"cannot probe missing file: {path}")
        if shutil.which(self.binary) is None:
            raise NodeError(f"'{self.binary}' not on PATH; install ffmpeg or inject a probe")
        cmd = [
            self.binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ]
        try:
            done = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError) as exc:
            raise NodeError(f"{self.binary} failed probing {path}: {exc}") from exc
        data = json.loads(done.stdout or "{}")
        fmt = data.get("format") or {}
        duration: float | None = None
        if fmt.get("duration") is not None:
            try:
                duration = float(fmt["duration"])
            except (TypeError, ValueError):
                duration = None
        return {"path": path, "duration_seconds": duration, "ok": duration is not None}


def run_ffprobe(path: Path) -> dict[str, Any]:
    """Probe ``path`` with a fresh :class:`FfprobeProbe`."""
    return FfprobeProbe()(path)


def _urllib_fetch(url: str, dest: Path) -> int:
    import urllib.request

    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310  # nosec B310
        data = resp.read()
        dest.write_bytes(data)
        return len(data)


async def default_download(url: str, dest: Path) -> int:
    """Download ``url`` to ``dest`` via the stdlib; returns bytes written."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    return await asyncio.to_thread(_urllib_fetch, url, dest)


class BaseNode(ABC):
    """Shared audio-node lifecycle.

    A concrete node supplies :attr:`FILENAME_STEM` and implements
    :meth:`_synthesize`, which calls the adapter method and returns
    ``(audio_url, destination)``. :meth:`generate` then downloads the audio
    into the project's ``nodes/`` directory, runs the probe, and locks the
    node on success. If the probe fails, the output is removed and left
    unlocked. The downloader and probe are injectable so tests can replay a
    recorded fixture without network access or a bare ``ffprobe``.
    """

    FILENAME_STEM: str = "asset"
    EXTENSION: str = ".wav"

    def __init__(
        self,
        adapter: Any,
        *,
        proj_dir: str | Path,
        downloader: Downloader | None = None,
        probe: ProbeRunner | None = None,
    ) -> None:
        self.adapter = adapter
        self._proj_dir = Path(proj_dir)
        self._nodes_dir = self._proj_dir / NODES_DIRNAME
        self._downloader = downloader if downloader is not None else default_download
        self._probe = probe if probe is not None else FfprobeProbe()
        self._path: Path | None = None
        self._ordinal = 0
        self._locked = False

    # -- NodeProtocol surface ------------------------------------------------

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def project_dir(self) -> Path:
        return self._proj_dir

    def lock(self) -> None:
        self._locked = True

    def unlock(self) -> None:
        self._locked = False

    def probe(self) -> dict[str, Any]:
        if self._path is None:
            raise NodeError(f"{self.FILENAME_STEM}: nothing generated to probe")
        return self._probe(self._path)

    # -- lifecycle -----------------------------------------------------------

    async def generate(self, *args: Any, **kwargs: Any) -> Path:
        if self._locked:
            raise NodeLockedError(
                f"{self.FILENAME_STEM}: locked; call unlock() before regenerating"
            )
        url, dest = await self._synthesize(*args, **kwargs)
        self._nodes_dir.mkdir(parents=True, exist_ok=True)
        await self._downloader(url, dest)
        self._path = dest
        report = self._probe(dest)
        if not report.get("ok"):
            try:
                dest.unlink(missing_ok=True)
            except OSError:
                pass
            raise NodeError(f"{self.FILENAME_STEM}: probe failed for {dest}")
        self._locked = True
        return dest

    @abstractmethod
    async def _synthesize(self, *args: Any, **kwargs: Any) -> tuple[str, Path]:
        """Call the adapter and return ``(audio_url, destination path)``."""
        raise NotImplementedError

    def _next_path(self) -> Path:
        self._ordinal += 1
        return self._nodes_dir / f"{self.FILENAME_STEM}-{self._ordinal}{self.EXTENSION}"
