# What the chess tools share: the board in the terminal, the engines
# (CHESS_ENGINES, from pkgs/chess-engines) and the HTTP calls
import json
import os
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

import chess
import chess.engine

AGENT = "dotnix-chess"
ENGINES = json.loads(Path(os.environ["CHESS_ENGINES"]).read_text())
CHESS_DIR = Path(os.environ["CHESS_DIR"])

GLYPHS = dict(zip("kqrbnp", "♚♛♜♝♞♟"))
LIGHT, DARK = (240, 217, 181), (181, 136, 99)
LIGHT_LAST, DARK_LAST = (205, 210, 106), (170, 162, 58)


def lichess_token():
    path = os.environ.get("LICHESS_TOKEN_FILE")
    return Path(path).read_text().strip() if path else None


def request(url, accept="application/json", data=None, token=None):
    headers = {"User-Agent": AGENT, "Accept": accept}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = urllib.parse.urlencode(data).encode() if data else None
    return urllib.request.urlopen(
        urllib.request.Request(url, body, headers), timeout=120
    )


def get(url, accept="application/json", data=None, token=None):
    with request(url, accept, data, token) as r:
        return r.read().decode()


def post_json(url, payload, token):
    headers = {
        "User-Agent": AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, body, headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def get_json(url, **kw):
    return json.loads(get(url, **kw))


def color(rgb, text):
    r, g, b = rgb
    return f"\033[38;2;{r};{g};{b}m{text}\033[0m"


def draw(board, flipped=False):
    last = board.peek() if board.move_stack else None
    marked = {last.from_square, last.to_square} if last else set()
    ranks = range(8) if flipped else range(7, -1, -1)
    files = range(7, -1, -1) if flipped else range(8)
    rows = []
    for rank in ranks:
        row = f" {rank + 1} "
        for file in files:
            sq = chess.square(file, rank)
            light = (file + rank) % 2 == 1
            if sq in marked:
                r, g, b = LIGHT_LAST if light else DARK_LAST
            else:
                r, g, b = LIGHT if light else DARK
            piece = board.piece_at(sq)
            cell = " "
            if piece:
                fg = "\033[1;97m" if piece.color else "\033[1;30m"
                cell = f"{fg}{GLYPHS[piece.symbol().lower()]}"
            row += f"\033[48;2;{r};{g};{b}m {cell} \033[0m"
        rows.append(row)
    rows.append("    " + "  ".join("abcdefgh"[f] for f in files))
    return "\n".join(rows)


def clear():
    print("\033[2J\033[H", end="")


def line_san(board, moves, limit=8):
    b = board.copy()
    out = []
    for m in moves[:limit]:
        if b.turn:
            out.append(f"{b.fullmove_number}.{b.san(m)}")
        else:
            out.append(f"{'' if out else f'{b.fullmove_number}...'}{b.san(m)}")
        b.push(m)
    return " ".join(out)


def is_maia(name):
    return name.startswith("maia-")


class Engine:
    """A UCI engine by name; Maia plays from its policy alone (one node)."""

    def __init__(self, name, seconds):
        if name not in ENGINES:
            raise SystemExit(f"no engine {name}: {', '.join(sorted(ENGINES))}")
        self.name = name
        self.seconds = seconds
        # lc0 talks a lot on stderr
        self.uci = chess.engine.SimpleEngine.popen_uci(
            ENGINES[name], stderr=subprocess.DEVNULL
        )
        cores = os.cpu_count() or 2
        options = {"Threads": max(1, cores // 2), "Hash": 512}
        self.uci.configure({k: v for k, v in options.items() if k in self.uci.options})

    def limit(self):
        if is_maia(self.name):
            return chess.engine.Limit(nodes=1)
        return chess.engine.Limit(time=self.seconds)

    def analyse(self, board, multipv=None):
        return self.uci.analyse(board, self.limit(), multipv=multipv)

    def quit(self):
        self.uci.quit()
