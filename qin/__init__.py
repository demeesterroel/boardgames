"""QIN: a deterministic, headless implementation of Reiner Knizia's QIN (2012).

The engine is the source of truth for the rules; self-play agents and strategy
analysis are built on top of it.
"""

from .board import Board, Cell, Color, Terrain
from .engine import IllegalMove, Move, Province, State
from .tiles import TileType, tile_str

__all__ = [
    "Board",
    "Cell",
    "Color",
    "Terrain",
    "IllegalMove",
    "Move",
    "Province",
    "State",
    "TileType",
    "tile_str",
]
