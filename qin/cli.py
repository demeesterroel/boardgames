"""Terminal version of QIN, for verifying the rules by hand.

Renders the board, shows the active player's hand and every legal move, applies
the chosen move, and prints each event it triggers (found / expand / major /
connect / conquer / absorb). Players can be human (hotseat) or random bots.

    python -m qin.cli                 # 2p: you (P0) vs a random bot (P1)
    python -m qin.cli --hotseat       # all human
    python -m qin.cli --players 3 --bots 1,2
    python -m qin.cli --auto --seed 7 # watch a full random game (no input)
"""

from __future__ import annotations

import argparse
import random

from .board import Board, Color, Terrain
from .engine import Move, State
from .layouts import provisional_board
from .tiles import tile_str

_OWNER_GLYPH = "·"  # unowned province/village marker


def render(state: State) -> str:
    board = state.board
    cell_owner: dict = {}
    for p in state.provinces:
        for cell in p.cells:
            cell_owner[cell] = p
    header = "    " + "".join(f"{c:>2}" for c in range(board.cols))
    lines = [header]
    for r in range(board.rows):
        row = [f"{r:>2}  "]
        for c in range(board.cols):
            cell = (r, c)
            t = board.terrain_at(cell)
            if t is Terrain.WATER:
                row.append("  ")
            elif t is Terrain.GRASS:
                row.append(" .")
            elif t is Terrain.VILLAGE:
                owner = state.village_owner.get(cell)
                row.append("o" + (str(owner) if owner is not None else _OWNER_GLYPH))
            else:  # PROVINCE
                col = board.color_at(cell).value
                prov = cell_owner.get(cell)
                if prov is None:
                    row.append(col + _OWNER_GLYPH)
                else:
                    mark = str(prov.owner)
                    # uppercase color = single pagoda, with '*' shown on majors
                    row.append((col if not prov.major else col.lower()) + mark)
        lines.append("".join(row))
    return "\n".join(lines)


def status(state: State) -> str:
    onb = state.on_board()
    parts = []
    for pl in range(state.num_players):
        parts.append(f"P{pl}: {state.supply(pl)} pagodas left")
    return " | ".join(parts)


def describe(move: Move) -> str:
    return (
        f"{tile_str(move.tile)}  "
        f"{move.color_a.value}@{move.cell_a} + {move.color_b.value}@{move.cell_b}"
    )


def choose_human(state: State, moves: list[Move]) -> Move:
    print("\nLegal moves:")
    for i, m in enumerate(moves):
        print(f"  {i:>3}: {describe(m)}")
    while True:
        raw = input(f"P{state.current_player} choose move # (or 'q'): ").strip()
        if raw.lower() in ("q", "quit"):
            raise SystemExit(0)
        if raw.isdigit() and 0 <= int(raw) < len(moves):
            return moves[int(raw)]
        print("  invalid choice")


def play(
    state: State,
    bots: set[int],
    rng: random.Random,
    auto: bool = False,
    max_turns: int = 10_000,
) -> None:
    turn = 0
    while not state.is_terminal() and turn < max_turns:
        turn += 1
        print("\n" + "=" * 60)
        print(render(state))
        print(status(state))
        hand = state.hands[state.current_player]
        print(
            f"\nTurn {turn} — P{state.current_player}"
            f"  hand: {' '.join(tile_str(t) for t in hand)}"
        )
        moves = state.legal_moves()
        if not moves:
            print("  no legal moves — passing")
            state._advance_turn()
            continue
        if auto or state.current_player in bots:
            move = rng.choice(moves)
            print(f"  -> {describe(move)}")
        else:
            move = choose_human(state, moves)
        events = state.apply(move)
        for e in events:
            print(f"    * {e}")

    print("\n" + "=" * 60)
    print(render(state))
    res = state.result()
    if res["winner"] is not None:
        print(f"\nGAME OVER — P{res['winner']} wins!  pagodas on board: {res['on_board']}")
    elif res["shared_winners"] is not None:
        print(f"\nGAME OVER — shared win: {res['shared_winners']}  {res['on_board']}")
    else:
        print("\nStopped (turn limit).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Terminal QIN")
    ap.add_argument("--players", type=int, default=2, choices=[2, 3, 4])
    ap.add_argument("--bots", type=str, default=None,
                    help="comma-separated bot player indices (default: all but P0)")
    ap.add_argument("--hotseat", action="store_true", help="all players human")
    ap.add_argument("--auto", action="store_true", help="all random, no input")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    state = State(provisional_board(), num_players=args.players, seed=args.seed)

    if args.hotseat:
        bots: set[int] = set()
    elif args.bots is not None:
        bots = {int(x) for x in args.bots.split(",") if x.strip() != ""}
    else:
        bots = set(range(1, args.players))  # P0 human, rest bots

    print("QIN — terminal verifier")
    print("Legend: ' .'=grass  'o'=village  'R0/Y1/B2'=province space "
          "(color+owner; lowercase color = major/double pagoda)")
    play(state, bots=bots, rng=rng, auto=args.auto)


if __name__ == "__main__":
    main()
