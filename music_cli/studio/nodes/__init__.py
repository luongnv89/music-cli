"""Studio nodes for audio assets and H3-backed video scenes.

Each node writes its generated asset into the project's ``nodes/`` directory,
runs a probe (``ffprobe``), and locks itself on success so a locked asset is
never regenerated without an explicit :meth:`~music_cli.studio.nodes.base
.BaseNode.unlock`.

Like :mod:`music_cli.studio.schemas`, this package is stdlib-only: concrete
nodes depend on the adapter *interface* (async ``music3_generate`` /
``speech28_synthesize`` methods) but never on keyring/httpx, so it is
importable in any install. The audio downloader and probe runner are injectable
so tests drive a recorded fixture with no network and no bare ``ffprobe``.
"""

from .assemble import AssembleNode, AssembleNodeError
from .base import (
    BaseNode,
    NodeError,
    NodeLockedError,
    NodeProtocol,
    default_download,
    run_ffprobe,
)
from .ffmpeg import (
    MixNode,
    MixNodeError,
    resolve_binary,
    write_srt,
)
from .music import MusicNode
from .speech import SpeechNode
from .video import BudgetExceeded, BuildBudget, VideoNode

__all__ = [
    "AssembleNode",
    "AssembleNodeError",
    "BaseNode",
    "BuildBudget",
    "BudgetExceeded",
    "MixNode",
    "MixNodeError",
    "MusicNode",
    "NodeError",
    "NodeLockedError",
    "NodeProtocol",
    "SpeechNode",
    "VideoNode",
    "default_download",
    "resolve_binary",
    "run_ffprobe",
    "write_srt",
]
