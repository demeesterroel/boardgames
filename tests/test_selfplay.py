"""Tests for the self-play layer: determinize, agents, and the fast legality
check (which must agree with the original clone-based resolution)."""

import random
from collections import Counter

from qin.agents import GreedyAgent, MCTSAgent, RandomAgent
from qin.engine import IllegalMove, Move, State
from qin.layouts import bird_board
from qin.selfplay import play_game


def all_tiles(state: State) -> Counter:
    c: Counter = Counter()
    for h in state.hands:
        c.update(h)
    c.update(state.deck)
    return c


def test_determinize_preserves_observer_and_multiset():
    s = State(bird_board(), 3, seed=1)
    rng = random.Random(0)
    for _ in range(10):
        s.apply(rng.choice(s.legal_moves()))
    obs = s.current_player
    before = all_tiles(s)
    d = s.determinize(obs, random.Random(7))
    assert d.hands[obs] == s.hands[obs]            # observer hand untouched
    for pl in range(3):
        assert len(d.hands[pl]) == len(s.hands[pl])  # counts preserved
    assert all_tiles(d) == before                  # full multiset conserved
    assert d.board.color == s.board.color          # board unchanged


def test_fast_legality_matches_full_resolution():
    """The optimized _is_legal must agree with a full clone+resolve on every
    candidate placement across a real game."""
    s = State(bird_board(), 2, seed=3)
    rng = random.Random(3)
    for _ in range(40):
        if s.is_terminal():
            break
        player = s.current_player
        # check agreement for all candidate (placement,tile,orientation) combos
        for (a, b) in s._candidate_placements():
            if not s._touches_existing_province(a, b):
                continue
            for tile in {t for t in s.hands[player]}:
                for ca, cb in {(tile[0], tile[1]), (tile[1], tile[0])}:
                    m = Move(a, ca, b, cb)
                    fast = s._is_legal(m, player)
                    trial = s.clone()
                    try:
                        trial._resolve_placement(m, player)
                        full = True
                    except IllegalMove:
                        full = False
                    assert fast == full, f"mismatch on {m}: fast={fast} full={full}"
        s.apply(rng.choice(s.legal_moves()))


def test_agents_play_full_games():
    for agent_cls in (RandomAgent, GreedyAgent):
        for np in (2, 3, 4):
            agents = [agent_cls(rng=random.Random(i)) for i in range(np)]
            res = play_game("bird", np, agents, seed=np, log_moves=False)
            assert res["winner"] is not None or res["shared_winners"]
            assert res["turns"] > 0


def test_mcts_returns_legal_move():
    s = State(bird_board(), 2, seed=5)
    rng = random.Random(0)
    for _ in range(6):
        s.apply(rng.choice(s.legal_moves()))
    agent = MCTSAgent(iterations=30, rng=random.Random(1))
    m = agent.choose(s)
    assert m in s.legal_moves()


def test_trajectory_logging_shapes():
    agents = [RandomAgent(rng=random.Random(i)) for i in range(2)]
    res = play_game("bird", 2, agents, seed=1, log_moves=True)
    assert res["moves"] is not None
    assert len(res["moves"]) == res["turns"]
    for rec in res["moves"]:
        assert set(rec) >= {"a", "ca", "b", "cb", "player", "events", "on_board_after"}
