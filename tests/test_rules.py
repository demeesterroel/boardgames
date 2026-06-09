"""Rule-by-rule verification of the QIN engine.

Each test builds a small, controlled board and drives the core resolver
(`State._resolve_placement`) directly, so the six rulebook events are checked in
isolation. White-box access to `state.provinces` / `state.village_owner` is
intentional: these tests pin the rules, not the public API.
"""

import random

import pytest

from qin.board import Board, Color
from qin.engine import IllegalMove, Move, Province, State


def make_state(map_text: str, num_players: int = 2) -> State:
    board = Board.from_ascii(map_text)
    return State(board, num_players=num_players, seed=0)


R, Y, B = Color.RED, Color.YELLOW, Color.BLUE


# --------------------------------------------------------------- 1. found
def test_found_province():
    s = make_state("R..\n...")
    # place R at (0,1) and (0,2); joins starting space (0,0) -> 3-space province
    s._resolve_placement(Move((0, 1), R, (0, 2), R), player=0)
    assert len(s.provinces) == 1
    p = s.provinces[0]
    assert p.owner == 0 and p.color is R and not p.major
    assert p.cells == frozenset({(0, 0), (0, 1), (0, 2)})
    assert s.on_board() == [1, 0]


def test_two_single_spaces_create_no_province():
    # A tile that only forms two isolated single spaces founds nothing.
    s = make_state("R.\nB.\n..")
    s._resolve_placement(Move((0, 1), B, (1, 1), R), player=0)
    assert s.provinces == []
    assert s.on_board() == [0, 0]


# ------------------------------------------------------ 2/3. expand + major
def test_expand_then_create_major():
    s = make_state("R.....\n......")
    s._resolve_placement(Move((0, 1), R, (0, 2), R), player=0)  # found size 3
    assert not s.provinces[0].major
    s._resolve_placement(Move((0, 3), R, (0, 4), R), player=0)  # -> size 5 major
    assert len(s.provinces) == 1
    p = s.provinces[0]
    assert p.major and p.owner == 0
    assert len(p.cells) == 5
    assert s.on_board() == [2, 0]  # double pagoda counts as 2


# --------------------------------------------------------- 4. connect village
def test_connect_unoccupied_village():
    s = make_state("R..\no..")
    s._resolve_placement(Move((0, 1), R, (0, 2), R), player=0)
    assert s.village_owner == {(1, 0): 0}
    assert s.on_board() == [2, 0]  # 1 province + 1 village


# --------------------------------------------------------- 5. conquer village
def test_conquer_village_by_majority_double_counts_two():
    s = make_state("Y....\no....\nR....\n.....\n.....")
    # P1 founds a Y province touching the village -> connects it
    s._resolve_placement(Move((0, 1), Y, (1, 1), Y), player=1)
    assert s.village_owner == {(1, 0): 1}
    # P0 builds an R major province also adjoining the village (via (2,0))
    s._resolve_placement(Move((2, 1), R, (3, 1), R), player=0)  # found size 3
    s._resolve_placement(Move((3, 0), R, (4, 0), R), player=0)  # -> size 5 major
    p0_prov = [p for p in s.provinces if p.owner == 0][0]
    assert p0_prov.major  # weight 2
    # weight: P0 (major, 2) > P1 (single, 1) -> P0 conquers
    assert s.village_owner == {(1, 0): 0}


def test_village_tie_does_not_seize():
    # Two single provinces of equal weight adjoin the village -> no seize.
    s = make_state("Y.R\n.o.\n...")
    # Manually set two equal single-weight provinces adjoining village (1,1).
    s.board.set_province((0, 0), Y)
    s.board.set_province((1, 0), Y)
    s.board.set_province((0, 2), R)
    s.board.set_province((1, 2), R)
    s.provinces = [
        Province(frozenset({(0, 0), (1, 0)}), Y, 0, False),
        Province(frozenset({(0, 2), (1, 2)}), R, 1, False),
    ]
    events = s._resolve_villages()
    assert s.village_owner == {}  # tie -> unowned
    assert events == []


