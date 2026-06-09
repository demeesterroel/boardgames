/* QIN rules engine — JavaScript port of the tested Python engine (qin/engine.py).
 *
 * Runs both in the browser (defines window.QIN) and in Node (module.exports),
 * so the same code powers the web UI and the headless sanity tests.
 *
 * The six rulebook events are unified into a province pass
 * (found / expand / major / absorb) and a village pass (connect / conquer),
 * matching the Python implementation.
 */
(function (root) {
  "use strict";

  const COLORS = ["R", "Y", "B"];
  const WATER = 0, GRASS = 1, VILLAGE = 2, PROVINCE = 3;
  const PAGODAS = { 2: 24, 3: 19, 4: 15 };
  const MAJOR = 5;
  const HAND = 3;

  function makeRng(seed) {
    let a = (seed >>> 0) || 0x9e3779b9;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function shuffle(arr, rng) {
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  }

  class Board {
    constructor(rows, cols) {
      this.rows = rows; this.cols = cols;
      this.terrain = new Int8Array(rows * cols).fill(WATER);
      this.color = new Array(rows * cols).fill(null);
    }
    idx(r, c) { return r * this.cols + c; }
    rc(i) { return [Math.floor(i / this.cols), i % this.cols]; }
    neighbors(i) {
      const [r, c] = this.rc(i); const out = [];
      if (r > 0) out.push(i - this.cols);
      if (r < this.rows - 1) out.push(i + this.cols);
      if (c > 0) out.push(i - 1);
      if (c < this.cols - 1) out.push(i + 1);
      return out;
    }
    clone() {
      const b = new Board(this.rows, this.cols);
      b.terrain = this.terrain.slice();
      b.color = this.color.slice();
      return b;
    }
    static fromAscii(text) {
      const lines = text.replace(/^\n+|\n+$/g, "").split("\n");
      const w = Math.max(...lines.map((l) => l.length));
      const b = new Board(lines.length, w);
      for (let r = 0; r < lines.length; r++) {
        const line = lines[r].padEnd(w, " ");
        for (let c = 0; c < w; c++) {
          const ch = line[c]; const i = b.idx(r, c);
          if (ch === "#" || ch === " ") b.terrain[i] = WATER;
          else if (ch === ".") b.terrain[i] = GRASS;
          else if (ch === "o" || ch === "v") b.terrain[i] = VILLAGE;
          else if (COLORS.includes(ch)) { b.terrain[i] = PROVINCE; b.color[i] = ch; }
          else throw new Error("bad map char " + ch);
        }
      }
      return b;
    }
    villages() {
      const out = [];
      for (let i = 0; i < this.terrain.length; i++) if (this.terrain[i] === VILLAGE) out.push(i);
      return out;
    }
    sameColorComponent(start) {
      const color = this.color[start];
      if (color == null) return new Set();
      const seen = new Set([start]); const stack = [start];
      while (stack.length) {
        const cur = stack.pop();
        for (const n of this.neighbors(cur)) {
          if (!seen.has(n) && this.terrain[n] === PROVINCE && this.color[n] === color) {
            seen.add(n); stack.push(n);
          }
        }
      }
      return seen;
    }
  }

  function fullDeck() {
    const types = [];
    for (let i = 0; i < COLORS.length; i++)
      for (let j = i; j < COLORS.length; j++) types.push([COLORS[i], COLORS[j]]);
    const deck = [];
    for (const t of types) for (let k = 0; k < 12; k++) deck.push(t.slice());
    return deck;
  }
  function tileKey(a, b) { return [a, b].sort().join(""); }

  class IllegalMove extends Error {}

  class State {
    constructor(board, numPlayers, seed) {
      if (!PAGODAS[numPlayers]) throw new Error("2-4 players only");
      this.board = board;
      this.numPlayers = numPlayers;
      this.allotment = PAGODAS[numPlayers];
      this.rng = makeRng(seed == null ? (Math.random() * 2 ** 31) | 0 : seed);
      this.provinces = [];
      this.villageOwner = new Map();
      this.currentPlayer = 0;
      this.winner = null;
      this.sharedWinners = null;
      this.gameOver = false;
      this.deck = shuffle(fullDeck(), this.rng);
      this.hands = Array.from({ length: numPlayers }, () => []);
      for (let k = 0; k < HAND; k++)
        for (let p = 0; p < numPlayers; p++)
          if (this.deck.length) this.hands[p].push(this.deck.pop());
    }
    clone() {
      const s = Object.create(State.prototype);
      s.board = this.board.clone();
      s.numPlayers = this.numPlayers;
      s.allotment = this.allotment;
      s.rng = this.rng;
      s.provinces = this.provinces.map((p) => ({ cells: new Set(p.cells), color: p.color, owner: p.owner, major: p.major }));
      s.villageOwner = new Map(this.villageOwner);
      s.currentPlayer = this.currentPlayer;
      s.winner = this.winner; s.sharedWinners = this.sharedWinners; s.gameOver = this.gameOver;
      s.deck = this.deck.slice();
      s.hands = this.hands.map((h) => h.map((t) => t.slice()));
      s._anchorCache = this._anchorCache;  // same board position; safe to share
      return s;
    }
    onBoard() {
      const c = new Array(this.numPlayers).fill(0);
      for (const p of this.provinces) c[p.owner] += p.major ? 2 : 1;
      for (const o of this.villageOwner.values()) c[o] += 1;
      return c;
    }
    supply(p) { return this.allotment - this.onBoard()[p]; }

    touchesProvince(a, b) {
      for (const [cell, other] of [[a, b], [b, a]])
        for (const n of this.board.neighbors(cell))
          if (n !== other && this.board.terrain[n] === PROVINCE) return true;
      return false;
    }
    candidatePairs() {
      const out = []; const B = this.board;
      for (let r = 0; r < B.rows; r++)
        for (let c = 0; c < B.cols; c++) {
          const i = B.idx(r, c);
          if (B.terrain[i] !== GRASS) continue;
          if (c + 1 < B.cols) { const j = B.idx(r, c + 1); if (B.terrain[j] === GRASS) out.push([i, j]); }
          if (r + 1 < B.rows) { const j = B.idx(r + 1, c); if (B.terrain[j] === GRASS) out.push([i, j]); }
        }
      return out;
    }
    // Anchor pairs (placements touching a province) are independent of the
    // hand, so cache them; they only change when the board changes (apply).
    anchorPairs() {
      if (this._anchorCache) return this._anchorCache;
      const out = [];
      for (const [a, b] of this.candidatePairs())
        if (this.touchesProvince(a, b)) out.push([a, b]);
      this._anchorCache = out;
      return out;
    }
    legalMoves(player) {
      if (player == null) player = this.currentPlayer;
      if (this.gameOver) return [];
      const handTypes = new Map();
      for (const t of this.hands[player]) handTypes.set(tileKey(t[0], t[1]), t);
      const moves = [];
      for (const [a, b] of this.anchorPairs()) {
        for (const t of handTypes.values()) {
          const assigns = t[0] === t[1] ? [[t[0], t[1]]] : [[t[0], t[1]], [t[1], t[0]]];
          for (const [ca, cb] of assigns) {
            const move = { a, ca, b, cb };
            if (this.isLegal(move, player)) moves.push(move);
          }
        }
      }
      return moves;
    }
    isLegal(move, player) {
      // Fast in-place check (mirrors qin/engine.py): geometry is guaranteed for
      // candidates, so only the absorb rule can make a placement illegal.
      const B = this.board; const { a, ca, b, cb } = move;
      const ta = B.terrain[a], ca0 = B.color[a];
      const tb = B.terrain[b], cb0 = B.color[b];
      B.terrain[a] = PROVINCE; B.color[a] = ca;
      B.terrain[b] = PROVINCE; B.color[b] = cb;
      let ok = true;
      const seen = new Set();
      for (const cell of [a, b]) {
        const comp = B.sameColorComponent(cell);
        const key = [...comp].sort((x, y) => x - y).join(",");
        if (seen.has(key)) continue;
        seen.add(key);
        const prev = this.provinces.filter((p) => this.overlaps(p, comp));
        if (prev.length >= 2) {
          if (prev.filter((p) => p.major).length >= 2) { ok = false; break; }
          const contrib = new Map();
          for (const p of prev) contrib.set(p.owner, (contrib.get(p.owner) || 0) + p.cells.size);
          const top = Math.max(...contrib.values());
          if ([...contrib.values()].filter((v) => v === top).length !== 1) { ok = false; break; }
        }
      }
      B.terrain[a] = ta; B.color[a] = ca0;
      B.terrain[b] = tb; B.color[b] = cb0;
      return ok;
    }
    apply(move) {
      if (this.gameOver) throw new IllegalMove("game over");
      const player = this.currentPlayer;
      const key = tileKey(move.ca, move.cb);
      const hi = this.hands[player].findIndex((t) => tileKey(t[0], t[1]) === key);
      if (hi < 0) throw new IllegalMove("tile not in hand");
      const events = this.resolvePlacement(move, player);
      this.hands[player].splice(hi, 1);
      if (!this.gameOver) {
        if (this.deck.length) this.hands[player].push(this.deck.pop());
        this.advanceTurn();
      }
      return events;
    }
    advanceTurn() {
      this.currentPlayer = (this.currentPlayer + 1) % this.numPlayers;
      if (this.legalMoves(this.currentPlayer).length === 0) this.endByBlockage();
    }
    endByBlockage() {
      const c = this.onBoard(); const best = Math.max(...c);
      const w = []; c.forEach((n, p) => { if (n === best) w.push(p); });
      this.gameOver = true;
      if (w.length === 1) this.winner = w[0]; else this.sharedWinners = w;
    }
    resolvePlacement(move, player) {
      const B = this.board; const { a, ca, b, cb } = move;
      if (!B.neighbors(a).includes(b)) throw new IllegalMove("not adjacent");
      if (B.terrain[a] !== GRASS || B.terrain[b] !== GRASS) throw new IllegalMove("not grass");
      if (!this.touchesProvince(a, b)) throw new IllegalMove("must touch a province");
      const events = [];
      B.terrain[a] = PROVINCE; B.color[a] = ca;
      B.terrain[b] = PROVINCE; B.color[b] = cb;
      this._anchorCache = null;   // board changed: invalidate anchor-pair cache
      const comps = new Map();
      for (const cell of [a, b]) {
        const comp = B.sameColorComponent(cell);
        comps.set([...comp].sort((x, y) => x - y).join(","), comp);
      }
      for (const comp of comps.values()) this.resolveProvince(comp, player, events);
      this.resolveVillages(events);
      if (this.supply(player) <= 0) {
        this.winner = player; this.gameOver = true;
        events.push(`P${player} placed their last pagoda and WINS!`);
      }
      return events;
    }
    overlaps(prov, comp) { for (const c of prov.cells) if (comp.has(c)) return true; return false; }
    resolveProvince(comp, player, events) {
      const any = comp.values().next().value;
      const color = this.board.color[any];
      const size = comp.size;
      const prev = this.provinces.filter((p) => this.overlaps(p, comp));
      if (prev.length === 0) {
        if (size < 2) return;
        const major = size >= MAJOR;
        this.provinces.push({ cells: comp, color, owner: player, major });
        events.push(`P${player} founds a ${color} ${major ? "major province" : "province"} (${size} spaces)`);
      } else if (prev.length === 1) {
        const p0 = prev[0];
        const major = p0.major || size >= MAJOR;
        this.removeProvinces(prev);
        this.provinces.push({ cells: comp, color, owner: p0.owner, major });
        events.push(major && !p0.major
          ? `P${p0.owner} expands ${color} province to ${size} spaces -> now MAJOR`
          : `P${p0.owner} expands ${color} province to ${size} spaces`);
      } else {
        if (prev.filter((p) => p.major).length >= 2) throw new IllegalMove("two majors");
        const contrib = new Map();
        for (const p of prev) contrib.set(p.owner, (contrib.get(p.owner) || 0) + p.cells.size);
        const top = Math.max(...contrib.values());
        const winners = [...contrib].filter(([, v]) => v === top).map(([o]) => o);
        if (winners.length !== 1) throw new IllegalMove("absorb tie");
        const owner = winners[0];
        this.removeProvinces(prev);
        this.provinces.push({ cells: comp, color, owner, major: true });
        events.push(`P${owner} absorbs ${color} provinces into a major province (${size} spaces)`);
      }
    }
    removeProvinces(list) { this.provinces = this.provinces.filter((p) => !list.includes(p)); }
    resolveVillages(events) {
      const cellToProv = new Map();
      for (const p of this.provinces) for (const c of p.cells) cellToProv.set(c, p);
      for (const v of this.board.villages()) {
        const adj = new Set();
        for (const n of this.board.neighbors(v)) { const pr = cellToProv.get(n); if (pr) adj.add(pr); }
        const weight = new Map();
        for (const p of adj) weight.set(p.owner, (weight.get(p.owner) || 0) + (p.major ? 2 : 1));
        if (weight.size === 0) continue;
        const cur = this.villageOwner.has(v) ? this.villageOwner.get(v) : null;
        const curW = cur != null ? (weight.get(cur) || 0) : 0;
        const top = Math.max(...weight.values());
        const leaders = [...weight].filter(([, w]) => w === top).map(([o]) => o);
        if (leaders.length === 1 && top > curW && leaders[0] !== cur) {
          const no = leaders[0];
          events.push(`P${no} ${cur == null ? "connects" : "conquers (from P" + cur + ")"} village`);
          this.villageOwner.set(v, no);
        }
      }
    }
    isTerminal() { return this.gameOver; }
    result() { return { winner: this.winner, sharedWinners: this.sharedWinners, onBoard: this.onBoard() }; }

    // Fast greedy score for a move: pagodas the mover would place this turn
    // (founds + village seizes) *10 + majors, computed in place without a full
    // clone. Used by the rollout policy. Restores the board before returning.
    scoreMove(move, me) {
      const B = this.board; const { a, ca, b, cb } = move;
      const ta = B.terrain[a], ca0 = B.color[a];
      const tb = B.terrain[b], cb0 = B.color[b];
      B.terrain[a] = PROVINCE; B.color[a] = ca;
      B.terrain[b] = PROVINCE; B.color[b] = cb;
      let gained = 0, majors = 0;
      const seen = new Set();
      for (const cell of [a, b]) {
        const comp = B.sameColorComponent(cell);
        const key = [...comp].sort((x, y) => x - y).join(",");
        if (seen.has(key)) continue;
        seen.add(key);
        const prev = this.provinces.filter((p) => this.overlaps(p, comp));
        const size = comp.size;
        if (prev.length === 0) {
          if (size >= 2) { gained += size >= MAJOR ? 2 : 1; if (size >= MAJOR) majors++; }
        } else if (prev.length === 1) {
          if (size >= MAJOR && !prev[0].major) { gained += 1; majors++; } // single->double
        } else {
          // absorb: contributor with most cells keeps a (double) pagoda
          const contrib = new Map();
          for (const p of prev) contrib.set(p.owner, (contrib.get(p.owner) || 0) + p.cells.size);
          const top = Math.max(...contrib.values());
          const winners = [...contrib].filter(([, v]) => v === top);
          if (winners.length === 1 && winners[0][0] === me) majors++;
        }
      }
      B.terrain[a] = ta; B.color[a] = ca0;
      B.terrain[b] = tb; B.color[b] = cb0;
      return gained * 10 + majors;
    }

    // Cheap rollout helper: return ONE random legal move without enumerating
    // them all. Tries shuffled (anchor, tile, orientation) combos and returns
    // the first legal one. Much faster than legalMoves() when only a sample is
    // needed (rollouts). Returns null if no legal move exists.
    randomLegalMove(rand) {
      const player = this.currentPlayer;
      const anchors = this.anchorPairs();
      const hand = [];
      const seen = new Set();
      for (const t of this.hands[player]) {
        const k = tileKey(t[0], t[1]);
        if (!seen.has(k)) { seen.add(k); hand.push(t); }
      }
      // build a shuffled index list over anchors
      const order = anchors.map((_, i) => i);
      for (let i = order.length - 1; i > 0; i--) {
        const j = Math.floor(rand() * (i + 1));
        [order[i], order[j]] = [order[j], order[i]];
      }
      for (const idx of order) {
        const [a, b] = anchors[idx];
        // shuffle hand tiles
        const htiles = hand.slice();
        for (let i = htiles.length - 1; i > 0; i--) {
          const j = Math.floor(rand() * (i + 1));
          [htiles[i], htiles[j]] = [htiles[j], htiles[i]];
        }
        for (const t of htiles) {
          const assigns = t[0] === t[1] ? [[t[0], t[1]]] : (rand() < 0.5
            ? [[t[0], t[1]], [t[1], t[0]]] : [[t[1], t[0]], [t[0], t[1]]]);
          for (const [ca, cb] of assigns) {
            const m = { a, ca, b, cb };
            if (this.isLegal(m, player)) return m;
          }
        }
      }
      return null;
    }

    // Resample hidden info (opponents' hands + deck) from observer's view.
    determinize(observer, rand) {
      const s = this.clone();
      let pool = s.deck.slice();
      for (let pl = 0; pl < s.numPlayers; pl++)
        if (pl !== observer) pool = pool.concat(s.hands[pl]);
      // Fisher-Yates with the provided rand()
      for (let i = pool.length - 1; i > 0; i--) {
        const j = Math.floor(rand() * (i + 1));
        [pool[i], pool[j]] = [pool[j], pool[i]];
      }
      let idx = 0;
      for (let pl = 0; pl < s.numPlayers; pl++) {
        if (pl !== observer) {
          const k = s.hands[pl].length;
          s.hands[pl] = pool.slice(idx, idx + k); idx += k;
        }
      }
      s.deck = pool.slice(idx);
      return s;
    }
  }

  // A simple, NON-AI heuristic bot: greedily maximise pagodas placed this turn
  // (founds + village seizes) with a small bonus for majors; ties random.
  function botMove(state, rng) {
    rng = rng || Math.random;
    const moves = state.legalMoves();
    if (moves.length === 0) return null;
    const me = state.currentPlayer;
    let best = [], bestScore = -Infinity;
    for (const m of moves) {
      const t = state.clone();
      const before = t.onBoard()[me];
      try { t.resolvePlacement(m, me); } catch (e) { continue; }
      const gained = t.onBoard()[me] - before;
      const majors = t.provinces.filter((p) => p.owner === me && p.major).length;
      const score = gained * 10 + majors;
      if (score > bestScore) { bestScore = score; best = [m]; }
      else if (score === bestScore) best.push(m);
    }
    return best[Math.floor(rng() * best.length)];
  }

  // greedy choice used both as a bot and as the MCTS rollout policy
  function greedyMove(state, moves, rng) {
    const me = state.currentPlayer;
    const sample = moves.length <= 12 ? moves
      : moves.slice().sort(() => rng() - 0.5).slice(0, 12);
    let best = [], bestScore = -Infinity;
    for (const m of sample) {
      const t = state.clone();
      const before = t.onBoard()[me];
      try { t.resolvePlacement(m, me); } catch (e) { continue; }
      const gained = t.onBoard()[me] - before;
      const majors = t.provinces.filter((p) => p.owner === me && p.major).length;
      const score = gained * 10 + majors;
      if (score > bestScore) { bestScore = score; best = [m]; }
      else if (score === bestScore) best.push(m);
    }
    return best[Math.floor(rng() * best.length)];
  }

  function moveId(m) { return m.a + ":" + m.ca + ":" + m.b + ":" + m.cb; }

  // Determinized-UCT MCTS bot (single-observer ISMCTS), JS port of MCTSAgent.
  // `iterations` controls strength. For browser responsiveness this port uses
  // greedy action-pruning (a shortlist of candidate moves per node, since QIN
  // is 200+ moves wide) plus light greedy rollouts (sample a few legal moves,
  // take the best by an in-place pagoda score). Greedy rollouts are what make
  // the search meaningfully beat the one-ply greedy bot.
  function mctsMove(state, iterations, rng) {
    rng = rng || Math.random;
    const root = { visits: 0, toPlay: state.currentPlayer, children: new Map() };
    const C = 1.4, rolloutDepth = 50;

    function rewardVec(s) {
      const n = s.numPlayers, v = new Array(n).fill(0);
      if (s.winner != null) { v[s.winner] = 1; return v; }
      if (s.sharedWinners) { for (const w of s.sharedWinners) v[w] = 1 / s.sharedWinners.length; return v; }
      const onb = s.onBoard(), best = Math.max(...onb);
      const lead = onb.map((x, i) => x === best ? i : -1).filter((i) => i >= 0);
      for (const i of lead) v[i] = 1 / lead.length;
      return v;
    }
    function rollout(s) {
      // Light greedy rollouts: sample a few legal moves cheaply (no full
      // enumeration) and take the one that places the most pagodas this turn.
      // Greedy playouts give MCTS real signal — uniform-random ones do not on a
      // game this wide — while staying browser-fast.
      const ROLL_SAMPLE = 5;
      let depth = 0;
      while (!s.isTerminal() && depth < rolloutDepth) {
        const me = s.currentPlayer;
        let best = null, bestScore = -Infinity, n = 0;
        for (let k = 0; k < ROLL_SAMPLE; k++) {
          const m = s.randomLegalMove(rng);
          if (!m) break;
          n++;
          const sc = s.scoreMove(m, me);
          if (sc > bestScore) { bestScore = sc; best = m; }
        }
        if (!best) break;
        s.apply(best); depth++;
      }
      return rewardVec(s);
    }
    function uctSelect(node, legal) {
      let total = 1;
      for (const m of legal) { const ch = node.children.get(moveId(m)); if (ch) total += ch.visits; }
      const logT = Math.log(total);
      let best = null, bestVal = -1e18;
      for (const m of legal) {
        const ch = node.children.get(moveId(m));
        if (!ch || ch.visits === 0) return m;
        const val = ch.reward / ch.visits + C * Math.sqrt(logT / ch.visits);
        if (val > bestVal) { bestVal = val; best = m; }
      }
      return best;
    }

    // Action pruning: QIN can offer 200+ legal moves, far too wide for MCTS to
    // search meaningfully in a browser-friendly budget. At each node we expand
    // only a greedy-ranked shortlist of candidates (progressive-style pruning),
    // which both focuses the search and keeps iterations cheap.
    const CAND_CAP = 14;
    function candidates(s) {
      const me = s.currentPlayer;
      const legal = s.legalMoves();
      if (legal.length <= CAND_CAP) return legal;
      const scored = legal.map((m) => {
        const t = s.clone();
        const before = t.onBoard()[me];
        try { t.resolvePlacement(m, me); } catch (e) { return [m, -1]; }
        const gained = t.onBoard()[me] - before;
        const majors = t.provinces.filter((p) => p.owner === me && p.major).length;
        return [m, gained * 10 + majors];
      });
      scored.sort((x, y) => y[1] - x[1]);
      return scored.slice(0, CAND_CAP).map((kv) => kv[0]);
    }

    for (let it = 0; it < iterations; it++) {
      const s = state.determinize(state.currentPlayer, rng);
      const path = [];
      let node = root;
      while (true) {
        if (s.isTerminal()) break;
        const legal = candidates(s); if (legal.length === 0) break;
        const untried = legal.filter((m) => !node.children.has(moveId(m)));
        if (untried.length) {
          const m = untried[Math.floor(rng() * untried.length)];
          s.apply(m);
          const child = { visits: 0, reward: 0, toPlay: s.currentPlayer, children: new Map(), move: m };
          node.children.set(moveId(m), child);
          path.push({ parent: node, move: m });
          node = child; break;
        }
        const m = uctSelect(node, legal);
        s.apply(m);
        path.push({ parent: node, move: m });
        node = node.children.get(moveId(m));
      }
      const reward = rollout(s);
      root.visits++;
      for (const { parent, move } of path) {
        const ch = parent.children.get(moveId(move));
        ch.visits++; ch.reward += reward[parent.toPlay];
      }
    }
    const legal = state.legalMoves();
    if (legal.length === 0) return null;
    let best = legal[0], bestV = -1;
    for (const m of legal) {
      const ch = root.children.get(moveId(m));
      const v = ch ? ch.visits : 0;
      if (v > bestV) { bestV = v; best = m; }
    }
    return best;
  }

  const QIN = { Board, State, IllegalMove, botMove, greedyMove, mctsMove,
                makeRng, COLORS, WATER, GRASS, VILLAGE, PROVINCE, tileKey };
  if (typeof module !== "undefined" && module.exports) module.exports = QIN;
  else root.QIN = QIN;
})(typeof window !== "undefined" ? window : globalThis);
