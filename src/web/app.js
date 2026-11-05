// Chess Openings: the openings by name, learned line by line on a board.
// Python (gui.py) holds the lines and the progress; this draws and plays
"use strict";

const $ = (s) => document.querySelector(s);
const api = () => window.pywebview.api;
const FILES = "abcdefgh";
let PIECES = {};

// Portuguese names typed in the search mean these
const ALIASES = {
  bispo: "bishop", cavalo: "knight", dama: "queen", rainha: "queen", rei: "king", torre: "rook",
  siciliana: "sicilian", francesa: "french", italiana: "italian", espanhola: "ruy lopez",
  inglesa: "english", escocesa: "scotch", holandesa: "dutch", eslava: "slav", russa: "russian",
  escandinava: "scandinavian", gambito: "gambit", defesa: "defense", india: "indian", indiana: "indian",
  vienense: "vienna", viena: "vienna", catala: "catalan", peao: "pawn", abertura: "", do: "", da: "", de: "",
};

function fold(text) {
  return text.toLowerCase().normalize("NFKD").replace(/[^a-z0-9 ]/g, "");
}

function searchWords(query) {
  return fold(query).split(/\s+/).filter(Boolean)
    .flatMap((w) => (w in ALIASES ? ALIASES[w].split(" ") : [w])).filter(Boolean);
}

function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function stars(card) {
  const box = card ? card.box || 0 : 0;
  return box === 0 ? 0 : box < 3 ? 1 : box < 5 ? 2 : 3;
}

function starsHtml(n) {
  return `<span class="stars">${"★".repeat(n)}<span class="off">${"★".repeat(3 - n)}</span></span>`;
}

function isDue(card) {
  return card && card.history && card.due <= today();
}

function pieceUrl(code) {
  return `url("data:image/svg+xml;utf8,${encodeURIComponent(PIECES[code])}")`;
}

function parseFen(fen) {
  const out = {};
  fen.split(" ")[0].split("/").forEach((row, r) => {
    let f = 0;
    for (const ch of row) {
      if (/\d/.test(ch)) f += +ch;
      else {
        out[FILES[f] + (8 - r)] = (ch === ch.toUpperCase() ? "w" : "b") + ch.toUpperCase();
        f++;
      }
    }
  });
  return out;
}

function turnOf(fen) {
  return fen.split(" ")[1] === "w" ? "white" : "black";
}

// sounds, made here: no files to ship
const sound = {
  on: true,
  ctx: null,
  play(kind) {
    if (!this.on) return;
    this.ctx = this.ctx || new AudioContext();
    const tones = {
      move: [[420, 0.05, "triangle", 0.25]],
      capture: [[300, 0.07, "square", 0.12]],
      ok: [[660, 0.08, "sine", 0.2], [880, 0.12, "sine", 0.2]],
      bad: [[200, 0.18, "sawtooth", 0.08]],
      win: [[523, 0.1, "sine", 0.2], [659, 0.1, "sine", 0.2], [784, 0.1, "sine", 0.2], [1047, 0.25, "sine", 0.2]],
    }[kind];
    let t = this.ctx.currentTime;
    for (const [freq, len, type, vol] of tones) {
      const o = this.ctx.createOscillator();
      const g = this.ctx.createGain();
      o.type = type;
      o.frequency.value = freq;
      g.gain.setValueAtTime(vol, t);
      g.gain.exponentialRampToValueAtTime(0.001, t + len);
      o.connect(g).connect(this.ctx.destination);
      o.start(t);
      o.stop(t + len);
      t += len * 0.9;
    }
  },
};

// the board: click or drag; arrows and marks drawn over it
class Board {
  constructor(el, onMove) {
    this.el = el;
    this.onMove = onMove;
    this.orientation = "white";
    this.fen = null;
    this.pieces = {};
    this.movable = null; // "white", "black", "both" or null
    this.dests = {};
    this.marks = {};
    this.arrows = [];
    this.selected = null;
    this.last = null;
    el.classList.add("board");
    el.addEventListener("pointerdown", (e) => this.down(e));
    window.addEventListener("pointermove", (e) => this.drag(e));
    window.addEventListener("pointerup", (e) => this.up(e));
    el.addEventListener("contextmenu", (e) => e.preventDefault());
  }

  xy(sq) {
    const f = FILES.indexOf(sq[0]);
    const r = +sq[1] - 1;
    return this.orientation === "white" ? [f, 7 - r] : [7 - f, r];
  }

  squareAt(e) {
    const box = this.el.getBoundingClientRect();
    const x = Math.floor(((e.clientX - box.left) / box.width) * 8);
    const y = Math.floor(((e.clientY - box.top) / box.height) * 8);
    if (x < 0 || x > 7 || y < 0 || y > 7) return null;
    return this.orientation === "white" ? FILES[x] + (8 - y) : FILES[7 - x] + (y + 1);
  }

  set(fen, { last = null, animate = null, check = false } = {}) {
    this.fen = fen;
    this.pieces = parseFen(fen);
    this.last = last;
    this.check = check;
    this.selected = null;
    this.marks = {};
    this.arrows = [];
    this.render(animate);
  }

  setDests(dests) {
    this.dests = dests || {};
  }

  canMove(sq) {
    const p = this.pieces[sq];
    if (!p || !this.movable) return false;
    const color = p[0] === "w" ? "white" : "black";
    return (this.movable === "both" ? turnOf(this.fen) : this.movable) === color && turnOf(this.fen) === color;
  }

  render(animate) {
    const el = this.el;
    el.innerHTML = "";
    const kingInCheck = this.check
      ? Object.keys(this.pieces).find((s) => this.pieces[s] === (turnOf(this.fen) === "white" ? "wK" : "bK"))
      : null;
    for (let i = 0; i < 64; i++) {
      const sq = FILES[i % 8] + (Math.floor(i / 8) + 1);
      const [x, y] = this.xy(sq);
      const d = document.createElement("div");
      d.className = `sq ${(i % 8) + Math.floor(i / 8) & 1 ? "l" : "d"}`;
      d.style.left = `${x * 12.5}%`;
      d.style.top = `${y * 12.5}%`;
      if (this.last && (sq === this.last.slice(0, 2) || sq === this.last.slice(2, 4))) d.classList.add("last");
      if (sq === this.selected) d.classList.add("sel");
      if (sq === kingInCheck) d.classList.add("check");
      if (this.marks[sq]) d.classList.add(this.marks[sq]);
      if (this.selected && (this.dests[this.selected] || []).includes(sq)) {
        d.classList.add("dest");
        if (this.pieces[sq]) d.classList.add("cap");
      }
      if (y === 7) d.insertAdjacentHTML("beforeend", `<span class="coord f">${sq[0]}</span>`);
      if (x === 0) d.insertAdjacentHTML("beforeend", `<span class="coord r">${sq[1]}</span>`);
      d.dataset.sq = sq;
      el.appendChild(d);
    }
    this.pieceEls = {};
    for (const [sq, code] of Object.entries(this.pieces)) {
      const p = document.createElement("div");
      p.className = "pc";
      p.style.backgroundImage = pieceUrl(code);
      const [x, y] = this.xy(sq);
      p.style.transform = `translate(${x * 100}%, ${y * 100}%)`;
      el.appendChild(p);
      this.pieceEls[sq] = p;
    }
    if (animate) {
      const p = this.pieceEls[animate.slice(2, 4)];
      if (p) {
        const [fx, fy] = this.xy(animate.slice(0, 2));
        const target = p.style.transform;
        p.style.transform = `translate(${fx * 100}%, ${fy * 100}%)`;
        p.getBoundingClientRect();
        p.classList.add("anim");
        p.style.transform = target;
      }
    }
    this.drawArrows();
  }