# ---------------------------------------------------------- 6. absorb
def _two_red_provinces(s: State, a_owner: int, a_cells, b_owner: int, b_cells):
    for c in a_cells + b_cells:
        s.board.set_province(c, R)
    s.provinces = [
        Province(frozenset(a_cells), R, a_owner, len(a_cells) >= 5),
        Province(frozenset(b_cells), R, b_owner, len(b_cells) >= 5),
    ]


def test_absorb_owner_is_largest_contributor():
    s = make_state("RR..RRR")
    _two_red_provinces(s, 0, [(0, 0), (0, 1)], 1, [(0, 4), (0, 5), (0, 6)])
    # bridge the gap with an RR tile at (0,2),(0,3)
    s._resolve_placement(Move((0, 2), R, (0, 3), R), player=0)
    assert len(s.provinces) == 1
    p = s.provinces[0]
    assert p.major and len(p.cells) == 7
    assert p.owner == 1  # P1 contributed 3 spaces > P0's 2
    assert s.on_board() == [0, 2]


def test_absorb_exact_tie_is_illegal():
    s = make_state("RR.RR\n..Y..")
    s.board.set_province((0, 0), R)
    s.board.set_province((0, 1), R)
    s.board.set_province((0, 3), R)
    s.board.set_province((0, 4), R)
    s.provinces = [
        Province(frozenset({(0, 0), (0, 1)}), R, 0, False),
        Province(frozenset({(0, 3), (0, 4)}), R, 1, False),
    ]
    # RY tile: R at (0,2) bridges the two equal provinces -> undeterminable owner
    with pytest.raises(IllegalMove):
        s._resolve_placement(Move((0, 2), R, (1, 2), Y), player=0)


def test_cannot_combine_two_majors():
    s = make_state("RRRRR.RRRRR\n.....Y.....")
    cells_a = [(0, c) for c in range(5)]
    cells_b = [(0, c) for c in range(6, 11)]
    for c in cells_a + cells_b:
        s.board.set_province(c, R)
    s.provinces = [
        Province(frozenset(cells_a), R, 0, True),
        Province(frozenset(cells_b), R, 1, True),
    ]
    with pytest.raises(IllegalMove):
        s._resolve_placement(Move((0, 5), R, (1, 5), Y), player=0)


# ---------------------------------------------------- legal-move generation
def test_legal_moves_filters_illegal_absorbs():
    s = make_state("RR.RR\n.....")
    s.board.set_province((0, 0), R)
    s.board.set_province((0, 1), R)
    s.board.set_province((0, 3), R)
    s.board.set_province((0, 4), R)
    s.provinces = [
        Province(frozenset({(0, 0), (0, 1)}), R, 0, False),
        Province(frozenset({(0, 3), (0, 4)}), R, 1, False),
    ]
    # give the active player an RR tile and verify no illegal bridge move appears
    s.hands[0] = [(R, R)]
    moves = s.legal_moves(0)
    bridge = Move((0, 2), R, (1, 2), R)  # not even a real candidate, sanity
    for m in moves:
        # an RR move that fills (0,2) and an adjacent grass would tie-absorb;
        # ensure none of the returned moves are the undeterminable bridge
        assert not (
            {m.cell_a, m.cell_b} == {(0, 2), (1, 2)}
        )


def test_legal_moves_require_touching_a_province():
    s = make_state("R....\n.....\n.....")
    s.hands[0] = [(R, R)]
    for m in s.legal_moves(0):
        # every legal placement must have a cell edge-adjacent to (0,0)
        assert s._touches_existing_province(m.cell_a, m.cell_b)


# ---------------------------------------------------------- self-play smoke
def test_random_playthrough_terminates():
    board = Board.from_ascii(
        "...........\n"
        ".o.......o.\n"
        "...........\n"
        "....o......\n"
        ".....RYB...\n"
        "...........\n"
        "......o....\n"
        "...........\n"
        ".o.......o.\n"
        "...........\n"
        "...........\n"
    )
    rng = random.Random(123)
    for _ in range(5):  # a few seeds
        s = State(board.clone(), num_players=2, seed=rng.randint(0, 10**6))
        steps = 0
        while not s.is_terminal() and steps < 2000:
            moves = s.legal_moves()
            if not moves:
                break
            s.apply(rng.choice(moves))
            steps += 1
        assert s.is_terminal() or steps < 2000
