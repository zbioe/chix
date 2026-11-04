# What the chess tools share: the engines (CHESS_ENGINES, from
# pkgs/chess-engines), the HTTP calls and the Lichess opening explorer
import json
import os
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import chess
import chess.engine

AGENT = "dotnix-chess"
EXPLORER = "https://explorer.lichess.ovh"
ENGINES = json.loads(Path(os.environ["CHESS_ENGINES"]).read_text())
CHESS_DIR = Path(os.environ["CHESS_DIR"])

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
        # the screens ask from worker threads: one search at a time
        self.lock = threading.Lock()

    def limit(self):
        if is_maia(self.name):
            return chess.engine.Limit(nodes=1)
        return chess.engine.Limit(time=self.seconds)

    def analyse(self, board, multipv=None):
        with self.lock:
            return self.uci.analyse(board, self.limit(), multipv=multipv)

    def quit(self):
        self.uci.quit()


def open_url(url):
    subprocess.Popen(
        ["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def score_text(score):
    s = score.white()
    if s.is_mate():
        return f"#{s.mate()}"
    return f"{s.score() / 100:+.2f}"


class ExplorerError(Exception):
    pass


class Explorer:
    """The moves played from a position: Lichess' games of some ratings,
    the masters' or a player's (as a color)."""

    def __init__(self, db="lichess", ratings="1600,1800,2000,2200,2500",
                 speeds="blitz,rapid,classical", player=None, color="white"):
        self.db = db
        self.ratings = ratings
        self.speeds = speeds
        self.player = player
        self.color = color
        self.cache = {}

    def describe(self):
        if self.db == "player":
            return f"{self.player}'s games as {self.color}"
        if self.db == "lichess":
            return f"Lichess {self.speeds.replace(',', ' ')}, rated {self.ratings.replace(',', ' ')}"
        return "masters"

    def query(self, board, moves=15):
        token = lichess_token()
        if not token:
            raise ExplorerError(
                "the explorer needs the Lichess token: dotnix.games.chess.lichess.enable"
            )
        params = {"fen": board.fen(), "moves": moves, "topGames": 0, "recentGames": 0}
        if self.db == "lichess":
            params |= {"speeds": self.speeds, "ratings": self.ratings}
        elif self.db == "player":
            params |= {"player": self.player, "color": self.color}
        key = (self.db, self.ratings, self.player, self.color, board.fen(), moves)
        if key not in self.cache:
            url = f"{EXPLORER}/{self.db}?{urllib.parse.urlencode(params)}"
            try:
                lines = get(url, token=token).strip().splitlines()
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    raise ExplorerError("Lichess asks to wait a minute (429)") from e
                raise ExplorerError(f"explorer: HTTP {e.code}") from e
            except urllib.error.URLError as e:
                raise ExplorerError(f"explorer: {e.reason}") from e
            # the player database streams updates: the last one is complete
            self.cache[key] = json.loads(lines[-1])
        return self.cache[key]
