"""Board model for QIN.

The board is *data*: a rectangular grid of cells. The rules engine is entirely
board-agnostic, so any number of boards (the real "Bird"/"Lion" layouts, or
small synthetic boards for testing) can be plugged in via an ASCII map.

ASCII map legend (one char per cell):
    '#' or ' '   water / off-board  (cannot place, not a province space)
    '.'          grassland          (tiles may be placed here)
    'o' or 'v'   village            (starts empty; can hold one pagoda)
    'R' 'Y' 'B'  starting province space of that colour (pre-printed on board)
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable


class Color(Enum):
    RED = "R"
    YELLOW = "Y"
    BLUE = "B"


class Terrain(Enum):
    WATER = "#"
    GRASS = "."
    VILLAGE = "v"
    PROVINCE = "P"  # a province *space*; its colour is stored in Board.color


_CHAR_TO_COLOR = {"R": Color.RED, "Y": Color.YELLOW, "B": Color.BLUE}
_WATER_CHARS = {"#", " "}
_VILLAGE_CHARS = {"o", "v"}

Cell = tuple[int, int]  # (row, col)


class Board:
    """Mutable grid. Part of the game state (placing tiles colours cells)."""

    def __init__(self, rows: int, cols: int) -> None:
        self.rows = rows
        self.cols = cols
        self.terrain: list[list[Terrain]] = [
            [Terrain.WATER] * cols for _ in range(rows)
        ]
        # colour[r][c] is set only for PROVINCE cells, else None
        self.color: list[list[Color | None]] = [[None] * cols for _ in range(rows)]

    # ------------------------------------------------------------------ build
    @classmethod
    def from_ascii(cls, text: str) -> "Board":
        lines = [ln for ln in text.strip("\n").splitlines()]
        # do not strip interior spaces (space == water); pad to common width
        width = max(len(ln) for ln in lines)
        lines = [ln.ljust(width) for ln in lines]
        board = cls(len(lines), width)
        for r, line in enumerate(lines):
            for c, ch in enumerate(line):
                if ch in _WATER_CHARS:
                    board.terrain[r][c] = Terrain.WATER
                elif ch == ".":
                    board.terrain[r][c] = Terrain.GRASS
                elif ch in _VILLAGE_CHARS:
                    board.terrain[r][c] = Terrain.VILLAGE
                elif ch in _CHAR_TO_COLOR:
                    board.terrain[r][c] = Terrain.PROVINCE
                    board.color[r][c] = _CHAR_TO_COLOR[ch]
                else:
                    raise ValueError(f"Unknown map char {ch!r} at ({r},{c})")
        return board

    def clone(self) -> "Board":
        b = Board(self.rows, self.cols)
        b.terrain = [row[:] for row in self.terrain]
        b.color = [row[:] for row in self.color]
        # neighbour adjacency depends only on grid size -> share the cache
        nbr = getattr(self, "_nbr_cache", None)
        if nbr is not None:
            b._nbr_cache = nbr
        return b

    # -------------------------------------------------------------- accessors
    def in_bounds(self, cell: Cell) -> bool:
        r, c = cell
        return 0 <= r < self.rows and 0 <= c < self.cols

    def terrain_at(self, cell: Cell) -> Terrain:
        return self.terrain[cell[0]][cell[1]]

    def color_at(self, cell: Cell) -> Color | None:
        return self.color[cell[0]][cell[1]]

    def neighbors(self, cell: Cell) -> list[Cell]:
        # Orthogonal neighbours are static for a given grid size, so precompute
        # them once (this is the hottest call under MCTS search).
        cache = getattr(self, "_nbr_cache", None)
        if cache is None:
            cache = {}
            for r in range(self.rows):
                for c in range(self.cols):
                    nb = []
                    if r > 0:
                        nb.append((r - 1, c))
                    if r < self.rows - 1:
                        nb.append((r + 1, c))
                    if c > 0:
                        nb.append((r, c - 1))
                    if c < self.cols - 1:
                        nb.append((r, c + 1))
                    cache[(r, c)] = nb
            self._nbr_cache = cache
        return cache[cell]

    def cells(self) -> Iterable[Cell]:
        for r in range(self.rows):
            for c in range(self.cols):
                yield (r, c)

    def villages(self) -> list[Cell]:
        return [cell for cell in self.cells() if self.terrain_at(cell) is Terrain.VILLAGE]

    def is_grass(self, cell: Cell) -> bool:
        return self.terrain_at(cell) is Terrain.GRASS

    def is_province(self, cell: Cell) -> bool:
        return self.terrain_at(cell) is Terrain.PROVINCE

    # ----------------------------------------------------------------- mutate
    def set_province(self, cell: Cell, color: Color) -> None:
        r, c = cell
        self.terrain[r][c] = Terrain.PROVINCE
        self.color[r][c] = color

    def same_color_component(self, start: Cell) -> frozenset[Cell]:
        """Flood-fill the connected component of same-coloured PROVINCE cells."""
        color = self.color_at(start)
        if color is None:
            return frozenset()
        seen: set[Cell] = {start}
        stack = [start]
        while stack:
            cur = stack.pop()
            for n in self.neighbors(cur):
                if n not in seen and self.is_province(n) and self.color_at(n) == color:
                    seen.add(n)
                    stack.append(n)
        return frozenset(seen)
