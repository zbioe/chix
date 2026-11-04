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
    const colors = { green: "#15781b", blue: "#003088", hover: "#3692e7", red: "#882020" };
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
  const [cls, label] = modes[S.mode];
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
      "Walk the variations: play a book move on the board, click one below or in the tree.";
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
  S.node = id;
  const n = node(id);
  const moved = n.parent === prev.id ? n.uci : null;
  board.set(n.fen, { last: n.uci, animate: animate && moved, check: n.check });
  if (snd && moved) sound.play(prev.fen.split(" ")[0].length > n.fen.split(" ")[0].length ? "capture" : "move");
  S.pick = 0;
  updateMovable();
  renderMoves();
  renderTree();
}

async function updateMovable() {
  const n = node(S.node);
  if (S.mode === "explore") board.movable = "both";
  else board.movable = !S.timer && turnOf(n.fen) === S.color ? S.color : null;
  const fen = n.fen;
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
  if (!path.length) box.innerHTML = '<span class="dim">the starting position</span>';
}

function renderNext() {
  const box = $("#next");
  box.innerHTML = "";
  const n = node(S.node);
  const visible = S.mode === "explore";
  $("#next-box").classList.toggle("hidden", !visible);
  if (!visible) return;
  if (!n.children.length) {
    box.innerHTML = '<div class="dim">The end of this line. ◀ to go back, or train it.</div>';
    board.setArrows([]);
    return;
  }
  const total = n.children.reduce((a, c) => a + node(c).size, 0);
  // the main branches only, and the one picked: twenty arrows hide the board
  const arrows = n.children.map((c, i) => [c, i]).filter(([, i]) => i < 5 || i === S.pick).map(([c, i]) => {
    const m = node(c).uci;
    return { from: m.slice(0, 2), to: m.slice(2, 4), color: i === S.pick ? "hover" : "blue",
      width: 0.08 + 0.14 * (node(c).size / total), opacity: i === S.pick ? 0.9 : 0.7 };
  });
  board.setArrows(arrows);
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
      renderNext();
    };
    row.onclick = () => go(c);
    box.appendChild(row);
  });
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

function exploreInfo() {
  const n = node(S.node);
  renderNext();
  if (!n.children.length) {
    say(`<span class="name">${n.label}</span>: the end of this line.`, false);
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
  S.timer = null;
  S.leaf = leaf;
  const c = card(leaf);
  S.mode = mode || (c && c.history ? "drill" : "learn");
  S.mistakes = 0;
  S.tries = 0;
  board.orientation = S.color;
  S.node = 0;
  board.set(node(0).fen);
  renderNext();
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
    ["🔍 Explore <small>(e)</small>", () => explore(S.node)],
  ]);
}

async function moved(from, to, clicked) {
  const n = node(S.node);
  const book = n.children.map(node).find((c) => c.uci.slice(0, 4) === from + to);
  if (S.mode === "explore") {
    if (book) {
      go(book.id, { animate: clicked });
      exploreInfo();
      return;
    }
    const m = await api().move(n.fen, from + to);
    if (!m) return;
    board.mark({ [to]: "wrong" });
    sound.play("bad");
    say(`<span class="bad">${m.san}</span> isn't a line of this opening. The blue arrows are.`);
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

// ---------------------------------------------------------------- keys

function nav(what) {
  if (!S.opening) return;
  const n = node(S.node);
  if (what === "flip") {
    board.orientation = board.orientation === "white" ? "black" : "white";
    board.render();
    return;
  }
  if (what === "back" && n.parent !== null) explore(n.parent);
  else if (what === "start") explore(S.opening.root);
  else if (what === "forward" && n.children.length) {
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
      if (S.mode === "explore" && n.children.length) {
        S.pick = (S.pick + 1) % n.children.length;
        renderNext();
      }
    },
    ArrowUp: () => {
      if (S.mode === "explore" && n.children.length) {
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
  window.addEventListener("resize", () => board.fen && board.render());
  $("#search").value = await api().initial();
  await showHome();
});
