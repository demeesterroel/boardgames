"""QIN rules engine.

Pure, deterministic game logic. No UI, no AI. Everything a player does on a turn
is: choose one tile from hand, place it on two adjacent grassland cells (with a
colour assignment), then draw a replacement tile.

Placing a tile resolves, in order:
  * province events  (found / expand / create-major / absorb)  -- per colour
  * village events   (connect / conquer)                       -- all villages

The six rulebook events are unified into two passes:

Province pass (per resulting same-colour connected component C):
  - 0 pre-existing owned provinces in C: FOUND  (if |C|>=2; the active player
    places a pagoda; double pagoda if |C|>=5)
  - 1 pre-existing owned province in C: EXPAND  (owner unchanged; upgrades to a
    major province / double pagoda if it reaches >=5 spaces)
  - >=2 pre-existing owned provinces in C: ABSORB (forms a major province; owner
    is whoever contributed the most province spaces; combining two majors, or an
    exact contribution tie, is illegal)

Village pass (every village):
  - owner becomes the unique player with the most adjoining pagodas
    (a double pagoda counts as 2), but only if that strictly beats the current
    owner's adjoining count. Ties never seize. This unifies connect (from
    unowned) and conquer (from another player).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace as dc_replace

from .board import Board, Cell, Color, Terrain
from .tiles import TileType, shuffled_deck

# pagodas available per player, keyed by player count
PAGODAS_BY_PLAYERS = {2: 24, 3: 19, 4: 15}
MAJOR_THRESHOLD = 5
HAND_SIZE = 3


class IllegalMove(Exception):
    """Raised when a placement violates the rules (e.g. an undeterminable absorb)."""


@dataclass(frozen=True)
class Province:
    cells: frozenset[Cell]
    color: Color
    owner: int
    major: bool

    @property
    def pagoda_weight(self) -> int:
        return 2 if self.major else 1


@dataclass(frozen=True)
class Move:
    """Place a tile so that `cell_a` gets `color_a` and `cell_b` gets `color_b`.

    `cell_a` and `cell_b` must be orthogonally adjacent grassland cells.
    """

    cell_a: Cell
    color_a: Color
    cell_b: Cell
    color_b: Color

    @property
    def tile(self) -> TileType:
        return tuple(sorted((self.color_a, self.color_b), key=lambda c: c.value))  # type: ignore[return-value]


class State:
    def __init__(self, board: Board, num_players: int, seed: int | None = None) -> None:
        if num_players not in PAGODAS_BY_PLAYERS:
            raise ValueError("QIN supports 2-4 players")
        self.board = board
        self.num_players = num_players
        self.rng = random.Random(seed)
        self.allotment = PAGODAS_BY_PLAYERS[num_players]
        self.provinces: list[Province] = []
        self.village_owner: dict[Cell, int] = {}  # only present once seized
        self.current_player = 0
        self.winner: int | None = None
        self.shared_winners: list[int] | None = None  # set on a tie at game end
        self.game_over = False

        self.deck: list[TileType] = shuffled_deck(self.rng)
        self.hands: list[list[TileType]] = [[] for _ in range(num_players)]
        for _ in range(HAND_SIZE):
            for pl in range(num_players):
                if self.deck:
                    self.hands[pl].append(self.deck.pop())

    # ------------------------------------------------------------------ clone
    def clone(self) -> "State":
        s = State.__new__(State)
        s.board = self.board.clone()
        s.num_players = self.num_players
        s.rng = random.Random()
        s.rng.setstate(self.rng.getstate())
        s.allotment = self.allotment
        s.provinces = list(self.provinces)
        s.village_owner = dict(self.village_owner)
        s.current_player = self.current_player
        s.winner = self.winner
        s.shared_winners = None if self.shared_winners is None else list(self.shared_winners)
        s.game_over = self.game_over
        s.deck = list(self.deck)
        s.hands = [h[:] for h in self.hands]
        s._anchor_cache = getattr(self, "_anchor_cache", None)  # same board pos
        s._c2p_cache = getattr(self, "_c2p_cache", None)
        return s

    # ------------------------------------------------------------ determinize
    def determinize(self, observer: int, rng: random.Random) -> "State":
        """Return a clone with the hidden information randomly resampled from
        `observer`'s point of view.

        What `observer` can see: their own hand, the board, and how many tiles
        every opponent holds and how many remain in the deck. What is hidden:
        the *identity* of opponents' tiles and the deck order. We pool all those
        unseen tiles, reshuffle, and redeal the same counts. The full 72-tile
        composition is known, so the pool is (deck composition) exactly.
        """
        s = self.clone()
        pool = list(s.deck)
        for pl in range(s.num_players):
            if pl != observer:
                pool.extend(s.hands[pl])
        rng.shuffle(pool)
        for pl in range(s.num_players):
            if pl != observer:
                k = len(s.hands[pl])
                s.hands[pl] = pool[:k]
                del pool[:k]
        s.deck = pool
        # give the clone its own independent RNG stream for rollouts
        s.rng = random.Random(rng.random())
        return s


    # -------------------------------------------------------------- pagodas
    def on_board(self) -> list[int]:
        counts = [0] * self.num_players
        for p in self.provinces:
            counts[p.owner] += p.pagoda_weight
        for owner in self.village_owner.values():
            counts[owner] += 1
        return counts

    def supply(self, player: int) -> int:
        return self.allotment - self.on_board()[player]

    # ----------------------------------------------------------- legal moves
    def _touches_existing_province(self, cell_a: Cell, cell_b: Cell) -> bool:
        """At least one of the two cells must edge-share with a pre-existing
        province space of any colour (the other tile cell does not count)."""
        for cell, other in ((cell_a, cell_b), (cell_b, cell_a)):
            for n in self.board.neighbors(cell):
                if n != other and self.board.is_province(n):
                    return True
        return False

    def _candidate_placements(self) -> list[tuple[Cell, Cell]]:
        """Each unordered pair of adjacent grassland cells, once."""
        pairs: list[tuple[Cell, Cell]] = []
        for r in range(self.board.rows):
            for c in range(self.board.cols):
                cell = (r, c)
                if not self.board.is_grass(cell):
                    continue
                for n in ((r, c + 1), (r + 1, c)):  # right, down -> each pair once
                    if self.board.in_bounds(n) and self.board.is_grass(n):
                        pairs.append((cell, n))
        return pairs

    def _anchor_pairs(self) -> list[tuple[Cell, Cell]]:
        """Adjacent grassland pairs that touch an existing province. Independent
        of the hand, and only change when the board changes, so cache them."""
        cached = getattr(self, "_anchor_cache", None)
        if cached is not None:
            return cached
        anchors = [(a, b) for (a, b) in self._candidate_placements()
                   if self._touches_existing_province(a, b)]
        self._anchor_cache = anchors
        return anchors

    def legal_moves(self, player: int | None = None) -> list[Move]:
        player = self.current_player if player is None else player
        if self.game_over:
            return []
        hand_types = {t for t in self.hands[player]}
        moves: list[Move] = []
        for (a, b) in self._anchor_pairs():
            for tile in hand_types:
                ca, cb = tile
                assignments = {(ca, cb), (cb, ca)}  # set dedupes monochrome tiles
                for col_a, col_b in assignments:
                    move = Move(a, col_a, b, col_b)
                    if self._is_legal(move, player):
                        moves.append(move)
        return moves

    def _cell_to_province(self) -> dict[Cell, "Province"]:
        """Map each province-space cell to its Province (cached per board pos)."""
        cached = getattr(self, "_c2p_cache", None)
        if cached is not None:
            return cached
        c2p: dict[Cell, "Province"] = {}
        for p in self.provinces:
            for cell in p.cells:
                c2p[cell] = p
        self._c2p_cache = c2p
        return c2p

    def _merged_groups(self, move: Move) -> list[list["Province"]]:
        """The groups of *pre-existing* provinces that the placement would merge
        into a single new component, one list per resulting component.

        Key fact: ``a`` and ``b`` are the only new cells, so any pre-existing
        province pulled into a new component must be edge-adjacent to ``a`` or
        ``b`` with the matching colour. No flood-fill needed.
        """
        a, b = move.cell_a, move.cell_b
        ca, cb = move.color_a, move.color_b
        c2p = self._cell_to_province()

        def adj_provinces(cell: Cell, color, exclude: Cell) -> list["Province"]:
            out: list["Province"] = []
            seen: set[int] = set()
            for n in self.board.neighbors(cell):
                if n == exclude:
                    continue
                p = c2p.get(n)
                if p is not None and p.color == color and id(p) not in seen:
                    seen.add(id(p))
                    out.append(p)
            return out

        if ca == cb:
            # a and b are adjacent and same colour -> one combined component
            seen: set[int] = set()
            group: list["Province"] = []
            for p in adj_provinces(a, ca, b) + adj_provinces(b, cb, a):
                if id(p) not in seen:
                    seen.add(id(p))
                    group.append(p)
            return [group]
        # different colours -> two independent components
        return [adj_provinces(a, ca, b), adj_provinces(b, cb, a)]

    def _is_legal(self, move: Move, player: int) -> bool:
        """Fast legality check (no clone, no flood-fill).

        Geometry is already guaranteed for candidates from ``legal_moves``. The
        only way a placement is illegal is the *absorb* rule: a new component
        merging >=2 existing provinces where either two are major or the
        largest-contributor is tied. The merged provinces are found purely from
        the neighbours of the two placed cells (see ``_merged_groups``).
        """
        for group in self._merged_groups(move):
            if len(group) >= 2:
                if sum(1 for p in group if p.major) >= 2:
                    return False
                contrib: dict[int, int] = {}
                for p in group:
                    contrib[p.owner] = contrib.get(p.owner, 0) + len(p.cells)
                top = max(contrib.values())
                if sum(1 for v in contrib.values() if v == top) != 1:
                    return False
        return True

    # ------------------------------------------------- fast helpers for search
    def random_legal_move(self, rng: random.Random) -> Move | None:
        """Return one random legal move without enumerating them all (for fast
        rollouts). Tries shuffled (anchor, tile, orientation) combos."""
        player = self.current_player
        anchors = self._anchor_pairs()
        if not anchors:
            return None
        tiles = list({t for t in self.hands[player]})
        order = list(range(len(anchors)))
        rng.shuffle(order)
        for idx in order:
            a, b = anchors[idx]
            rng.shuffle(tiles)
            for tile in tiles:
                ca, cb = tile
                orients = [(ca, cb)] if ca == cb else (
                    [(ca, cb), (cb, ca)] if rng.random() < 0.5 else [(cb, ca), (ca, cb)])
                for col_a, col_b in orients:
                    m = Move(a, col_a, b, col_b)
                    if self._is_legal(m, player):
                        return m
        return None

    def score_move(self, move: Move, me: int) -> int:
        """Greedy heuristic score (pagodas the mover would place this turn * 10
        + majors), computed from the merged-province groups without cloning or
        flood-fill. The new component's size = (cells the merged provinces hold)
        + the new cell(s) feeding that component."""
        groups = self._merged_groups(move)
        a_is_b_color = move.color_a == move.color_b
        gained = 0
        majors = 0
        # number of newly placed cells contributing to each component
        if a_is_b_color:
            new_cells_for = [2]                  # one component fed by both cells
        else:
            new_cells_for = [1, 1]               # two components, one cell each
        for group, new_cells in zip(groups, new_cells_for):
            existing = sum(len(p.cells) for p in group)
            size = existing + new_cells
            if not group:
                if size >= 2:
                    gained += 2 if size >= MAJOR_THRESHOLD else 1
                    if size >= MAJOR_THRESHOLD:
                        majors += 1
            elif len(group) == 1:
                if size >= MAJOR_THRESHOLD and not group[0].major:
                    gained += 1
                    majors += 1
            else:
                contrib: dict[int, int] = {}
                for p in group:
                    contrib[p.owner] = contrib.get(p.owner, 0) + len(p.cells)
                top = max(contrib.values())
                winners = [o for o, v in contrib.items() if v == top]
                if len(winners) == 1 and winners[0] == me:
                    majors += 1
        return gained * 10 + majors

    # ------------------------------------------------------------- apply move
    def apply(self, move: Move) -> list[str]:
        if self.game_over:
            raise IllegalMove("game is over")
        player = self.current_player
        if move.tile not in self.hands[player]:
            raise IllegalMove("tile not in hand")
        events = self._resolve_placement(move, player)
        self.hands[player].remove(move.tile)
        if not self.game_over:
            if self.deck:
                self.hands[player].append(self.deck.pop())
            self._advance_turn()
        return events

    def _advance_turn(self) -> None:
        self.current_player = (self.current_player + 1) % self.num_players
        # secondary end condition: the player to act has no legal move at all
        if not self.legal_moves(self.current_player):
            self._end_by_blockage()

    def _end_by_blockage(self) -> None:
        counts = self.on_board()
        best = max(counts)
        winners = [pl for pl, n in enumerate(counts) if n == best]
        self.game_over = True
        if len(winners) == 1:
            self.winner = winners[0]
        else:
            self.shared_winners = winners

    # ------------------------------------------------------- core resolution
    def _resolve_placement(self, move: Move, player: int) -> list[str]:
        a, b = move.cell_a, move.cell_b
        # --- validation ---
        if not (self.board.in_bounds(a) and self.board.in_bounds(b)):
            raise IllegalMove("off-board")
        if b not in self.board.neighbors(a):
            raise IllegalMove("cells not adjacent")
        if not (self.board.is_grass(a) and self.board.is_grass(b)):
            raise IllegalMove("must place on two grassland cells")
        if not self._touches_existing_province(a, b):
            raise IllegalMove("tile must touch an existing province space")

        events: list[str] = []
        self.board.set_province(a, move.color_a)
        self.board.set_province(b, move.color_b)
        self._anchor_cache = None  # board changed: invalidate caches
        self._c2p_cache = None

        # --- province pass: one component per placed cell (deduped) ---
        components: dict[frozenset[Cell], None] = {}
        for cell in (a, b):
            comp = self.board.same_color_component(cell)
            components[comp] = None
        for comp in components:
            events.extend(self._resolve_province(comp, player))

        # --- village pass ---
        events.extend(self._resolve_villages())

        # --- win / pagoda check ---
        if self.supply(player) <= 0:
            self.winner = player
            self.game_over = True
            events.append(f"P{player} placed their last pagoda and WINS!")
        return events

    def _resolve_province(self, comp: frozenset[Cell], player: int) -> list[str]:
        color = self.board.color_at(next(iter(comp)))
        assert color is not None
        size = len(comp)
        prev = [p for p in self.provinces if p.cells & comp]
        events: list[str] = []

        if not prev:
            if size < 2:
                return events  # a lone province space is not a province
            major = size >= MAJOR_THRESHOLD
            new = Province(comp, color, player, major)
            self.provinces.append(new)
            kind = "major province" if major else "province"
            events.append(f"P{player} founds a {color.value} {kind} ({size} spaces)")
        elif len(prev) == 1:
            p0 = prev[0]
            major = p0.major or size >= MAJOR_THRESHOLD
            new = Province(comp, color, p0.owner, major)
            self.provinces.remove(p0)
            self.provinces.append(new)
            if major and not p0.major:
                events.append(
                    f"P{p0.owner} expands {color.value} province to {size} "
                    f"spaces -> now MAJOR"
                )
            else:
                events.append(
                    f"P{p0.owner} expands {color.value} province to {size} spaces"
                )
        else:  # absorb
            if sum(1 for p in prev if p.major) >= 2:
                raise IllegalMove("cannot combine two major provinces")
            contrib: dict[int, int] = {}
            for p in prev:
                contrib[p.owner] = contrib.get(p.owner, 0) + len(p.cells)
            top = max(contrib.values())
            winners = [o for o, v in contrib.items() if v == top]
            if len(winners) != 1:
                raise IllegalMove("absorb contribution tie: owner undeterminable")
            owner = winners[0]
            new = Province(comp, color, owner, True)
            for p in prev:
                self.provinces.remove(p)
            self.provinces.append(new)
            losers = sorted({p.owner for p in prev} - {owner})
            events.append(
                f"P{owner} absorbs {color.value} provinces into a major province "
                f"({size} spaces; dislodged: "
                f"{', '.join(f'P{l}' for l in losers) or 'none'})"
            )
        return events

    def _resolve_villages(self) -> list[str]:
        events: list[str] = []
        # map province cell -> province for adjacency lookups
        cell_to_prov: dict[Cell, Province] = {}
        for p in self.provinces:
            for cell in p.cells:
                cell_to_prov[cell] = p

        for v in self.board.villages():
            adjoining: set[Province] = set()
            for n in self.board.neighbors(v):
                prov = cell_to_prov.get(n)
                if prov is not None:
                    adjoining.add(prov)
            weight: dict[int, int] = {}
            for p in adjoining:
                weight[p.owner] = weight.get(p.owner, 0) + p.pagoda_weight
            if not weight:
                continue
            cur = self.village_owner.get(v)
            cur_w = weight.get(cur, 0) if cur is not None else 0
            top = max(weight.values())
            leaders = [o for o, w in weight.items() if w == top]
            if len(leaders) == 1 and top > cur_w:
                new_owner = leaders[0]
                if new_owner != cur:
                    verb = "connects" if cur is None else f"conquers (from P{cur})"
                    self.village_owner[v] = new_owner
                    events.append(f"P{new_owner} {verb} village at {v}")
        return events

    # --------------------------------------------------------------- queries
    def is_terminal(self) -> bool:
        return self.game_over

    def result(self) -> dict:
        return {
            "winner": self.winner,
            "shared_winners": self.shared_winners,
            "on_board": self.on_board(),
        }