  mark(marks) {
    this.marks = marks;
    for (const d of this.el.querySelectorAll(".sq")) {
      d.classList.remove("wrong", "hover");
      if (marks[d.dataset.sq]) d.classList.add(marks[d.dataset.sq]);
    }
  }

  setArrows(arrows) {
    this.arrows = arrows;
    this.drawArrows();
  }

  drawArrows() {
    this.el.querySelector("svg.arrows")?.remove();
    if (!this.arrows.length) return;
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("class", "arrows");
    svg.setAttribute("viewBox", "0 0 8 8");
    const colors = { green: "#15781b", blue: "#003088", hover: "#3692e7", red: "#882020", engine: "#8a3fbf", gray: "#6b6762" };
    const defs = document.createElementNS(ns, "defs");
    for (const [name, c] of Object.entries(colors)) {
      defs.insertAdjacentHTML(
        "beforeend",
        `<marker id="head-${name}" orient="auto" markerWidth="4" markerHeight="8" refX="2.05" refY="2.01">` +
          `<path d="M0,0 V4 L3,2 Z" fill="${c}"></path></marker>`,
      );
    }
    svg.appendChild(defs);
    for (const { from, to, color = "green", width = 0.16, opacity = 0.85 } of this.arrows) {
      const [x1, y1] = this.xy(from);
      const [x2, y2] = this.xy(to);
      const dx = x2 - x1;
      const dy = y2 - y1;
      const len = Math.hypot(dx, dy);
      const line = document.createElementNS(ns, "line");
      line.setAttribute("x1", x1 + 0.5);
      line.setAttribute("y1", y1 + 0.5);
      // stop short: the head ends at the square's center
      line.setAttribute("x2", x2 + 0.5 - (dx / len) * 0.38);
      line.setAttribute("y2", y2 + 0.5 - (dy / len) * 0.38);
      line.setAttribute("stroke", colors[color]);
      line.setAttribute("stroke-width", width);
      line.setAttribute("stroke-linecap", "round");
      line.setAttribute("marker-end", `url(#head-${color})`);
      line.setAttribute("opacity", opacity);
      svg.appendChild(line);
    }
    this.el.appendChild(svg);
  }

  select(sq) {
    this.selected = sq;
    for (const d of this.el.querySelectorAll(".sq")) {
      const s = d.dataset.sq;
      d.classList.toggle("sel", s === sq);
      const dest = sq && (this.dests[sq] || []).includes(s);
      d.classList.toggle("dest", !!dest);
      d.classList.toggle("cap", !!dest && !!this.pieces[s]);
    }
  }

  down(e) {
    if (e.button !== 0) return;
    const sq = this.squareAt(e);
    if (!sq) return;
    if (this.selected && sq !== this.selected && (this.dests[this.selected] || []).includes(sq)) {
      const from = this.selected;
      this.select(null);
      this.onMove(from, sq, true);
      return;
    }
    if (this.canMove(sq)) {
      this.select(sq);
      const p = this.pieceEls[sq];
      const box = this.el.getBoundingClientRect();
      this.dragging = { from: sq, el: p, box, moved: false, x: e.clientX, y: e.clientY };
      e.preventDefault();
    } else {
      this.select(null);
    }
  }

  drag(e) {
    const d = this.dragging;
    if (!d) return;
    if (!d.moved && Math.hypot(e.clientX - d.x, e.clientY - d.y) < 4) return;
    d.moved = true;
    const size = d.box.width / 8;
    d.el.classList.add("drag");
    d.el.style.transform = `translate(${e.clientX - d.box.left - size / 2}px, ${e.clientY - d.box.top - size / 2}px)`;
    const over = this.squareAt(e);
    for (const s of this.el.querySelectorAll(".sq.hover")) s.classList.remove("hover");
    if (over && (this.dests[d.from] || []).includes(over)) {
      this.el.querySelector(`.sq[data-sq="${over}"]`).classList.add("hover");
    }
  }

  up(e) {
    const d = this.dragging;
    if (!d) return;
    this.dragging = null;
    for (const s of this.el.querySelectorAll(".sq.hover")) s.classList.remove("hover");
    if (!d.moved) return; // a click: the piece stays selected
    const to = this.squareAt(e);
    d.el.classList.remove("drag");
    const [x, y] = this.xy(d.from);
    d.el.style.transform = `translate(${x * 100}%, ${y * 100}%)`;
    if (to && to !== d.from && (this.dests[d.from] || []).includes(to)) {
      this.select(null);
      this.onMove(d.from, to, false);
    }
  }
}

// a still board for the cards
function miniBoard(fen) {
  const pieces = parseFen(fen);
  const el = document.createElement("div");
  el.className = "mini";
  for (let r = 8; r >= 1; r--) {
    for (let f = 0; f < 8; f++) {
      const sq = FILES[f] + r;
      const d = document.createElement("div");
      d.style.background = (f + r) % 2 ? "var(--dark)" : "var(--light)";
      if (pieces[sq]) {
        const img = document.createElement("img");
        img.src = `data:image/svg+xml;utf8,${encodeURIComponent(PIECES[pieces[sq]])}`;
        d.appendChild(img);
      }
      el.appendChild(d);
    }
  }
  return el;
}

function confetti() {
  const canvas = $("#confetti");
  const ctx = canvas.getContext("2d");
  canvas.width = innerWidth;
  canvas.height = innerHeight;
  const colors = ["#81b64c", "#f4b400", "#3692e7", "#e8e6e3", "#d64f3a"];
  const bits = Array.from({ length: 140 }, () => ({
    x: innerWidth / 2 + (Math.random() - 0.5) * 300,
    y: innerHeight / 2,
    vx: (Math.random() - 0.5) * 16,
    vy: -Math.random() * 16 - 4,
    r: Math.random() * 6 + 3,
    c: colors[Math.floor(Math.random() * colors.length)],
    a: Math.random() * Math.PI,
  }));
  let frames = 0;
  (function tick() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const b of bits) {
      b.x += b.vx;
      b.y += b.vy;
      b.vy += 0.5;
      b.a += 0.2;
      ctx.fillStyle = b.c;
      ctx.save();
      ctx.translate(b.x, b.y);
      ctx.rotate(b.a);
      ctx.fillRect(-b.r, -b.r / 2, b.r * 2, b.r);
      ctx.restore();
    }
    if (++frames < 110) requestAnimationFrame(tick);
    else ctx.clearRect(0, 0, canvas.width, canvas.height);
  })();
}

