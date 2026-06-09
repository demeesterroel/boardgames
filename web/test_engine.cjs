// Headless sanity checks for the JS engine. Run: node web/test_engine.cjs
const QIN = require("./engine.js");
const { Board, State, IllegalMove, botMove } = QIN;

let pass = 0, fail = 0;
function check(name, cond) {
  if (cond) { pass++; } else { fail++; console.error("FAIL:", name); }
}
function mkState(map, np = 2) { return new State(Board.fromAscii(map), np, 1); }
function place(s, a, ca, b, cb, player) {
  s.resolvePlacement({ a: s.board.idx(...a), ca, b: s.board.idx(...b), cb }, player);
}

// 1. found
(() => {
  const s = mkState("R..\n...");
  place(s, [0, 1], "R", [0, 2], "R", 0);
  check("found: one province", s.provinces.length === 1);
  check("found: owner/size", s.provinces[0].owner === 0 && s.provinces[0].cells.size === 3 && !s.provinces[0].major);
  check("found: on_board", JSON.stringify(s.onBoard()) === JSON.stringify([1, 0]));
})();

// 2. two single spaces -> no province
(() => {
  const s = mkState("R.\nB.\n..");
  place(s, [0, 1], "B", [1, 1], "R", 0);
  check("two-singles: no province", s.provinces.length === 0);
})();

// 3. expand then major
(() => {
  const s = mkState("R.....\n......");
  place(s, [0, 1], "R", [0, 2], "R", 0);
  check("expand: not major yet", !s.provinces[0].major);
  place(s, [0, 3], "R", [0, 4], "R", 0);
  check("major: single province size5", s.provinces.length === 1 && s.provinces[0].cells.size === 5 && s.provinces[0].major);
  check("major: counts as 2", JSON.stringify(s.onBoard()) === JSON.stringify([2, 0]));
})();

// 4. connect village
(() => {
  const s = mkState("R..\no..");
  place(s, [0, 1], "R", [0, 2], "R", 0);
  check("connect: village owned by 0", s.villageOwner.get(s.board.idx(1, 0)) === 0);
})();

// 5. conquer (double counts as 2)
(() => {
  const s = mkState("Y....\no....\nR....\n.....\n.....");
  place(s, [0, 1], "Y", [1, 1], "Y", 1);
  check("conquer: connected by P1", s.villageOwner.get(s.board.idx(1, 0)) === 1);
  place(s, [2, 1], "R", [3, 1], "R", 0);
  place(s, [3, 0], "R", [4, 0], "R", 0);
  check("conquer: P0 major takes it", s.villageOwner.get(s.board.idx(1, 0)) === 0);
})();

// 6. absorb by largest contributor
(() => {
  const s = mkState("RR..RRR");
  for (const c of [[0, 0], [0, 1], [0, 4], [0, 5], [0, 6]]) { const i = s.board.idx(...c); s.board.terrain[i] = QIN.PROVINCE; s.board.color[i] = "R"; }
  s.provinces = [
    { cells: new Set([0, 1].map((c) => s.board.idx(0, c))), color: "R", owner: 0, major: false },
    { cells: new Set([4, 5, 6].map((c) => s.board.idx(0, c))), color: "R", owner: 1, major: false },
  ];
  place(s, [0, 2], "R", [0, 3], "R", 0);
  check("absorb: single major size7", s.provinces.length === 1 && s.provinces[0].major && s.provinces[0].cells.size === 7);
  check("absorb: owner is larger contributor (P1)", s.provinces[0].owner === 1);
})();

// 7. two majors cannot combine
(() => {
  const s = mkState("RRRRR.RRRRR\n.....Y.....");
  const ca = [0, 1, 2, 3, 4].map((c) => s.board.idx(0, c));
  const cb = [6, 7, 8, 9, 10].map((c) => s.board.idx(0, c));
  for (const i of [...ca, ...cb]) { s.board.terrain[i] = QIN.PROVINCE; s.board.color[i] = "R"; }
  s.provinces = [
    { cells: new Set(ca), color: "R", owner: 0, major: true },
    { cells: new Set(cb), color: "R", owner: 1, major: true },
  ];
  let threw = false;
  try { place(s, [0, 5], "R", [1, 5], "Y", 0); } catch (e) { threw = e instanceof IllegalMove; }
  check("two-majors illegal", threw);
})();

// 8. absorb exact tie illegal
(() => {
  const s = mkState("RR.RR\n..Y..");
  const ca = [0, 1].map((c) => s.board.idx(0, c));
  const cb = [3, 4].map((c) => s.board.idx(0, c));
  for (const i of [...ca, ...cb]) { s.board.terrain[i] = QIN.PROVINCE; s.board.color[i] = "R"; }
  s.provinces = [
    { cells: new Set(ca), color: "R", owner: 0, major: false },
    { cells: new Set(cb), color: "R", owner: 1, major: false },
  ];
  let threw = false;
  try { place(s, [0, 2], "R", [1, 2], "Y", 0); } catch (e) { threw = e instanceof IllegalMove; }
  check("absorb tie illegal", threw);
})();

