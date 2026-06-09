# boardgame-strategy

Turn board-game **rulebooks into deterministic engines**, then let **self-learning
agents** play thousands of games to discover winning strategies.

First game: **QIN** (Reiner Knizia, 2012) — a tile-laying / area-majority game.

> **Note on scope & repo location.** This project currently lives as a
> self-contained folder inside the `cloud-infra` repository for convenience. It
> is *not* part of the infrastructure-as-code and is intended to be extracted
> into its own GitHub repository later, e.g.:
> ```
> git subtree split -P boardgame-strategy -b boardgame-strategy-standalone
> # then push that branch as `main` of a new empty repo (history preserved)
> ```

## Why QIN, and why this stack

We evaluated **boardgame.io** vs **no framework** vs the **Python RL ecosystem**
against the goal (heavy self-play to discover strategy):

- boardgame.io is a *web-game* framework; its only AI is plain MCTS, which is
  weakest on multiplayer + chance + large action spaces, and JS throughput hurts
  for millions of games. Good only as an optional later front-end.
- The valuable, reusable asset is a **correct, deterministic, headless engine**.
  We build that in **Python** so the self-play / analysis steps can use the
  mature ecosystem (numpy, RL libs, pandas, OpenSpiel/PettingZoo if needed).

QIN was chosen over a heavier game (e.g. *Village*) as the first target: small,
clean action space (pick 1 of 3 tiles × legal placement × rotation), short
games, mostly-observable state, mild hidden info (3-tile hands). It is simple
enough to get *correct*, yet a real design with emergent strategy.

## Status

| Step | Description | State |
|------|-------------|-------|
| 1 | Deterministic engine (board-as-data, legal moves, rules resolution) | ✅ done |
| 2 | Rule-by-rule test suite (rulebook events in isolation) | ✅ done (12 tests) |
| 3 | Terminal version to verify rules by playing & watching events | ✅ done |
| 3b | **Web game** (2-player hotseat or vs a simple non-AI bot) | ✅ done |
| 4 | Self-play agents (random / greedy / determinized MCTS) + runner | ✅ done |
| 5 | Analysis of self-play data → strategy per board setup | 🟡 first pass |
| 6 | *(optional)* boardgame.io front-end over the engine | ⬜ optional |

## ⚠️ Board layouts

- **Bird** (`qin/layouts.py` `BIRD_MAP`, and `web/qin.html` `BOARDS.bird`) — a
  **12×12** transcription of the official board, central B/Y/R provinces stacked
  in column 5 (rows 4/6/8). Transcribed from a **straight-down photo**: the grid
  pitch was measured from the printed grid lines (~66 px/cell), the three
  provinces give the anchor, and every village cell was confirmed by zooming in.
  An overlay of this map back onto the photo lands on every village, so it's a
  verified transcription rather than an estimate. (Earlier 9×9 and 16×16
  versions — the latter from an angled photo + a vision model — were both wrong
  on grid size; this supersedes them.)
- **Lion** — not yet digitized (need a photo/scan of the other side).
- **Provisional** — an 11×11 stand-in used for early testing.

The rules engine is fully board-agnostic, so finalizing/adding boards is a pure
data task (legend in `qin/board.py`).

## Web game

A self-contained browser game (no server, no build step):

```bash
cd boardgame-strategy/web
python -m http.server 8000      # then open http://localhost:8000/qin.html
# or just open web/qin.html directly in a browser
node test_engine.cjs            # verify the JS engine (26 checks)
```

- **Two modes:** 2-player hotseat, or vs a **simple non-AI bot** (a greedy
  heuristic — most pagodas placed this turn, small bonus for majors; no search,
  no learning).
- Opponent options: **simple bot (greedy)**, a stronger **MCTS bot**
  (determinized UCT, with a fast/normal/strong iteration selector), or
  2-player **hotseat**.
- Pick a tile from your hand → click a highlighted cell → choose orientation.
  Province colour = tile colour; the pagoda ring shows the owner; a glowing ring
  marks a major (double pagoda). The event log narrates every rule that fires.
- `web/engine.js` is a faithful port of the tested Python engine (same
  determinize + MCTS), so the web game and the analysis pipeline share identical
  rules. It uses the same fast in-place legality check, so MCTS is responsive.

## Layout