let toastTimer = null;
function toast(text) {
  const t = $("#toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 1800);
}

// ---------------------------------------------------------------- state

const S = {
  catalog: [],
  filter: "all",
  opening: null, // {family, color, root, nodes, progress}
  color: "white",
  node: 0,
  mode: "explore", // learn, drill, explore
  leaf: null,
  mistakes: 0,
  tries: 0,
  score: 0,
  streak: 0,
  timer: null,
  open: new Set(),
  pick: 0, // the book move ↑/↓ points at
  extra: [], // moves played past the book: {uci, san, fen, check}
  redo: [], // the ones ◀ took back, for ▶
  tab: "analysis",
  engineOn: true,
  db: "lichess",
  ratings: "1600,1800,2000,2200,2500",
  an: { fen: null }, // what's known of the position shown
  hover: null, // the explorer move the mouse is over
  anTimer: null,
};

let board;

function nodes() {
  return S.opening.nodes;
}

function node(id) {
  return S.opening.nodes[id];
}

function pathOf(id) {
  const out = [];
  for (let n = node(id); n.parent !== null; n = node(n.parent)) out.push(n.id);
  return out.reverse();
}

function leaves(top = S.opening.root) {
  return node(top).leaves.map(node);
}

function prepare(opening) {
  // the lines under each node, in the order of its branches
  const all = opening.nodes;
  for (let i = all.length - 1; i >= 0; i--) {
    const n = all[i];
    n.leaves = n.children.length ? n.children.flatMap((c) => all[c].leaves) : [n.id];
  }
  // a position reached by another move order is still the book's
  opening.index = {};
  for (const n of all) opening.index[epd(n.fen)] ??= n.id;
}

function epd(fen) {
  return fen.split(" ").slice(0, 4).join(" ");
}

// the position shown: a book node, or past it
function curFen() {
  return S.extra.length ? S.extra[S.extra.length - 1].fen : node(S.node).fen;
}

function key(leaf) {
  return `${S.color}:${S.opening.family}:${leaf.path}`;
}

function card(leaf) {
  return S.opening.progress[key(leaf)];
}

function bump(points) {
  S.score += points;
  $("#score").textContent = S.score;
  $("#streak").textContent = S.streak;
  $("#stats").classList.toggle("hot", S.streak >= 3);
}

// ---------------------------------------------------------------- home

async function showHome() {
  clearTimeout(S.timer);
  clearTimeout(S.anTimer);
  S.opening = null;
  $("#study").classList.add("hidden");
  $("#home").classList.remove("hidden");
  S.catalog = await api().catalog();
  renderCards();
  $("#search").focus();
}

function renderCards() {
  const words = searchWords($("#search").value);
  let list = S.catalog.map((o) => {
    const inName = words.every((w) => o.search.includes(w));
    const found = words.length && !inName
      ? o.variations.filter((v) => words.every((w) => fold(`${o.family} ${v}`).includes(w)))
      : [];
    return { o, inName, found };
  }).filter(({ inName, found }) => inName || found.length);
  if (S.filter === "white" || S.filter === "black") list = list.filter(({ o }) => o.color === S.filter);
  if (S.filter === "started") list = list.filter(({ o }) => o.learned || o.due);
  list.sort((a, b) =>
    (b.inName - a.inName) || (b.o.due - a.o.due) || (b.o.learned - a.o.learned) || (b.o.lines - a.o.lines));
  const shown = list.slice(0, 60);
  $("#home-hint").textContent = shown.length
    ? `${list.length} opening${list.length === 1 ? "" : "s"}: pick one and learn it line by line, every variation. ` +
      "The ones you've started come first."
    : "Nothing by that name. Try its English name: bishop, sicilian, caro-kann, queen's gambit…";
  const cards = $("#cards");
  cards.innerHTML = "";
  for (const { o, found } of shown) {
    const c = document.createElement("div");
    c.className = "card";
    c.appendChild(miniBoard(o.fen));
    const pct = Math.round((100 * o.learned) / o.lines);
    c.insertAdjacentHTML(
      "beforeend",
      `<h3>${o.family}</h3><div class="moves">${o.eco} · ${o.moves}</div>
       <div class="row"><span>${o.lines} line${o.lines === 1 ? "" : "s"}</span>
         <span class="side ${o.color}">as ${o.color === "white" ? "White" : "Black"}</span></div>
       <div class="thin"><i style="width:${pct}%"></i></div>
       <div class="row"><span class="dim">${o.learned ? `${o.learned} learned` : "not started"}</span>
         ${o.due ? `<span class="due">${o.due} to review</span>` : ""}</div>`,
    );
    if (found.length) {
      const f = document.createElement("div");
      f.className = "found";
      for (const v of found.slice(0, 6)) {
        const b = document.createElement("button");
        b.textContent = v;
        b.title = "Open the opening on this variation";
        b.onclick = (e) => {
          e.stopPropagation();
          openOpening(o.family, v);
        };
        f.appendChild(b);
      }
      if (found.length > 6) f.insertAdjacentHTML("beforeend", `<span class="dim">+${found.length - 6}</span>`);
      c.appendChild(f);
    }
    c.onclick = () => openOpening(o.family);
    cards.appendChild(c);
  }
}

// ---------------------------------------------------------------- an opening

async function openOpening(family, variation = null) {
  S.opening = await api().opening(family);
  prepare(S.opening);
  S.color = S.opening.color;
  board.orientation = S.color;
  S.open = new Set();
  $("#home").classList.add("hidden");
  $("#study").classList.remove("hidden");
  $("#search").blur();
  const target = variation && nodes().find((n) => n.name === variation);
  if (target) explore(target.id);
  else nextLine();
}

function header() {
  const o = S.opening;
  const all = leaves();
  const learned = all.filter((l) => stars(card(l))).length;
  const due = all.filter((l) => isDue(card(l))).length;
  const root = node(o.root);
  $("#family").textContent = o.family;
  $("#sub").textContent = `${root.eco || ""} · ${movesText(o.root)}`;
  $("#color-btn").textContent = `as ${S.color === "white" ? "White" : "Black"} ⇄`;
  $("#bar i").style.width = `${(100 * learned) / all.length}%`;
  $("#progress-text").textContent = `${learned}/${all.length} lines learned${due ? ` · ${due} to review` : ""}`;
}

function movesText(id) {
  const out = [];
  for (const i of pathOf(id)) {
    const n = node(i);
    out.push(n.ply % 2 === 1 ? n.numbered : out.length ? n.san : n.numbered);
  }
  return out.join(" ");
}

function say(html, pop = true) {
  const m = $("#message");
  m.innerHTML = html;
  if (pop) {
    m.classList.remove("pop");
    m.getBoundingClientRect();
    m.classList.add("pop");
  }
}

function actions(list) {
  const box = $("#actions");
  box.innerHTML = "";
  for (const [label, fn, primary] of list) {
    const b = document.createElement("button");
    b.innerHTML = label;
    if (primary) b.className = "primary";
    b.onclick = fn;
    box.appendChild(b);
  }
}

function quest() {
  const modes = {
    learn: ["learn", "New line"],
    drill: ["drill", "From memory"],
    explore: ["explore", "Exploring"],
  };
  const [cls, label] = S.mode === "explore" && S.extra.length ? ["analysis", "Past the book"] : modes[S.mode];
  $("#quest").classList.toggle("compact", S.mode === "explore");
  let title = `<span class="mode ${cls}">${label}</span>`;
  if (S.leaf) {
    title += `<span>${S.leaf.label}</span>${starsHtml(stars(card(S.leaf)))}`;
  } else {
    title += `<span>${node(S.node).label || S.opening.family}</span>`;
  }
  $("#quest-title").innerHTML = title;
  const due = leaves().filter((l) => isDue(card(l))).length;
  const learn = ["▶ Next line <small>(n)</small>", nextLine, S.mode === "explore"];
  if (S.mode === "explore") {
    $("#quest-line").textContent =
      "Play any move: the book's, the games' or the engine's. ◀ takes it back.";
    actions([
      learn,
      [`🎯 Train the lines from here <small>(t)</small>`, trainHere],
      ...(due ? [[`🧠 Review ${due} due`, nextLine]] : []),
    ]);
  } else {
    $("#quest-line").textContent = S.mode === "learn"
      ? "Play the green arrows; the other side answers by itself. Then you play it from memory."
      : "Play the line without help. h shows the move (it counts as a slip).";
    actions([
      ["💡 Hint <small>(h)</small>", hint],
      ["⟲ Again <small>(r)</small>", again],
      ["🔍 Explore <small>(e)</small>", () => explore(S.node)],
    ]);
  }
}

// moving around

function go(id, { animate = true, sound: snd = true } = {}) {
  const prev = node(S.node);
  const prevFen = curFen();
  S.extra = [];
  S.redo = [];
  S.node = id;
  const n = node(id);
  const moved = n.parent === prev.id ? n.uci : null;
  board.set(n.fen, { last: n.uci, animate: animate && moved, check: n.check });
  if (snd && moved) playSound(prevFen, n.fen);
  S.pick = 0;
  updateMovable();
  renderMoves();
  renderTree();
}

function playSound(before, after) {
  sound.play(before.split(" ")[0].length > after.split(" ")[0].length ? "capture" : "move");
}

async function updateMovable() {
  const fen = curFen();
  board.setDests({});
  if (S.mode === "explore") board.movable = "both";
  else board.movable = !S.timer && turnOf(fen) === S.color ? S.color : null;
  const dests = await api().dests(fen);
  if (board.fen === fen) board.setDests(dests);
}

function renderMoves() {
  const box = $("#moves");
  box.innerHTML = "";
  const path = pathOf(S.node);
  for (const id of path) {
    const n = node(id);
    if (n.ply % 2 === 1) box.insertAdjacentHTML("beforeend", `<span class="num">${(n.ply + 1) / 2}.</span>`);
    const s = document.createElement("span");
    s.textContent = n.san;
    s.title = n.label;
    if (id === S.node) s.className = "cur";
    s.onclick = () => explore(id);
    box.appendChild(s);
  }
  S.extra.forEach((m, i) => {
    const ply = node(S.node).ply + i + 1;
    if (ply % 2 === 1) box.insertAdjacentHTML("beforeend", `<span class="num">${(ply + 1) / 2}.</span>`);
    else if (i === 0 && !path.length) box.insertAdjacentHTML("beforeend", `<span class="num">${ply / 2}…</span>`);
    const s = document.createElement("span");
    s.textContent = m.san;
    s.title = "past the book";
    s.className = `off${i === S.extra.length - 1 ? " cur" : ""}`;
    s.onclick = () => {
      while (S.extra.length > i + 1) S.redo.push(S.extra.pop());
      showPosition(false);
    };
    box.appendChild(s);
  });
  if (S.extra.length) for (const c of box.querySelectorAll("span.cur:not(.off)")) c.classList.remove("cur");
  if (!path.length && !S.extra.length) box.innerHTML = '<span class="dim">the starting position</span>';
}

function renderNext() {
  const box = $("#next");
  box.innerHTML = "";
  const n = node(S.node);
  const visible = S.mode === "explore";
  $("#next-box").classList.toggle("hidden", !visible);
  if (!visible) return;
  exploreArrows();
  if (S.extra.length) {
    box.innerHTML = '<div class="dim">Past the book: the Analysis tab goes on from here.</div>';
    return;
  }
  if (!n.children.length) {
    box.innerHTML = '<div class="dim">The end of this line. Play on: the Analysis tab goes on from here.</div>';
    return;
  }
  n.children.forEach((c, i) => {
    const child = node(c);
    const learned = leaves(c).filter((l) => stars(card(l))).length;
    const row = document.createElement("div");
    row.className = `next${i === S.pick ? " sel" : ""}`;
    const name = child.name || node(firstNamed(c)).label;
    row.innerHTML = `<b>${child.numbered}</b><span class="nm">${name}</span>` +
      `<span class="n">${child.size} line${child.size === 1 ? "" : "s"}${learned ? ` · ${learned}★` : ""}</span>`;
    row.onmouseenter = () => {
      S.pick = i;
      for (const [j, r] of [...box.children].entries()) r.classList.toggle("sel", j === i);
      exploreArrows();
    };
    row.onclick = () => go(c);
    box.appendChild(row);
  });
}

// the arrows while exploring: the book's moves (or the games' when past
// it), Stockfish's best, and the move under the mouse
function exploreArrows() {
  if (S.mode !== "explore") return;
  const n = node(S.node);
  const arrows = [];
  const arrow = (uci, color, width, opacity) =>
    arrows.push({ from: uci.slice(0, 2), to: uci.slice(2, 4), color, width, opacity });
  if (!S.extra.length && n.children.length) {
    const total = n.children.reduce((a, c) => a + node(c).size, 0);
    // the main branches only, and the one picked: twenty arrows hide the board
    n.children.forEach((c, i) => {
      if (i < 5 || i === S.pick) {
        arrow(node(c).uci, i === S.pick && !S.hover ? "hover" : "blue", 0.08 + 0.14 * (node(c).size / total),
          i === S.pick ? 0.9 : 0.7);
      }
    });
  } else if (S.an.fen === curFen() && S.an.exp && S.an.exp.moves) {
    for (const m of S.an.exp.moves.slice(0, 3)) arrow(m.uci, "gray", 0.06 + 0.16 * m.share, 0.75);
  }
  const best = S.an.fen === curFen() && S.an.lines && S.an.lines[0];
  if (best) arrow(best.uci, "engine", 0.13, 0.8);
  if (S.hover) arrow(S.hover, "hover", 0.16, 0.9);
  board.setArrows(arrows);
}

function firstNamed(id) {
  // the name a branch gets further on: its first named line
  const stack = [id];
  while (stack.length) {
    const n = node(stack.shift());
    if (n.name) return n.id;
    stack.push(...n.children);
  }
  return id;
}

// the tree: a row is a run of moves with no branch and no new name

function renderTree() {
  const box = $("#tree");
  const scroll = box.scrollTop;
  box.innerHTML = "";
  const onPath = new Set(pathOf(S.node));
  onPath.add(S.node);
  // the line being trained shows open, its end marked
  const target = S.leaf && S.mode !== "explore" ? S.leaf.id : null;
  if (target !== null) for (const id of pathOf(target)) onPath.add(id);
  const root = node(S.opening.root);
  const head = document.createElement("div");
  head.className = "trow on-path";
  head.innerHTML = `<span class="tog"></span>`;
  const mvs = document.createElement("span");
  mvs.className = "mvs";
  pathOf(root.id).forEach((id, i, all) => mvs.appendChild(moveSpan(id, all[i - 1])));
  head.appendChild(mvs);
  head.insertAdjacentHTML("beforeend", `<span class="tn">${S.opening.family}</span><span class="cnt">${leaves().length}</span>`);
  box.appendChild(head);
  const kids = document.createElement("div");
  for (const c of root.children) kids.appendChild(treeRow(c, onPath, 0, target));
  box.appendChild(kids);
  box.scrollTop = scroll;
  const cur = box.querySelector(".mv.cur");
  if (cur) {
    const b = box.getBoundingClientRect();
    const r = cur.getBoundingClientRect();
    if (r.top < b.top || r.bottom > b.bottom) cur.scrollIntoView({ block: "center" });
  }
}

function moveSpan(id, after = null) {
  const n = node(id);
  const s = document.createElement("span");
  s.className = `mv${id === S.node ? " cur" : ""}`;
  s.textContent = n.ply % 2 === 0 && after === n.parent ? n.san : n.numbered;
  s.onclick = (e) => {
    e.stopPropagation();
    explore(id);
  };
  return s;
}

function treeRow(start, onPath, depth, target) {
  const chain = [start];
  for (;;) {
    const last = node(chain[chain.length - 1]);
    if (last.children.length !== 1 || node(last.children[0]).name) break;
    chain.push(last.children[0]);
  }
  const end = node(chain[chain.length - 1]);
  const wrap = document.createElement("div");
  const row = document.createElement("div");
  const here = chain.some((id) => onPath.has(id));
  row.className = `trow${here ? " on-path" : ""}`;
  const branches = end.children.length;
  const open = S.open.has(end.id) || (here && branches) || (depth < 1 && branches && !S.open.has(-end.id));
  const tog = document.createElement("span");
  tog.className = "tog";
  tog.textContent = branches ? (open ? "▾" : "▸") : "";
  tog.onclick = () => {
    if (open) {
      S.open.delete(end.id);
      S.open.add(-end.id);
    } else {
      S.open.add(end.id);
      S.open.delete(-end.id);
    }
    renderTree();
  };
  row.appendChild(tog);
  const mvs = document.createElement("span");
  mvs.className = "mvs";
  chain.forEach((id, i) => mvs.appendChild(moveSpan(id, chain[i - 1])));
  row.appendChild(mvs);
  const named = [...chain].reverse().map(node).find((n) => n.name);
  const tn = document.createElement("span");
  tn.className = "tn";
  tn.textContent = (chain.includes(target) ? "🎯 " : "") + (named ? named.name : "");
  row.appendChild(tn);
  if (branches) {
    const all = leaves(end.id);
    const learned = all.filter((l) => stars(card(l))).length;
    row.insertAdjacentHTML("beforeend", `<span class="cnt">${learned ? `${learned}/` : ""}${all.length}</span>`);
  } else {
    row.insertAdjacentHTML("beforeend", starsHtml(stars(card(end))));
  }
  const goBtn = document.createElement("button");
  goBtn.className = "go";
  goBtn.textContent = "▶";
  goBtn.title = branches ? "Train the lines of this branch" : "Train this line";
  goBtn.onclick = (e) => {
    e.stopPropagation();
    if (branches) startLine(pick(leaves(end.id)));
    else startLine(end);
  };
  row.appendChild(goBtn);
  wrap.appendChild(row);
  if (branches && open) {
    const kids = document.createElement("div");
    kids.className = "tkids";
    for (const c of end.children) kids.appendChild(treeRow(c, onPath, depth + 1, target));
    wrap.appendChild(kids);
  }
  return wrap;
}

// ---------------------------------------------------------------- modes

function explore(id) {
  clearTimeout(S.timer);
  S.timer = null;
  S.mode = "explore";
  S.leaf = null;
  go(id, { animate: false, sound: false });
  header();
  quest();
  exploreInfo();
}

// the position past the book, after ◀/▶ or a click on its moves
function showPosition(animate) {
  const m = S.extra[S.extra.length - 1];
  const n = node(S.node);
  if (m) board.set(m.fen, { last: m.uci, animate: animate && m.uci, check: m.check });
  else board.set(n.fen, { last: n.uci, check: n.check });
  updateMovable();
  renderMoves();
  quest();
  exploreInfo();
}

function playOff(m, animate) {
  const before = curFen();
  const back = S.opening.index[epd(m.fen)];
  if (back !== undefined) {
    // another move order, back into the book
    go(back, { animate: false, sound: false });
    playSound(before, m.fen);
    toast(`Back in the book: ${node(back).label}`);
    quest();
    exploreInfo();
    return;
  }
  S.extra.push(m);
  S.redo = [];
  playSound(before, m.fen);
  showPosition(animate);
}

// a move from the explorer or the engine: the book's own when it is one
async function playUci(uci) {
  S.hover = null;
  const n = node(S.node);
  const book = !S.extra.length && n.children.map(node).find((c) => c.uci === uci);
  if (book) {
    go(book.id);
    exploreInfo();
    return;
  }
  const m = await api().move(curFen(), uci);
  if (m) playOff(m, true);
}

function exploreInfo() {
  const n = node(S.node);
  renderNext();
  showTabs();
  refreshAnalysis();
  if (S.extra.length) {
    say(`<b>${S.extra.length}</b> move${S.extra.length === 1 ? "" : "s"} past the book. ` +
      "What's played here and what the engine thinks is below.", false);
  } else if (!n.children.length) {
    say(`<span class="name">${n.label}</span>: the end of the book line. ` +
      "Play on: the games and the engine go further.", false);
  } else if (n.children.length === 1) {
    say(`Book: <b>${node(n.children[0]).numbered}</b>`, false);
  } else {
    say(`<b>${n.children.length}</b> book moves here, <b>${n.size}</b> lines in all.`, false);
  }
}

function pick(list) {
  const due = list.filter((l) => isDue(card(l)));
  if (due.length) return due.sort((a, b) => (card(a).due < card(b).due ? -1 : 1))[0];
  // new ones: the short lines first, the long ones build on them
  const fresh = list.filter((l) => !card(l));
  if (fresh.length) return fresh.reduce((a, b) => (b.ply < a.ply ? b : a));
  return list[Math.floor(Math.random() * list.length)];
}

function nextLine() {
  startLine(pick(leaves()));
}

function trainHere() {
  startLine(pick(leaves(S.node)));
}

function again() {
  if (S.leaf) startLine(S.leaf, "drill");
}

function startLine(leaf, mode = null) {
  clearTimeout(S.timer);
  clearTimeout(S.anTimer);
  S.timer = null;
  S.leaf = leaf;
  const c = card(leaf);
  S.mode = mode || (c && c.history ? "drill" : "learn");
  S.mistakes = 0;
  S.tries = 0;
  board.orientation = S.color;
  S.node = 0;
  S.extra = [];
  board.set(node(0).fen);
  renderNext();
  showTabs();
  header();
  quest();
  say(S.mode === "learn"
    ? `A new line: <span class="name">${leaf.label}</span>. Follow the green arrows.`
    : `From memory: <span class="name">${leaf.label}</span>. ${S.color === "white" ? "Your move." : ""}`);
  go(0, { animate: false, sound: false });
  advance();
}

function expected() {
  const path = pathOf(S.leaf.id);
  const n = node(S.node);
  return n.ply < path.length ? node(path[n.ply]) : null;
}

function advance() {
  const nxt = expected();
  if (!nxt) return finish();
  if (turnOf(node(S.node).fen) !== S.color) {
    board.movable = null;
    S.timer = setTimeout(reply, 550);
    return;
  }
  updateMovable();
  if (S.mode === "learn") {
    showHint(nxt);
  }
}

function showHint(nxt) {
  board.setArrows([{ from: nxt.uci.slice(0, 2), to: nxt.uci.slice(2, 4), color: "green", width: 0.2 }]);
}

function reply() {
  S.timer = null;
  const nxt = expected();
  go(nxt.id);
  if (nxt.name) say(`They answer <b>${nxt.san}</b>: now it's the <span class="name">${nxt.name}</span>`);
  else say(`They answer <b>${nxt.san}</b>.${S.mode === "learn" ? "" : " Your move."}`, false);
  advance();
}

async function finish() {
  board.movable = null;
  board.setArrows([]);
  if (S.mode === "learn") {
    sound.play("ok");
    say('<span class="ok">Line seen!</span> Now play it from memory: it starts again in a moment.');
    S.timer = setTimeout(() => startLine(S.leaf, "drill"), 1800);
    return;
  }
  const right = S.mistakes === 0;
  const k = key(S.leaf);
  const c = await api().answer(k, right);
  S.opening.progress[k] = c;
  const intervals = await api().intervals();
  if (right) {
    const bonus = 20 * (1 + stars(c));
    bump(bonus);
    sound.play("win");
    confetti();
    toast(`Perfect! +${bonus}`);
    say(`<span class="ok">Perfect!</span> +${bonus} ${starsHtml(stars(c))}<br>` +
      `<span class="dim">It comes back in ${intervals[c.box]} day${intervals[c.box] === 1 ? "" : "s"}.</span>`);
  } else {
    say(`<span class="warn">Done, with ${S.mistakes} slip${S.mistakes === 1 ? "" : "s"}.</span><br>` +
      '<span class="dim">It comes back tomorrow: try it once more now.</span>');
  }
  header();
  renderTree();
  actions([
    ["▶ Next line <small>(n)</small>", nextLine, right],
    ["⟲ Again <small>(r)</small>", again, !right],
    ["🔍 Explore on from here <small>(e)</small>", () => explore(S.node)],
  ]);
}

async function moved(from, to, clicked) {
  const n = node(S.node);
  const book = n.children.map(node).find((c) => c.uci.slice(0, 4) === from + to);
  if (S.mode === "explore") {
    if (book && !S.extra.length) {
      go(book.id, { animate: clicked });
      exploreInfo();
      return;
    }
    const m = await api().move(curFen(), from + to);
    if (m) playOff(m, clicked);
    return;
  }
  const nxt = expected();
  if (!nxt || S.timer) return;
  if (book && book.id === nxt.id) {
    S.tries = 0;
    S.streak++;
    bump(5 * (1 + Math.floor(Math.min(S.streak, 20) / 5)));
    board.setArrows([]);
    go(nxt.id, { animate: clicked });
    sound.play("ok");
    say(`<span class="ok">✔ ${nxt.san}</span>${nxt.name ? `: the <span class="name">${nxt.name}</span>` : ""}`);
    advance();
    return;
  }
  if (book) {
    const name = book.name || node(firstNamed(book.id)).label;
    say(`<span class="warn">${book.san}</span> is book too (<span class="name">${name}</span>), ` +
      "but this line goes another way.");
    board.mark({ [to]: "wrong" });
    return;
  }
  const m = await api().move(n.fen, from + to);
  if (!m) return;
  S.streak = 0;
  S.mistakes++;
  S.tries++;
  bump(0);
  sound.play("bad");
  board.mark({ [to]: "wrong" });
  if (S.tries >= 2 || S.mode === "learn") {
    showHint(nxt);
    say(`<span class="bad">✘ ${m.san}</span> isn't the move: the green arrow is.`);
  } else {
    say(`<span class="bad">✘ ${m.san}</span> isn't the move. Try again.`);
  }
}

function hint() {
  const nxt = S.leaf && S.mode !== "explore" ? expected() : null;
  if (!nxt || turnOf(node(S.node).fen) !== S.color) return;
  S.mistakes++;
  showHint(nxt);
  say(`Play <b>${nxt.san}</b> <span class="dim">(a hint counts as a slip)</span>`);
}

function switchColor() {
  S.color = S.color === "white" ? "black" : "white";
  board.orientation = S.color;
  toast(`Now you play ${S.color === "white" ? "White" : "Black"}`);
  nextLine();
}

// ---------------------------------------------------------------- analysis

// the tabs show while exploring; a line being trained keeps its tree
function showTabs() {
  const exploring = S.mode === "explore";
  $("#tabs").classList.toggle("hidden", !exploring);
  const tab = exploring ? S.tab : "tree";
  $("#tab-analysis").classList.toggle("hidden", tab !== "analysis");
  $("#tab-tree").classList.toggle("hidden", tab !== "tree");
  for (const b of document.querySelectorAll("#tabs .tab")) b.classList.toggle("on", b.dataset.tab === tab);
  $("#evalbar").classList.toggle("hidden", !exploring || !S.engineOn);
  if (!exploring) clearTimeout(S.anTimer);
}

function setTab(tab) {
  if (S.mode !== "explore") return;
  S.tab = tab;
  showTabs();
}

function toggleEngine() {
  if (!S.opening || S.mode !== "explore") return;
  S.engineOn = !S.engineOn;
  $("#engine-btn").classList.toggle("on", S.engineOn);
  S.an = { fen: null };
  showTabs();
  refreshAnalysis();
  exploreArrows();
}

function setDb(db) {
  if (!S.opening || S.mode !== "explore") return;
  S.db = db;
  for (const b of document.querySelectorAll("#an-tools [data-db]")) b.classList.toggle("on", b.dataset.db === db);
  $("#ratings").classList.toggle("hidden", db !== "lichess");
  S.an = { fen: null };
  refreshAnalysis();
}

// Lichess' winning chances, [-1, 1], for a white-POV score
function chances(cp) {
  const c = Math.max(-1000, Math.min(1000, cp));
  return 2 / (1 + Math.exp(-0.00368208 * c)) - 1;
}

function pov(cp, color) {
  return color === "white" ? cp : -cp;
}

function scoreBadge(line) {
  const neg = line.cp < 0 || (line.mate !== null && line.mate < 0);
  return `<span class="score${neg ? " neg" : ""}">${line.text}</span>`;
}

function verdict(line) {
  if (line.mate !== null) {
    return line.mate > 0 ? `White mates in ${line.mate}` : `Black mates in ${-line.mate}`;
  }
  const cp = line.cp;
  const who = cp > 0 ? "White" : "Black";
  const a = Math.abs(cp);
  if (a < 35) return "About equal";
  if (a < 90) return `${who} is slightly better`;
  if (a < 200) return `${who} is better`;
  if (a < 500) return `${who} is much better`;
  return `${who} is winning`;
}

function refreshAnalysis() {
  clearTimeout(S.anTimer);
  if (!S.opening || S.mode !== "explore") return;
  const fen = curFen();
  if (S.an.fen !== fen) S.an = { fen, exp: null, lines: null, judged: null, name: null, over: null };
  renderAnalysis();
  // a pause first: ← held down shouldn't ask Lichess for every position
  S.anTimer = setTimeout(() => runAnalysis(fen), 200);
}

async function runAnalysis(fen) {
  const A = S.an;
  const here = () => S.mode === "explore" && S.an === A && curFen() === fen;
  api().named(fen).then((n) => {
    if (here()) {
      A.name = n;
      renderAnalysis();
    }
  });
  const games = api().explorer(fen, S.db, S.ratings).then((d) => {
    if (here()) {
      A.exp = d;
      renderAnalysis();
    }
    return d;
  });
  if (!S.engineOn) return;
  let r = await api().analyse(fen, 0.4);
  if (!r || !here()) return;
  A.lines = r.lines;
  A.over = r.over;
  renderAnalysis();
  const d = await games;
  if (!here()) return;
  if (d && d.moves && d.moves.length) {
    // the engine's word on each move people play here, mistakes included
    const j = await api().analyse(fen, 1.2, d.moves.slice(0, 8).map((m) => m.uci));
    if (!j || !here()) return;
    A.judged = Object.fromEntries(j.lines.map((l) => [l.uci, l]));
    renderAnalysis();
  }
  r = await api().analyse(fen, 3);
  if (!r || !here()) return;
  A.lines = r.lines;
  renderAnalysis();
}

function compact(n) {
  if (n >= 1e6) return `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M`;
  if (n >= 1e4) return `${Math.round(n / 1e3)}k`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}k`;
  return String(n);
}

function pct(n, total) {
  return total ? Math.round((100 * n) / total) : 0;
}

function wdb(m) {
  const t = m.white + m.draws + m.black;
  const w = pct(m.white, t);
  const d = pct(m.draws, t);
  const bl = t ? 100 - w - d : 0;
  const label = (v) => (v >= 12 ? `${v}%` : "");
  return `<span class="wdb" title="White wins ${w}%, draws ${d}%, Black wins ${bl}%">` +
    `<i class="w" style="width:${w}%">${label(w)}</i><i class="d" style="width:${d}%">${label(d)}</i>` +
    `<i class="b" style="width:${bl}%">${label(bl)}</i></span>`;
}

// the mover's score in practice: wins and half the draws
function practice(m, color) {
  const t = m.white + m.draws + m.black;
  return t ? ((color === "white" ? m.white : m.black) + m.draws / 2) / t : 0;
}

// how much a move gives away next to the best one, for its mover
function loss(line, best, color) {
  return chances(pov(best.cp, color)) - chances(pov(line.cp, color));
}

function lossClass(l) {
  if (l >= 0.3) return "blunder";
  if (l >= 0.2) return "mistake";
  if (l >= 0.1) return "inacc";
  return "ok";
}

function mv(uci, san) {
  return `<span class="mv" data-uci="${uci}">${san}</span>`;
}

function renderAnalysis() {
  if (S.mode !== "explore") return;
  const A = S.an;
  const fen = curFen();
  const mover = turnOf(fen);
  const Mover = mover === "white" ? "White" : "Black";
  const yours = mover === S.color;
  const n = node(S.node);
  const exp = A.exp && !A.exp.error ? A.exp : null;
  const best = A.lines && A.lines[0];
  const judged = A.judged || {};
  const tips = [];

  // where we are
  const name = (exp && exp.opening && exp.opening.name) || (A.name && A.name.name);
  if (S.extra.length) {
    tips.push(["dim", `Past the book of ${S.opening.family}${name ? `, now in the <b>${name}</b>` : ""}.`]);
  }
  if (A.over) tips.push(["eval", `The game is over: ${A.over}.`]);
  if (best) {
    const after = best.reply ? `, ${best.reply} the answer` : "";
    tips.push(["eval", `${scoreBadge(best)} <b>${verdict(best)}</b>. The engine plays ${mv(best.uci, best.san)}${after}.`]);
  } else if (S.engineOn && !A.over) {
    tips.push(["dim", "Stockfish is thinking…"]);
  }
  if (exp && exp.total) {
    const where = S.db === "masters" ? "masters' games" : "Lichess games";
    const w = pct(exp.white, exp.total);
    const d = pct(exp.draws, exp.total);
    tips.push(["dim", `${compact(exp.total)} ${where} from here: White wins ${w}%, ${d}% draws, ` +
      `Black wins ${100 - w - d}%.`]);
  }
  if (exp && exp.moves.length) {
    const top = exp.moves[0];
    const engineTop = best && exp.moves.find((m) => m.uci === best.uci);
    if (best && top.uci === best.uci) {
      tips.push(["good", `The most played, ${mv(top.uci, top.san)} (${pct(top.games, exp.total)}%), is also the engine's choice.`]);
    } else if (best) {
      tips.push(["good", `Most played: ${mv(top.uci, top.san)} (${pct(top.games, exp.total)}%). ` +
        `The engine prefers ${mv(best.uci, best.san)}${engineTop ? ` (${pct(engineTop.games, exp.total)}% play it)` : ", hardly ever played"}.`]);
    }
    // what scores best for the mover, among moves with enough games
    const solid = exp.moves.filter((m) => m.games >= 100 && m.share >= 0.02);
    const scorer = solid.length > 1 && solid.reduce((a, b) => (practice(b, mover) > practice(a, mover) ? b : a));
    if (scorer && scorer.uci !== top.uci) {
      tips.push(["good", `${mv(scorer.uci, scorer.san)} scores best in practice: ` +
        `${Math.round(100 * practice(scorer, mover))}% for ${Mover} (${compact(scorer.games)} games).`]);
    }
    // traps: moves people play a lot that the engine refutes
    if (best) {
      for (const m of exp.moves) {
        const j = judged[m.uci];
        if (!j || m.share < 0.03 || m.games < 50) continue;
        const l = loss(j, best, mover);
        if (l < 0.2) continue;
        const share = `${pct(m.games, exp.total)}%`;
        if (yours) {
          tips.push(["avoid", `⚠ Avoid ${mv(m.uci, m.san)}: ${share} of players go for it, ` +
            `but ${j.reply ? `${j.reply} refutes it` : "it loses ground"} (${j.text}).`]);
        } else {
          tips.push(["trap", `🪤 A common mistake: ${mv(m.uci, m.san)}, played by ${share}. ` +
            `${j.reply ? `Punish it with ${j.reply}` : "The engine punishes it"} (${j.text}).`]);
        }
      }
    }
  } else if (exp) {
    tips.push(["dim", "No games from this position: you're on your own, with the engine."]);
  }
  if (A.exp && A.exp.error) tips.push(["avoid", A.exp.error]);

  const ul = $("#insights");
  ul.innerHTML = tips.map(([cls, html]) => `<li class="${cls}">${html}</li>`).join("");

  // the engine's lines
  const el = $("#engine-lines");
  if (!S.engineOn) {
    el.innerHTML = '<div class="xnote">Engine off (l)</div>';
  } else if (A.lines && A.lines.length) {
    el.innerHTML = `<div class="who">Stockfish · depth ${A.lines[0].depth || "?"}</div>` + A.lines.map((l) =>
      `<div class="eline" data-uci="${l.uci}">${scoreBadge(l)}<span class="pv">${l.pv}</span></div>`).join("");
  } else {
    el.innerHTML = "";
  }

  // the moves played here
  const box = $("#explorer");
  if (!A.exp) {
    box.innerHTML = '<div class="xnote">Loading the games…</div>';
  } else if (!exp) {
    box.innerHTML = "";
  } else {
    const bookMoves = S.extra.length ? new Map() : new Map(n.children.map((c) => [node(c).uci, node(c)]));
    box.innerHTML = exp.moves.map((m) => {
      const j = judged[m.uci];
      const l = j && best ? loss(j, best, mover) : null;
      const badges = [
        bookMoves.has(m.uci) ? '<span class="badge" title="A line of this opening">📖</span>' : "",
        best && best.uci === m.uci ? '<span class="badge" title="The engine\'s choice">★</span>' : "",
        l !== null && l >= 0.2 && m.share >= 0.03 ? '<span class="badge" title="Played a lot, refuted by the engine">🪤</span>' : "",
      ].join("");
      const book = bookMoves.get(m.uci);
      const title = book ? (book.name || node(firstNamed(book.id)).label) : "";
      return `<div class="xrow${book ? " book" : ""}" data-uci="${m.uci}" title="${title}">` +
        `<span class="san">${m.san}${badges}</span>` +
        `<span class="num">${pct(m.games, exp.total)}%</span>` +
        `<span class="num">${compact(m.games)}</span>` +
        wdb(m) +
        `<span class="ev ${l === null ? "" : lossClass(l)}">${j ? j.text : ""}</span></div>`;
    }).join("") || '<div class="xnote">No games from here.</div>';
  }

  for (const e of document.querySelectorAll("#tab-analysis [data-uci]")) {
    e.onclick = () => playUci(e.dataset.uci);
    e.onmouseenter = () => {
      S.hover = e.dataset.uci;
      exploreArrows();
    };
    e.onmouseleave = () => {
      S.hover = null;
      exploreArrows();
    };
  }

  // the bar: White's share from the bottom (from the top when flipped)
  const bar = $("#evalbar");
  bar.classList.toggle("flip", board.orientation === "black");
  if (best) {
    const white = 50 + 50 * chances(best.cp);
    bar.querySelector("i").style.height = `${white}%`;
    const label = bar.querySelector("span");
    label.textContent = best.text.replace("+", "");
    const whiteUp = best.cp >= 0;
    // on the side of the one ahead, in a color that reads on it
    label.className = whiteUp === (board.orientation === "white") ? "low" : "high";
    label.style.color = whiteUp ? "#333" : "#ddd";
  } else if (!S.engineOn || A.over) {
    bar.querySelector("i").style.height = "50%";
    bar.querySelector("span").textContent = "";
  }
  exploreArrows();
}

