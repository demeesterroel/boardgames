"""Self-play agents for QIN.

Three agents, increasing in strength:

- ``RandomAgent``    — uniform over legal moves (baseline).
- ``GreedyAgent``    — one-ply heuristic: maximise pagodas placed this turn,
                       small bonus for majors. Mirrors the web bot.
- ``MCTSAgent``      — determinized Monte-Carlo Tree Search. QIN has hidden
                       information (opponents' hands, deck order), so each MCTS
                       iteration first *determinizes* the state from the acting
                       player's view (resampling the hidden tiles), then runs a
                       UCT iteration on that fully-observable sample. This is
                       "Determinized UCT" / single-observer ISMCTS, a standard
                       and effective approach for stochastic hidden-info games.

All agents expose ``choose(state) -> Move``.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .engine import Move, State


class Agent:
    name = "agent"

    def choose(self, state: State) -> Move:
        raise NotImplementedError


class RandomAgent(Agent):
    name = "random"

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def choose(self, state: State) -> Move:
        return self.rng.choice(state.legal_moves())


class GreedyAgent(Agent):
    """One-ply: pick the move that puts the most pagodas on the board this turn
    (founds + village seizes), tie-broken by majors then randomly."""

    name = "greedy"

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def _score(self, state: State, move: Move, me: int) -> tuple[int, int]:
        trial = state.clone()
        before = trial.on_board()[me]
        trial._resolve_placement(move, me)
        gained = trial.on_board()[me] - before
        majors = sum(1 for p in trial.provinces if p.owner == me and p.major)
        return (gained, majors)

    def choose(self, state: State) -> Move:
        me = state.current_player
        moves = state.legal_moves()
        best, best_key = [], (-1, -1)
        for m in moves:
            key = self._score(state, m, me)
            if key > best_key:
                best_key, best = key, [m]
            elif key == best_key:
                best.append(m)
        return self.rng.choice(best)


# --------------------------------------------------------------------- MCTS
@dataclass
class _Node:
    """A node in the search tree, keyed by the move that reached it.

    Because we re-determinize every iteration, children are stored per *move*
    (moves are comparable/hashable via their fields) and statistics are pooled
    across determinizations — the standard SO-ISMCTS / determinized-UCT setup.
    """

    to_play: int
    visits: int = 0
    reward: float = 0.0  # summed reward from the perspective of `to_play`
    children: dict = field(default_factory=dict)  # Move -> _Node
    untried: list = field(default_factory=list)
    expanded: bool = False


class MCTSAgent(Agent):
    name = "mcts"

    def __init__(
        self,
        iterations: int = 400,
        c: float = 1.4,
        rng: random.Random | None = None,
        rollout_depth: int = 60,
        heuristic_rollout: bool = True,
    ) -> None:
        self.iterations = iterations
        self.c = c
        self.rng = rng or random.Random()
        self.rollout_depth = rollout_depth
        # heuristic (greedy) rollouts make playouts far more informative than
        # uniform-random ones, which sharply strengthens MCTS for a given budget.
        self.heuristic_rollout = heuristic_rollout

    def choose(self, state: State) -> Move:
        root_player = state.current_player
        root = _Node(to_play=root_player)

        for _ in range(self.iterations):
            det = state.determinize(root_player, self.rng)
            self._iterate(root, det)

        # most-visited child (robust choice)
        if not root.children:
            return self.rng.choice(state.legal_moves())
        best_move = max(root.children.items(), key=lambda kv: kv[1].visits)[0]
        return best_move

    # QIN can offer 200+ legal moves — far too wide for MCTS to search in a
    # modest budget. Restrict each node to a greedy-ranked shortlist.
    CAND_CAP = 14

    def _candidates(self, state: State) -> list[Move]:
        legal = state.legal_moves()
        if len(legal) <= self.CAND_CAP:
            return legal
        me = state.current_player
        legal.sort(key=lambda m: state.score_move(m, me), reverse=True)
        return legal[: self.CAND_CAP]

    def _iterate(self, root: _Node, state: State) -> None:
        path: list[tuple[_Node, Move]] = []
        node = root
        # --- selection + expansion, following this determinization's legal moves
        while True:
            if state.is_terminal():
                break
            legal = self._candidates(state)
            if not legal:
                break
            # initialise untried moves available in THIS determinization
            tried = set(node.children.keys())
            untried = [m for m in legal if m not in tried]
            if untried:
                move = self.rng.choice(untried)
                state.apply(move)
                child = _Node(to_play=state.current_player)
                node.children[move] = child
                path.append((node, move))
                node = child
                break  # expanded one node; now roll out
            # all legal moves have nodes -> UCT select among legal only
            move = self._uct_select(node, legal)
            state.apply(move)
            path.append((node, move))
            node = node.children[move]

        # --- rollout ---
        reward = self._rollout(state)

        # --- backprop: reward is a per-player vector ---
        root.visits += 1
        for parent, move in path:
            child = parent.children[move]
            child.visits += 1
            # store reward from the perspective of the player who was to move at
            # the parent (i.e. who chose `move`)
            child.reward += reward[parent.to_play]

    def _uct_select(self, node: _Node, legal: list[Move]) -> Move:
        # total visits over the legal children only
        total = sum(node.children[m].visits for m in legal) + 1
        log_total = math.log(total)
        best, best_val = None, -1e18
        for m in legal:
            ch = node.children[m]
            if ch.visits == 0:
                return m
            exploit = ch.reward / ch.visits
            explore = self.c * math.sqrt(log_total / ch.visits)
            val = exploit + explore
            if val > best_val:
                best_val, best = val, m
        return best

    ROLL_SAMPLE = 5

    def _rollout(self, state: State) -> list[float]:
        depth = 0
        while not state.is_terminal() and depth < self.rollout_depth:
            move = self._rollout_move(state)
            if move is None:
                break
            state.apply(move)
            depth += 1
        return self._reward_vector(state)

    def _rollout_move(self, state: State) -> Move | None:
        """Cheap playout policy. Sample a few legal moves via the no-enumeration
        sampler and (if heuristic rollouts are on) take the best by the in-place
        greedy score — no cloning, no full legal-move enumeration."""
        if not self.heuristic_rollout:
            return state.random_legal_move(self.rng)
        me = state.current_player
        best, best_score = None, -1
        for _ in range(self.ROLL_SAMPLE):
            m = state.random_legal_move(self.rng)
            if m is None:
                break
            sc = state.score_move(m, me)
            if sc > best_score:
                best_score, best = sc, m
        return best

    def _reward_vector(self, state: State) -> list[float]:
        """1.0 for the winner, shared equally on ties, 0 otherwise. If the
        rollout hit the depth cap without terminating, fall back to pagodas
        placed (most placed = leader) as a heuristic reward."""
        n = state.num_players
        if state.winner is not None:
            v = [0.0] * n
            v[state.winner] = 1.0
            return v
        if state.shared_winners:
            v = [0.0] * n
            for w in state.shared_winners:
                v[w] = 1.0 / len(state.shared_winners)
            return v
        # non-terminal cutoff: reward proportional to lead in pagodas placed
        onb = state.on_board()
        best = max(onb)
        leaders = [i for i, x in enumerate(onb) if x == best]
        v = [0.0] * n
        for i in leaders:
            v[i] = 1.0 / len(leaders)
        return v


AGENTS = {
    "random": RandomAgent,
    "greedy": GreedyAgent,
    "mcts": MCTSAgent,
}
