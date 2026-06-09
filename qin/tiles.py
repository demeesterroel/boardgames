"""Tile deck for QIN.

Each tile is a 1x2 domino showing two province spaces. A tile is identified by
the (unordered) pair of colours of its two halves. The retail game has 72 tiles:
12 copies of each of the 6 unordered colour pairs
(RR, YY, BB, RY, RB, YB).
"""

from __future__ import annotations

import random
from itertools import combinations_with_replacement

from .board import Color

# A tile type: an unordered pair of colours, stored as a sorted 2-tuple.
TileType = tuple[Color, Color]

TILE_TYPES: list[TileType] = [
    tuple(sorted(pair, key=lambda c: c.value))  # type: ignore[misc]
    for pair in combinations_with_replacement(Color, 2)
]

COPIES_PER_TYPE = 12


def full_deck() -> list[TileType]:
    """The 72-tile deck (order not yet shuffled)."""
    deck: list[TileType] = []
    for t in TILE_TYPES:
        deck.extend([t] * COPIES_PER_TYPE)
    return deck


def shuffled_deck(rng: random.Random) -> list[TileType]:
    deck = full_deck()
    rng.shuffle(deck)
    return deck


def tile_str(tile: TileType) -> str:
    return f"[{tile[0].value}{tile[1].value}]"
