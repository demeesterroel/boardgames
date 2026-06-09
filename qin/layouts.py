"""Board layouts.

IMPORTANT: the real "Bird" and "Lion" boards are NOT yet accurately digitized.
The rules-sheet only contains small stylized thumbnails, which are not reliable
enough to transcribe every cell. `PROVISIONAL_BOARD` below is a playable
stand-in (3 central starting provinces, a scatter of villages and water) so the
engine and CLI can be exercised end-to-end. Replace it with transcriptions of
the real boards once a clean high-resolution scan is available.

Legend: '#'=water  '.'=grass  'o'=village  'R'/'Y'/'B'=starting province space
"""

from __future__ import annotations

from .board import Board

# Provisional 11x11 playable board (NOT the official Bird/Lion layout).
PROVISIONAL_MAP = """
...........
.o.......o.
...........
....o......
.....RYB...
...........
......o....
...........
.o.......o.
...........
...........
"""


def provisional_board() -> Board:
    return Board.from_ascii(PROVISIONAL_MAP)


# The official "Bird" board: a 12x12 grid with three central starting-province
# spaces stacked B/Y/R in column 5 (rows 4/6/8). Transcribed from a
# straight-down board photo: the grid pitch was measured from the printed grid
# lines (~66 px/cell), the three provinces give the anchor, and every village
# was confirmed by zooming each cell. This supersedes earlier guesses (a 9x9,
# then a 16x16 from an angled photo + vision model — both wrong on size).
BIRD_MAP = """
....oo.....o
............
............
.o......o...
.....B......
............
.....Y......
.o.......oo.
.o...R......
............
............
......oo...o
"""


def bird_board() -> Board:
    return Board.from_ascii(BIRD_MAP)


# ----- small boards used by the rule tests (constructed for clarity) -----

def board_from(lines: list[str]) -> Board:
    return Board.from_ascii("\n".join(lines))
