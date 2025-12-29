"""Player module for music-cli."""

from .base import Player, PlayerState
from .ffplay import FFplayPlayer

__all__ = ["Player", "PlayerState", "FFplayPlayer"]
