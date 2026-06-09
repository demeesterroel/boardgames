# QIN — Self-Play Strategy Report

_Generated from self-play trajectories by `qin.report`. Findings describe what beats the configured opponents on the given board; they are empirical tendencies, not proven optimal play._


---

## 2-player — board `bird` (agents: greedy, greedy)

*200 games.*

### Turn-order effect (seat win-rate)

| Seat | Win-rate | |
|------|---------:|---|
| 0 (first) | 52.5% | `████████████████████████` |
| 1 | 47.5% | `██████████████████████··` |

Shared/tie games: 0.0%.
First-mover spread: **5.0 pts** (seat 0 leads).

### What winners do more (per-turn event lift)

Lift = winner's per-turn rate ÷ loser's. >1 means winners do it more.

| Event | Winner/turn | Loser/turn | Lift | |
|-------|------------:|-----------:|-----:|---|
| found | 0.819 | 0.780 | 1.05× | ≈ neutral |
| expand | 0.204 | 0.221 | 0.92× | ≈ neutral |
| major | 0.090 | 0.080 | 1.13× | ▲ favoured by winners |
| connect | 0.350 | 0.264 | 1.32× | ▲▲ strongly favoured by winners |
| conquer | 0.072 | 0.053 | 1.35× | ▲▲ strongly favoured by winners |
| absorb | 0.061 | 0.048 | 1.28× | ▲▲ strongly favoured by winners |

### Opening preferences (first 3 tiles)

- **Colour** — winners: `{'Y': 0.34, 'R': 0.338, 'B': 0.323}` · losers: `{'R': 0.377, 'B': 0.318, 'Y': 0.305}`
- **Region** (first move) — winners' top: `{'mid-center': 0.308, 'bot-center': 0.212, 'top-center': 0.205}`

### Endgame

Avg pagodas placed at game end — **winner 24.14** vs loser 19.59.

> **Takeaway:** winners lean hardest on **conquer** (1.35× the losing rate); turn order is worth ~5 points to the first player.


---

## 3-player — board `bird` (agents: greedy, greedy, greedy)

*150 games.*

### Turn-order effect (seat win-rate)

| Seat | Win-rate | |
|------|---------:|---|
| 0 (first) | 45.3% | `████████████████████████` |
| 1 | 30.0% | `████████████████········` |
| 2 | 24.7% | `█████████████···········` |

Shared/tie games: 0.0%.
First-mover spread: **20.6 pts** (seat 0 leads).

### What winners do more (per-turn event lift)

Lift = winner's per-turn rate ÷ loser's. >1 means winners do it more.

| Event | Winner/turn | Loser/turn | Lift | |
|-------|------------:|-----------:|-----:|---|
| found | 0.846 | 0.804 | 1.05× | ≈ neutral |
| expand | 0.172 | 0.191 | 0.90× | ≈ neutral |
| major | 0.078 | 0.056 | 1.40× | ▲▲ strongly favoured by winners |
| connect | 0.338 | 0.249 | 1.36× | ▲▲ strongly favoured by winners |
| conquer | 0.106 | 0.062 | 1.71× | ▲▲ strongly favoured by winners |
| absorb | 0.071 | 0.047 | 1.50× | ▲▲ strongly favoured by winners |

### Opening preferences (first 3 tiles)

- **Colour** — winners: `{'R': 0.353, 'Y': 0.343, 'B': 0.303}` · losers: `{'Y': 0.342, 'B': 0.335, 'R': 0.323}`
- **Region** (first move) — winners' top: `{'mid-center': 0.293, 'bot-center': 0.193, 'top-center': 0.171}`

### Endgame

Avg pagodas placed at game end — **winner 19.15** vs loser 14.36.

> **Takeaway:** winners lean hardest on **conquer** (1.71× the losing rate); turn order is worth ~21 points to the first player.


---

## 4-player — board `bird` (agents: greedy, greedy, greedy, greedy)

*120 games.*

### Turn-order effect (seat win-rate)

| Seat | Win-rate | |
|------|---------:|---|
| 0 (first) | 38.3% | `████████████████████████` |
| 1 | 17.5% | `███████████·············` |
| 2 | 24.2% | `███████████████·········` |
| 3 | 20.0% | `█████████████···········` |

Shared/tie games: 0.0%.
First-mover spread: **20.8 pts** (seat 0 leads).

### What winners do more (per-turn event lift)

Lift = winner's per-turn rate ÷ loser's. >1 means winners do it more.

| Event | Winner/turn | Loser/turn | Lift | |
|-------|------------:|-----------:|-----:|---|
| found | 0.849 | 0.821 | 1.03× | ≈ neutral |
| expand | 0.162 | 0.186 | 0.87× | ≈ neutral |
| major | 0.067 | 0.050 | 1.35× | ▲▲ strongly favoured by winners |
| connect | 0.339 | 0.255 | 1.33× | ▲▲ strongly favoured by winners |
| conquer | 0.119 | 0.064 | 1.86× | ▲▲ strongly favoured by winners |
| absorb | 0.075 | 0.046 | 1.64× | ▲▲ strongly favoured by winners |

### Opening preferences (first 3 tiles)

- **Colour** — winners: `{'B': 0.347, 'Y': 0.329, 'R': 0.324}` · losers: `{'Y': 0.344, 'B': 0.339, 'R': 0.317}`
- **Region** (first move) — winners' top: `{'mid-center': 0.225, 'top-center': 0.203, 'bot-center': 0.194}`

### Endgame

Avg pagodas placed at game end — **winner 15.12** vs loser 11.15.

> **Takeaway:** winners lean hardest on **conquer** (1.86× the losing rate); turn order is worth ~21 points to the first player.


---

## Cross-cut summary

| Players | 1st-seat win% | Worst-seat win% | Top winner lever |
|--------:|--------------:|----------------:|------------------|
| 2 | 52% | 48% | conquer (1.35×) |
| 3 | 45% | 25% | conquer (1.71×) |
| 4 | 38% | 18% | conquer (1.86×) |
