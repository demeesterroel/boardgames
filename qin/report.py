"""Generate a self-contained Markdown strategy report from self-play data.

Consumes one or more JSONL trajectory files (from ``qin.selfplay``) and produces
a single Markdown document: per-file analysis (seat win-rate, winner-vs-loser
event lifts, opening preferences) plus an ASCII-bar visualisation that renders
in any Markdown viewer without image dependencies.

    python -m qin.report runs/2p.jsonl runs/3p.jsonl runs/4p.jsonl -o STRATEGY.md
"""

from __future__ import annotations

import argparse

from .analyze import analyze, load

EVENTS = ["found", "expand", "major", "connect", "conquer", "absorb"]


def bar(value: float, vmax: float, width: int = 24) -> str:
    if vmax <= 0:
        return ""
    n = int(round(width * value / vmax))
    return "█" * n + "·" * (width - n)


def lift_arrow(lift) -> str:
    if lift is None:
        return ""
    if lift >= 1.25:
        return "▲▲ strongly favoured by winners"
    if lift >= 1.08:
        return "▲ favoured by winners"
    if lift <= 0.85:
        return "▽ relatively avoided by winners"
    return "≈ neutral"


def section(a: dict) -> str:
    lines = []
    np = a["num_players"]
    lines.append(f"## {np}-player — board `{a['board']}` "
                 f"(agents: {', '.join(a['agents'])})")
    lines.append(f"\n*{a['n_games']} games.*\n")

    # seat win-rate
    lines.append("### Turn-order effect (seat win-rate)\n")
    wr = a["seat_win_rate"]
    vmax = max(wr.values()) if wr else 1
    lines.append("| Seat | Win-rate | |")
    lines.append("|------|---------:|---|")
    for s in range(np):
        v = wr[s]
        lines.append(f"| {s}{' (first)' if s==0 else ''} | {v*100:.1f}% | `{bar(v, vmax)}` |")
    lines.append(f"\nShared/tie games: {a['shared_rate']*100:.1f}%.")
    spread = (max(wr.values()) - min(wr.values())) * 100 if wr else 0
    lines.append(f"First-mover spread: **{spread:.1f} pts** "
                 f"(seat 0 {'leads' if wr[0]==max(wr.values()) else 'does not lead'}).\n")

    # event lifts
    lines.append("### What winners do more (per-turn event lift)\n")
    lines.append("Lift = winner's per-turn rate ÷ loser's. >1 means winners do it more.\n")
    lines.append("| Event | Winner/turn | Loser/turn | Lift | |")
    lines.append("|-------|------------:|-----------:|-----:|---|")
    w = a["events_per_turn_winner"]; l = a["events_per_turn_loser"]; lf = a["winner_lift"]
    for k in EVENTS:
        lift = lf.get(k)
        lift_s = "—" if lift is None else f"{lift:.2f}×"
        lines.append(f"| {k} | {w.get(k,0):.3f} | {l.get(k,0):.3f} | {lift_s} | {lift_arrow(lift)} |")

    # opening
    lines.append("\n### Opening preferences (first 3 tiles)\n")
    lines.append(f"- **Colour** — winners: `{a['opening_color_winner']}` · "
                 f"losers: `{a['opening_color_loser']}`")
    lines.append(f"- **Region** (first move) — winners' top: "
                 f"`{_top(a['opening_region_winner'], 3)}`")

    lines.append(f"\n### Endgame\n")
    lines.append(f"Avg pagodas placed at game end — "
                 f"**winner {a['avg_final_pagodas_winner']}** vs "
                 f"loser {a['avg_final_pagodas_loser']}.\n")

    # takeaway
    lifts = {k: v for k, v in lf.items() if v is not None}
    if lifts:
        top = max(lifts.items(), key=lambda kv: kv[1])
        lines.append(f"> **Takeaway:** winners lean hardest on **{top[0]}** "
                     f"({top[1]:.2f}× the losing rate); turn order is worth "
                     f"~{spread:.0f} points to the first player.\n")
    return "\n".join(lines)


def _top(d: dict, k: int) -> dict:
    return dict(list(d.items())[:k])


def build_report(paths: list[str]) -> str:
    out = ["# QIN — Self-Play Strategy Report\n"]
    out.append("_Generated from self-play trajectories by `qin.report`. "
               "Findings describe what beats the configured opponents on the "
               "given board; they are empirical tendencies, not proven optimal "
               "play._\n")
    analyses = []
    for p in paths:
        games = load(p)
        a = analyze(games)
        analyses.append(a)
        out.append("\n---\n")
        out.append(section(a))

    # cross-cut summary
    out.append("\n---\n\n## Cross-cut summary\n")
    out.append("| Players | 1st-seat win% | Worst-seat win% | Top winner lever |")
    out.append("|--------:|--------------:|----------------:|------------------|")
    for a in analyses:
        wr = a["seat_win_rate"]
        lifts = {k: v for k, v in a["winner_lift"].items() if v is not None}
        top = max(lifts.items(), key=lambda kv: kv[1]) if lifts else ("—", 0)
        out.append(f"| {a['num_players']} | {wr[0]*100:.0f}% | "
                   f"{min(wr.values())*100:.0f}% | {top[0]} ({top[1]:.2f}×) |")
    out.append("")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Markdown strategy report from self-play JSONL")
    ap.add_argument("paths", nargs="+", help="JSONL files from qin.selfplay (with --out)")
    ap.add_argument("-o", "--out", default="STRATEGY.md")
    args = ap.parse_args()
    md = build_report(args.paths)
    with open(args.out, "w") as f:
        f.write(md)
    print(f"wrote {args.out} ({len(md)} chars, {len(args.paths)} datasets)")


if __name__ == "__main__":
    main()
