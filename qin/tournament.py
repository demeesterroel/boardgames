"""Round-robin tournament between QIN agents (validates strength ordering).

Plays every ordered pairing (so first-player advantage is averaged out) across a
chosen player count and board, reporting head-to-head win-rates.

    python -m qin.tournament --games 60 --players 2 --agents random,greedy,mcts
    python -m qin.tournament --games 40 --players 2 --agents greedy,mcts --mcts-iters 200
"""

from __future__ import annotations

import argparse
import itertools
import random
import time
from collections import defaultdict

from .agents import GreedyAgent, MCTSAgent, RandomAgent
from .layouts import bird_board, provisional_board
from .selfplay import play_game

BOARDS = {"bird": bird_board, "provisional": provisional_board}


def build(name: str, seed: int, mcts_iters: int):
    rng = random.Random(seed)
    if name == "random":
        return RandomAgent(rng=rng)
    if name == "greedy":
        return GreedyAgent(rng=rng)
    if name == "mcts":
        return MCTSAgent(iterations=mcts_iters, rng=rng)
    raise SystemExit(f"unknown agent {name}")


def run(args: argparse.Namespace) -> None:
    names = [s.strip() for s in args.agents.split(",") if s.strip()]
    rng = random.Random(args.seed)
    board_fn = BOARDS[args.board]

    # head-to-head wins[(a,b)] = games where a beat b (only meaningful for 2p)
    wins = defaultdict(int)
    played = defaultdict(int)
    t0 = time.time()

    if args.players == 2:
        orderings = list(itertools.permutations(names, 2))
        total_games = len(orderings) * args.games
        done = 0
        for a, b in orderings:
            for g in range(args.games):
                seed = rng.randint(0, 2**31 - 1)
                agents = [build(a, seed, args.mcts_iters),
                          build(b, seed + 1, args.mcts_iters)]
                res = play_game(args.board, 2, agents, seed, log_moves=False)
                played[(a, b)] += 1
                if res["winner"] == 0:
                    wins[(a, b)] += 1
                elif res["winner"] == 1:
                    wins[(b, a)] += 1
                done += 1
                if args.progress:
                    rate = done / (time.time() - t0)
                    eta = (total_games - done) / rate if rate else 0
                    print(f"PROGRESS {done}/{total_games} | last {a} vs {b} "
                          f"-> winner {res['winner']} | {rate:.2f} games/s "
                          f"| eta {eta:.0f}s", flush=True)
        # symmetric table: combine both seat orders
        print(f"\n2-player round-robin | board={args.board} "
              f"| {args.games} games/ordering | mcts_iters={args.mcts_iters}")
        print(f"\nRow agent win-rate vs column agent (both seat orders pooled):")
        col_w = 9
        header = " " * 10 + "".join(f"{n:>{col_w}}" for n in names)
        print(header)
        overall = defaultdict(lambda: [0, 0])  # name -> [wins, games]
        for a in names:
            row = f"{a:>10}"
            for b in names:
                if a == b:
                    row += f"{'-':>{col_w}}"
                    continue
                w = wins[(a, b)]; tot = played[(a, b)] + played[(b, a)]
                wt = w + wins[(a, b)]  # placeholder
                total_w = wins[(a, b)]
                total_games = played[(a, b)] + played[(b, a)]
                # a's wins over b across both orderings:
                aw = wins[(a, b)]
                pct = 100 * aw / total_games if total_games else 0
                row += f"{pct:>{col_w-1}.0f}%"
                overall[a][0] += aw
                overall[a][1] += total_games
            print(row)
        print(f"\nOverall win-rate (vs all opponents):")
        for n in sorted(names, key=lambda x: -overall[x][0] / max(overall[x][1], 1)):
            w, tot = overall[n]
            print(f"  {n:>8}: {100 * w / max(tot,1):5.1f}%  ({w}/{tot})")
    else:
        # N-player: seat every agent once per game in rotated orders
        from collections import Counter
        win = Counter()
        total = 0
        # use all names cycled to fill seats; rotate start to balance turn order
        for g in range(args.games):
            seed = rng.randint(0, 2**31 - 1)
            order = [names[(g + i) % len(names)] for i in range(args.players)]
            agents = [build(order[i], seed + i, args.mcts_iters)
                      for i in range(args.players)]
            res = play_game(args.board, args.players, agents, seed, log_moves=False)
            total += 1
            if res["winner"] is not None:
                win[order[res["winner"]]] += 1
            if args.progress:
                rate = total / (time.time() - t0)
                eta = (args.games - total) / rate if rate else 0
                print(f"PROGRESS {total}/{args.games} | {rate:.2f} games/s "
                      f"| eta {eta:.0f}s", flush=True)
        print(f"\n{args.players}-player tournament | board={args.board} "
              f"| {args.games} games | seats rotated")
        for n in sorted(set(names), key=lambda x: -win[x]):
            print(f"  {n:>8}: {win[n]} wins ({100*win[n]/total:.1f}% of games)")

    print(f"\nelapsed: {time.time()-t0:.1f}s")


def main() -> None:
    ap = argparse.ArgumentParser(description="QIN agent tournament")
    ap.add_argument("--games", type=int, default=50)
    ap.add_argument("--players", type=int, default=2, choices=[2, 3, 4])
    ap.add_argument("--board", default="bird", choices=list(BOARDS))
    ap.add_argument("--agents", default="random,greedy,mcts")
    ap.add_argument("--mcts-iters", type=int, default=150)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--progress", action="store_true",
                    help="print a PROGRESS line after each game (for monitoring)")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
