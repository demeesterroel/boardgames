"""Strategy analysis over self-play trajectories (step 5, first pass).

Reads a JSONL file produced by ``qin.selfplay`` and extracts signal about what
winning play looks like *for a given board + player count*:

- win-rate by seat (turn-order effect)
- how often winners trigger each event type (found/expand/major/connect/
  conquer/absorb) vs losers, normalised per turn
- opening preference: which colour / board region winners play their first
  tiles into, vs losers
- correlation between final pagodas-on-board and winning

This is deliberately interpretable (frequencies and lifts), not a black box, so
the output reads as human strategy advice. A learned model can come later.

    python -m qin.analyze runs/2p.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict

EVENT_KEYS = {
    "founds a": "found",
    "expands": "expand",
    "MAJOR": "major",
    "connects village": "connect",
    "conquers": "conquer",
    "absorbs": "absorb",
}


def classify_events(events: list[str]) -> Counter:
    c: Counter = Counter()
    for e in events:
        for needle, key in EVENT_KEYS.items():
            if needle in e:
                c[key] += 1
    return c


def load(path: str) -> list[dict]:
    games = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                games.append(json.loads(line))
    return games


def region(cell: list[int], rows: int, cols: int) -> str:
    """Coarse 3x3 region label for a cell, for opening-location analysis."""
    r, c = cell
    rb = "top" if r < rows / 3 else ("mid" if r < 2 * rows / 3 else "bot")
    cb = "left" if c < cols / 3 else ("center" if c < 2 * cols / 3 else "right")
    return f"{rb}-{cb}"


def is_winner(game: dict, seat: int) -> bool:
    if game["winner"] is not None:
        return game["winner"] == seat
    if game["shared_winners"]:
        return seat in game["shared_winners"]
    return False


def analyze(games: list[dict], board_dims: tuple[int, int] = (12, 12)) -> dict:
    rows, cols = board_dims
    n_games = len(games)
    if n_games == 0:
        raise SystemExit("no games in file")
    nplayers = games[0]["num_players"]

    seat_wins = Counter()
    shared = 0

    # per-outcome accumulators
    ev_winner = Counter(); ev_loser = Counter()
    turns_winner = 0; turns_loser = 0
    open_color = {"winner": Counter(), "loser": Counter()}
    open_region = {"winner": Counter(), "loser": Counter()}
    final_pagoda_winner = []; final_pagoda_loser = []

    for g in games:
        if g["winner"] is not None:
            seat_wins[g["winner"]] += 1
        elif g["shared_winners"]:
            shared += 1

        # split this game's moves by the acting player's outcome
        per_seat_moves = defaultdict(list)
        if g.get("moves"):
            for mv in g["moves"]:
                per_seat_moves[mv["player"]].append(mv)

        onb = g["on_board"]
        for seat in range(g["num_players"]):
            won = is_winner(g, seat)
            tag = "winner" if won else "loser"
            (final_pagoda_winner if won else final_pagoda_loser).append(onb[seat])

            moves = per_seat_moves.get(seat, [])
            if not moves:
                continue
            ev = Counter()
            for mv in moves:
                ev += classify_events(mv["events"])
            if won:
                ev_winner += ev; turns_winner += len(moves)
            else:
                ev_loser += ev; turns_loser += len(moves)

            # opening = first 3 moves
            for mv in moves[:3]:
                for col in (mv["ca"], mv["cb"]):
                    open_color[tag][col] += 1
                open_region[tag][region(mv["a"], rows, cols)] += 1

    def per_turn(counter: Counter, turns: int) -> dict:
        return {k: round(counter[k] / turns, 4) for k in
                ["found", "expand", "major", "connect", "conquer", "absorb"]} \
            if turns else {}

    wt = per_turn(ev_winner, turns_winner)
    lt = per_turn(ev_loser, turns_loser)
    lift = {k: (round(wt[k] / lt[k], 2) if lt.get(k) else None) for k in wt}

    def norm(counter: Counter) -> dict:
        tot = sum(counter.values()) or 1
        return {k: round(v / tot, 3) for k, v in counter.most_common()}

    return {
        "n_games": n_games,
        "num_players": nplayers,
        "agents": games[0]["agents"],
        "board": games[0]["board"],
        "seat_win_rate": {s: round(seat_wins[s] / n_games, 3) for s in range(nplayers)},
        "shared_rate": round(shared / n_games, 3),
        "events_per_turn_winner": wt,
        "events_per_turn_loser": lt,
        "winner_lift": lift,
        "opening_color_winner": norm(open_color["winner"]),
        "opening_color_loser": norm(open_color["loser"]),
        "opening_region_winner": norm(open_region["winner"]),
        "opening_region_loser": norm(open_region["loser"]),
        "avg_final_pagodas_winner":
            round(sum(final_pagoda_winner) / len(final_pagoda_winner), 2)
            if final_pagoda_winner else None,
        "avg_final_pagodas_loser":
            round(sum(final_pagoda_loser) / len(final_pagoda_loser), 2)
            if final_pagoda_loser else None,
    }


def print_report(a: dict) -> None:
    print(f"\n=== QIN strategy analysis ===")
    print(f"file: {a['n_games']} games | {a['num_players']}p "
          f"| board={a['board']} | agents={a['agents']}")
    print(f"\nSeat win-rate (turn-order effect):")
    for s, wr in a["seat_win_rate"].items():
        print(f"  seat {s}: {wr*100:5.1f}%")
    print(f"  shared/tie: {a['shared_rate']*100:.1f}%")

    print(f"\nEvents per turn — winners vs losers (lift = winner/loser):")
    print(f"  {'event':8} {'winner':>8} {'loser':>8} {'lift':>6}")
    for k in ["found", "expand", "major", "connect", "conquer", "absorb"]:
        w = a["events_per_turn_winner"].get(k, 0)
        l = a["events_per_turn_loser"].get(k, 0)
        lift = a["winner_lift"].get(k)
        print(f"  {k:8} {w:8.3f} {l:8.3f} {('  -' if lift is None else f'{lift:6.2f}')}")

    print(f"\nOpening colour preference (first 3 tiles):")
    print(f"  winners: {a['opening_color_winner']}")
    print(f"  losers:  {a['opening_color_loser']}")
    print(f"\nOpening board region (first move):")
    print(f"  winners: {a['opening_region_winner']}")
    print(f"  losers:  {a['opening_region_loser']}")
    print(f"\nAvg final pagodas on board: "
          f"winner={a['avg_final_pagodas_winner']} "
          f"loser={a['avg_final_pagodas_loser']}")

    # headline takeaways
    print(f"\nTakeaways:")
    lifts = {k: v for k, v in a["winner_lift"].items() if v is not None}
    if lifts:
        top = max(lifts.items(), key=lambda kv: kv[1])
        bot = min(lifts.items(), key=lambda kv: kv[1])
        print(f"  - winners do '{top[0]}' {top[1]}x more per turn than losers")
        if bot[1] < 1:
            print(f"  - winners do '{bot[0]}' relatively less ({bot[1]}x)")
    seats = a["seat_win_rate"]
    lead = max(seats, key=seats.get)
    print(f"  - turn order matters: seat {lead} leads "
          f"({seats[lead]*100:.0f}% vs {min(seats.values())*100:.0f}% worst)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Analyze QIN self-play trajectories")
    ap.add_argument("path", help="JSONL file from qin.selfplay (needs --out, with moves)")
    ap.add_argument("--json", action="store_true", help="emit raw JSON instead of a report")
    args = ap.parse_args()
    games = load(args.path)
    result = analyze(games)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_report(result)


if __name__ == "__main__":
    main()