```
qin/
  board.py     # Board grid + ASCII-map loader (terrain, colours, components)
  tiles.py     # 72-tile deck (12 each of RR,YY,BB,RY,RB,YB)
  engine.py    # State, Move, legal_moves, apply — the rules resolver
  layouts.py   # board maps (provisional + Bird from photo)
  cli.py       # terminal verifier (human / hotseat / random bots / auto)
web/
  engine.js        # JS port of the rules engine (browser + Node)
  qin.html         # self-contained web game (no backend)
  test_engine.cjs  # headless sanity tests mirroring the Python tests
qin/
  agents.py     # random / greedy / determinized-MCTS self-play agents
  selfplay.py   # batch runner: plays N games, logs trajectories (JSONL)
  analyze.py    # strategy analysis over the trajectory logs
  tournament.py # round-robin / N-player tournament (validates agent strength)
  report.py     # Markdown strategy-report generator (-> STRATEGY.md)
STRATEGY.md       # generated strategy report (2/3/4p greedy self-play)
AGENTS_FINDINGS.md # agent strength results + why greedy beats MCTS here
tests/
  test_rules.py
  test_selfplay.py
```

## Self-play & strategy analysis (steps 4–5)

```bash
# play games and record trajectories (JSONL, one game per line)
python -m qin.selfplay --games 500 --players 2 --agents greedy --out runs/2p.jsonl
python -m qin.selfplay --games 200 --players 3 --agents mcts,greedy,random --out runs/3p.jsonl

# mine the trajectories for what winning play looks like
python -m qin.analyze runs/2p.jsonl

# generate a shareable Markdown strategy report from one or more datasets
python -m qin.report runs/2p.jsonl runs/3p.jsonl runs/4p.jsonl -o STRATEGY.md

# round-robin to validate agent strength ordering (use --progress for long runs)
python -m qin.tournament --games 40 --players 2 --agents random,greedy,mcts --progress
```

**Agents** (`--agents`, cycled across seats): `random` (baseline), `greedy`
(one-ply: maximise pagodas placed this turn), `mcts` (determinized UCT —
re-samples the hidden opponent hands + deck each iteration, so it handles QIN's
imperfect information; greedy rollouts + greedy action-pruning).

**Measured strength: `random ≪ MCTS < greedy`.** MCTS beats random 12–0 (so the
search works) but loses to greedy, because QIN is a pagoda-placement race and
greedy maximises exactly that — it is near-optimal, and search at interactive
budgets can't beat it. See **`AGENTS_FINDINGS.md`**. Consequence: the web greedy
bot is the *strongest* opponent; the MCTS bot is labelled experimental.

**Hidden information.** `State.determinize(observer, rng)` resamples the
unseen tiles (opponents' hands + deck order) while preserving what the observer
can see; MCTS calls it once per iteration (single-observer ISMCTS).

**Analysis** (`qin.analyze`) is intentionally interpretable — frequencies and
*lifts*, not a black box — so the output reads as strategy advice: seat
(turn-order) win-rate, how much more often winners trigger each event
(found/expand/major/connect/conquer/absorb) per turn, and opening colour/region
preferences of winners vs losers. A learned model can be layered on later.

## Rules model (how the engine resolves a placement)

The six rulebook events are unified into two passes:

1. **Province pass** (per resulting same-colour connected component):
   0 prior owned provinces → **found**; 1 → **expand** (→ **major** at ≥5
   spaces, double pagoda); ≥2 → **absorb** (forms a major; owner is the largest
   space contributor; combining two majors or an exact tie is illegal).
2. **Village pass** (every village): owner = unique player with the most
   adjoining pagodas (double counts as 2), only if it strictly beats the current
   owner. Ties never seize. This covers both **connect** and **conquer**.

Game ends when a player places their last pagoda (they win), or when no legal
move remains (most pagodas on board wins; ties shared).

## Running

```bash
cd boardgame-strategy
python -m pytest -q                 # run the rule tests
python -m qin.cli                   # play P0 vs a random bot
python -m qin.cli --hotseat         # all human (hotseat)
python -m qin.cli --auto --seed 7   # watch a full random game, no input
```
```
Legend:  ' .'=grass   'o'=village   'R0/Y1/B2'=province space (colour+owner)
lowercase colour (e.g. 'r0') = a major province / double pagoda
```
