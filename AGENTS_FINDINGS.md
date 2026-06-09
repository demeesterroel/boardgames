# QIN — Agent strength findings

Empirical results from self-play on the Bird board (2 players). These validate
the agents and, importantly, characterise *why* the strength ordering comes out
the way it does.

## Headline

| Matchup | Result | Source |
|---|---|---|
| greedy vs random | **greedy 200–0** | round-robin, 100 games/ordering |
| MCTS vs random (both seats) | **MCTS 12–0** | seat-alternated diagnostic |
| MCTS vs greedy | **greedy 24–0** | round-robin, 12 games/ordering, 100 iters |
| MCTS picks greedy's move | **0 / 5 trials** (mid-game) | first-move agreement probe |

So the strength ordering is **random ≪ MCTS < greedy**, with greedy clearly on
top.

## Interpretation — MCTS is not broken; greedy is near-optimal for QIN

A losing MCTS is suspicious, so we checked it directly:

1. **MCTS crushes random 12–0** (seats alternated to cancel first-player
   advantage). A broken search would not beat random — so the MCTS machinery
   (determinize → select → greedy rollout → backprop) is sound. Rollouts were
   separately verified to reach a terminal state 50/50, so the reward is a true
   win/loss signal, not a mid-game heuristic.

2. **MCTS rarely plays greedy's move** (0/5 mid-game positions) and **loses to
   greedy**. So MCTS is diverging from greedy and the divergent moves are worse.

Why greedy is so strong here: QIN's win condition *is* "place all your pagodas
first". The greedy agent maximises pagodas-placed-this-turn (founds + village
seizes, with a major-province bonus), which races directly toward that win
condition. It is close to optimal for a pagoda-placement race.

Why MCTS underperforms it at feasible budgets:
- The branching factor is huge (200+ legal placements). Even with greedy action
  pruning to a 14-move shortlist per node, ~100–200 iterations spread over 14
  root moves give each only a handful of visits, so the most-visited-child
  choice is dominated by exploration noise rather than a settled value estimate.
- Against a near-optimal deterministic heuristic, "noisy" loses. MCTS would need
  far more iterations (and likely a value-aware tree policy, not just greedy
  rollouts) to match greedy — well beyond an interactive budget.

## Consequences for the web game

- **The "simple" greedy bot is the genuinely strong opponent.** It should be the
  recommended challenging bot.
- **The MCTS bot is experimental, not "strong".** At interactive iteration
  counts it is weaker than greedy and slow. It is kept for experimentation and
  to demonstrate the determinized-ISMCTS machinery, and is labelled honestly in
  the UI rather than marketed as the tough opponent.

## Methodological notes (so this is reproducible)

- Strength ordering validated with `python -m qin.tournament` (use `--progress`
  to watch long runs; MCTS games are slow — keep game counts small).
- The MCTS-vs-random check alternates seats to remove the first-player edge,
  which is large in QIN (see `STRATEGY.md`: ~5 pts at 2p, ~21 pts at 4p).
- Lesson learned during this work: run CPU-bound agent jobs **one at a time**
  (parallel MCTS runs throttle each other) and **with progress output**.