// ---------------------------------------------------------------- keys

function nav(what) {
  if (!S.opening) return;
  const n = node(S.node);
  if (what === "flip") {
    board.orientation = board.orientation === "white" ? "black" : "white";
    board.render();
    if (S.mode === "explore") renderAnalysis();
    return;
  }
  if (what === "back" && S.mode === "explore" && S.extra.length) {
    S.redo.push(S.extra.pop());
    showPosition(false);
  } else if (what === "back" && n.parent !== null) explore(n.parent);
  else if (what === "start") explore(S.opening.root);
  else if (what === "forward" && S.mode === "explore" && S.redo.length) {
    const m = S.redo.pop();
    const before = curFen();
    S.extra.push(m);
    playSound(before, m.fen);
    showPosition(true);
  } else if (what === "forward" && !S.extra.length && n.children.length) {
    if (S.mode !== "explore") explore(S.node);
    go(n.children[S.pick] ?? n.children[0]);
    exploreInfo();
  } else if (what === "end") {
    let id = S.node;
    while (node(id).children.length) id = node(id).children[0];
    explore(id);
  }
}

document.addEventListener("keydown", (e) => {
  if (e.target === $("#search")) {
    if (e.key === "Enter") {
      const first = $("#cards .card");
      if (first) first.click();
    }
    if (e.key === "Escape") $("#search").value = "";
    if (e.key === "Escape" || e.key === "Enter") renderCards();
    return;
  }
  if (e.key === "Escape") {
    showHome();
    return;
  }
  if (!S.opening) {
    if (e.key.length === 1) $("#search").focus();
    return;
  }
  const n = node(S.node);
  const keys = {
    ArrowLeft: () => nav("back"),
    ArrowRight: () => nav("forward"),
    Home: () => nav("start"),
    End: () => nav("end"),
    ArrowDown: () => {
      if (S.mode === "explore" && !S.extra.length && n.children.length) {
        S.pick = (S.pick + 1) % n.children.length;
        renderNext();
      }
    },
    ArrowUp: () => {
      if (S.mode === "explore" && !S.extra.length && n.children.length) {
        S.pick = (S.pick - 1 + n.children.length) % n.children.length;
        renderNext();
      }
    },
    Enter: () => nav("forward"),
    f: () => nav("flip"),
    h: hint,
    n: nextLine,
    r: again,
    t: trainHere,
    e: () => explore(S.node),
    c: switchColor,
    l: toggleEngine,
    d: () => setDb(S.db === "lichess" ? "masters" : "lichess"),
    v: () => setTab(S.tab === "analysis" ? "tree" : "analysis"),
  };
  if (keys[e.key]) {
    e.preventDefault();
    keys[e.key]();
  }
});