// 9. village tie does not seize
(() => {
  const s = mkState("Y.R\n.o.\n...");
  for (const [c, col] of [[[0, 0], "Y"], [[1, 0], "Y"], [[0, 2], "R"], [[1, 2], "R"]]) {
    const i = s.board.idx(...c); s.board.terrain[i] = QIN.PROVINCE; s.board.color[i] = col;
  }
  s.provinces = [
    { cells: new Set([s.board.idx(0, 0), s.board.idx(1, 0)]), color: "Y", owner: 0, major: false },
    { cells: new Set([s.board.idx(0, 2), s.board.idx(1, 2)]), color: "R", owner: 1, major: false },
  ];
  const ev = []; s.resolveVillages(ev);
  check("village tie -> unowned", !s.villageOwner.has(s.board.idx(1, 1)));
})();

// 10. legalMoves filters illegal absorbs
(() => {
  const s = mkState("RR.RR\n.....");
  const ca = [0, 1].map((c) => s.board.idx(0, c));
  const cb = [3, 4].map((c) => s.board.idx(0, c));
  for (const i of [...ca, ...cb]) { s.board.terrain[i] = QIN.PROVINCE; s.board.color[i] = "R"; }
  s.provinces = [
    { cells: new Set(ca), color: "R", owner: 0, major: false },
    { cells: new Set(cb), color: "R", owner: 1, major: false },
  ];
  s.hands[0] = [["R", "R"]];
  const bridge = s.board.idx(0, 2);
  const moves = s.legalMoves(0);
  const hasBridge = moves.some((m) => (m.a === bridge || m.b === bridge) && QIN.tileKey(m.ca, m.cb) === "RR");
  check("legalMoves excludes tie-absorb bridge", !hasBridge);
})();

// 11. full random games terminate with a winner
(() => {
  const map = "..o.o.o..\n.o..o..o.\n..o.B....\n..o.Y.o..\n..o.R..o.\n....o....\n.o.....o.\n.........\n....o.o..";
  for (let seed = 0; seed < 10; seed++) {
    const s = new State(Board.fromAscii(map), 2, seed);
    let steps = 0;
    while (!s.isTerminal() && steps < 5000) {
      const m = botMove(s, s.rng) || s.legalMoves()[0];
      if (!m) break;
      s.apply(m); steps++;
    }
    check(`game seed ${seed} terminates`, s.isTerminal());
  }
})();

// 12. determinize preserves observer hand + tile multiset
(() => {
  const map = "..o.o.o..\n.o..o..o.\n..o.B....\n..o.Y.o..\n..o.R..o.\n....o....\n.o.....o.\n.........\n....o.o..";
  const s = new State(Board.fromAscii(map), 3, 1);
  for (let i = 0; i < 8; i++) { const ms = s.legalMoves(); if (!ms.length) break; s.apply(ms[0]); }
  const obs = s.currentPlayer;
  const tally = (st) => { const c = {}; for (const h of st.hands) for (const t of h) c[QIN.tileKey(t[0],t[1])]=(c[QIN.tileKey(t[0],t[1])]||0)+1; for (const t of st.deck) c[QIN.tileKey(t[0],t[1])]=(c[QIN.tileKey(t[0],t[1])]||0)+1; return JSON.stringify(Object.keys(c).sort().map((k)=>[k,c[k]])); };
  const before = tally(s);
  const d = s.determinize(obs, Math.random);
  check("determinize: observer hand preserved", JSON.stringify(d.hands[obs]) === JSON.stringify(s.hands[obs]));
  check("determinize: hand sizes preserved", d.hands.every((h,i)=>h.length===s.hands[i].length));
  check("determinize: multiset conserved", tally(d) === before);
})();

// 13. mcts returns a legal move and (weakly) beats greedy over a few games
(() => {
  const map = "....oo.....o\n............\n............\n.o......o...\n.....B......\n............\n.....Y......\n.o.......oo.\n.o...R......\n............\n............\n......oo...o";
  // returns legal
  const s = new State(Board.fromAscii(map), 2, 5);
  for (let i = 0; i < 6; i++) s.apply(s.legalMoves()[0]);
  const m = QIN.mctsMove(s, 40, Math.random);
  check("mcts returns legal move", s.legalMoves().some((x)=>QIN.tileKey(x.ca,x.cb)===QIN.tileKey(m.ca,m.cb)&&x.a===m.a&&x.b===m.b));

  // one quick mcts-driven game terminates cleanly (strength is validated in
  // the Python tournament; here we only check the JS port runs end to end)
  const st = new State(Board.fromAscii(map), 2, 100);
  let n = 0;
  while (!st.isTerminal() && n < 4000) {
    const ms = st.legalMoves(); if (!ms.length) break;
    const mv = st.currentPlayer === 0 ? QIN.mctsMove(st, 30, Math.random) : botMove(st, Math.random);
    st.apply(mv); n++;
  }
  check("mcts-driven game terminates", st.isTerminal());
})();

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
