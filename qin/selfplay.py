"""Self-play runner for QIN (step 4).

Plays many games between configurable agents on a chosen board and player count,
records each game's full trajectory plus outcome to a JSONL file, and prints
win-rate / tie statistics. The JSONL is the input to the strategy-analysis step.

Examples:
    # 500 games, 2 players, greedy vs greedy on the Bird board
    python -m qin.selfplay --games 500 --players 2 --agents greedy

    # MCTS vs greedy vs random, 3 players, log trajectories
    python -m qin.selfplay --games 100 --players 3 \
        --agents mcts,greedy,random --out runs/3p.jsonl

Each JSONL line is one game:
    {
      "board": "bird", "num_players": 3, "seed": 12,
      "agents": ["mcts","greedy","random"],
      "winner": 0, "shared_winners": null,
      "on_board": [15, 11, 9],
      "turns": 47,
      "moves": [{"player":0,"a":[r,c],"ca":"R","b":[r,c],"cb":"Y",
                 "events":[...], "on_board_after":[...]}, ...]
    }
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from collections import Counter

from .agents import AGENTS, Agent
from .engine import Move, State
from .layouts import bird_board, provisional_board

BOARDS = {"bird": bird_board, "provisional": provisional_board}


def make_agents(specs: list[str], num_players: int, rng: random.Random) -> list[Agent]:
    """Expand the --agents list to one agent per seat (cycling if shorter)."""
    out: list[Agent] = []
    for i in range(num_players):
        name = specs[i % len(specs)]
        cls = AGENTS[name]
        # give each agent its own derived rng for reproducibility
        out.append(cls(rng=random.Random(rng.random())))
    return out


def move_record(move: Move) -> dict:
    return {
        "a": list(move.cell_a),
        "ca": move.color_a.value,
        "b": list(move.cell_b),
        "cb": move.color_b.value,
    }


def play_game(
    board_name: str,
    num_players: int,
    agents: list[Agent],
    seed: int,
    log_moves: bool = True,
    max_turns: int = 5000,
) -> dict:
    state = State(BOARDS[board_name]().clone(), num_players=num_players, seed=seed)
    moves_log: list[dict] = []
    turns = 0
    while not state.is_terminal() and turns < max_turns:
        legal = state.legal_moves()
        if not legal:
            break
        agent = agents[state.current_player]
        player = state.current_player
        move = agent.choose(state)
        events = state.apply(move)
        turns += 1
        if log_moves:
            rec = move_record(move)
            rec["player"] = player
            rec["events"] = events
            rec["on_board_after"] = state.on_board()
            moves_log.append(rec)

    res = state.result()
    return {
        "board": board_name,
        "num_players": num_players,
        "seed": seed,
        "agents": [a.name for a in agents],
        "winner": res["winner"],
        "shared_winners": res["shared_winners"],
        "on_board": res["on_board"],
        "turns": turns,
        "moves": moves_log if log_moves else None,
    }


def run(args: argparse.Namespace) -> None:
    rng = random.Random(args.seed)
    specs = [s.strip() for s in args.agents.split(",") if s.strip()]
    for s in specs:
        if s not in AGENTS:
            raise SystemExit(f"unknown agent '{s}'; choose from {list(AGENTS)}")

    out_f = None
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        out_f = open(args.out, "w")

    win_counter: Counter = Counter()
    shared = 0
    turn_total = 0
    t0 = time.time()

    for g in range(args.games):
        game_seed = rng.randint(0, 2**31 - 1)
        agents = make_agents(specs, args.players, random.Random(game_seed))
        result = play_game(
            args.board, args.players, agents, game_seed,
            log_moves=not args.no_log,
        )
        turn_total += result["turns"]
        if result["winner"] is not None:
            win_counter[result["winner"]] += 1
        elif result["shared_winners"]:
            shared += 1
        if out_f:
            out_f.write(json.dumps(result) + "\n")
        if args.progress and (g + 1) % args.progress == 0:
            print(f"  ... {g + 1}/{args.games} games", flush=True)

    if out_f:
        out_f.close()
    dt = time.time() - t0

    print(f"\n{args.games} games | {args.players}p | board={args.board} "
          f"| agents={specs}")
    print(f"seats: {[specs[i % len(specs)] for i in range(args.players)]}")
    for p in range(args.players):
        wins = win_counter[p]
        print(f"  seat {p} ({specs[p % len(specs)]}): "
              f"{wins} wins ({100 * wins / args.games:.1f}%)")
    print(f"  shared/tie games: {shared} ({100 * shared / args.games:.1f}%)")
    print(f"  avg turns/game: {turn_total / args.games:.1f}")
    print(f"  elapsed: {dt:.1f}s ({args.games / dt:.1f} games/s)")
    if args.out:
        print(f"  trajectories written to {args.out}")


def main() -> None:
    ap = argparse.ArgumentParser(description="QIN self-play runner")
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--players", type=int, default=2, choices=[2, 3, 4])
    ap.add_argument("--board", default="bird", choices=list(BOARDS))
    ap.add_argument("--agents", default="greedy",
                    help="comma-separated agents per seat (cycles): "
                         f"{list(AGENTS)}")
    ap.add_argument("--out", default=None, help="JSONL trajectory output path")
    ap.add_argument("--no-log", action="store_true",
                    help="don't record per-move trajectories (faster)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--progress", type=int, default=0,
                    help="print progress every N games (0=off)")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