// ---------------------------------------------------------------- start

window.addEventListener("pywebviewready", async () => {
  PIECES = await api().pieces();
  board = new Board($("#board"), moved);
  $("#search").addEventListener("input", renderCards);
  $("#home-btn").onclick = showHome;
  $("#color-btn").onclick = switchColor;
  $("#sound").onclick = () => {
    sound.on = !sound.on;
    $("#sound").textContent = sound.on ? "🔊" : "🔇";
  };
  for (const b of document.querySelectorAll("#filters .chip")) {
    b.onclick = () => {
      S.filter = b.dataset.filter;
      for (const x of document.querySelectorAll("#filters .chip")) x.classList.toggle("on", x === b);
      renderCards();
    };
  }
  for (const b of document.querySelectorAll("#controls button")) b.onclick = () => nav(b.dataset.nav);
  for (const b of document.querySelectorAll("#tabs .tab")) b.onclick = () => setTab(b.dataset.tab);
  for (const b of document.querySelectorAll("#an-tools [data-db]")) b.onclick = () => setDb(b.dataset.db);
  $("#engine-btn").onclick = toggleEngine;
  $("#ratings").onchange = () => {
    S.ratings = $("#ratings").value;
    $("#ratings").blur();
    S.an = { fen: null };
    refreshAnalysis();
  };
  window.addEventListener("resize", () => board.fen && board.render());
  $("#search").value = await api().initial();
  await showHome();
});
