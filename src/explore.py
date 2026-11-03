# chess-explore [MOVES... | --fen FEN]: walk an opening through the Lichess
# explorer (every move played from the position, with its results) and an
# engine; `tree` lays out the main variations from where you are
import argparse
import json
import readline  # noqa: F401  line editing and history for input()
import subprocess
import sys
import urllib.error
import urllib.parse
from pathlib import Path

import chess
import chess.pgn

from common import (
    CHESS_DIR,
    ENGINES,
    Engine,
    clear,
    color,
    draw,
    get,
    lichess_token,
    line_san,
)

EXPLORER = "https://explorer.lichess.ovh"
HELP = """\
  MOVE          play it (e4, Nf3, e2e4) or the Nth move of the table (1, 2...)
  b [N]         back N moves (1)
  r             back to the start
  f             flip the board
  e             engine on or off
  engine NAME   another engine: {engines}
  t SECONDS     engine time per position
  db masters | lichess | player NAME [white|black]
                which games the explorer counts
  tree [DEPTH] [WIDTH]
                the variations from here: the WIDTH most played moves of
                each position, DEPTH moves deep (3 3)
  pgn           the line so far
  save [FILE]   add the line to FILE ($CHESS_DIR/repertoire.pgn)
  web           open the position on Lichess
  q             quit"""


class ExplorerError(Exception):
    pass


class Explorer:
    def __init__(self, args):
        self.db = args.db
        self.player = args.player
        self.color = args.color
        self.speeds = args.speeds
        self.ratings = args.ratings
        self.cache = {}

    def describe(self):
        if self.db == "player":
            return f"{self.player}'s games as {self.color}"
        if self.db == "lichess":
            return f"Lichess {self.speeds} {self.ratings}"
        return "masters"

    def query(self, board):
        token = lichess_token()
        if not token:
            raise ExplorerError(
                "the explorer needs a Lichess token: dotnix.games.chess.lichess.enable"
            )
        params = {"fen": board.fen(), "moves": 15, "topGames": 0, "recentGames": 0}
        if self.db == "lichess":
            params |= {"speeds": self.speeds, "ratings": self.ratings}
        elif self.db == "player":
            params |= {"player": self.player, "color": self.color}
        key = (self.db, self.player, self.color, board.fen())
        if key not in self.cache:
            url = f"{EXPLORER}/{self.db}?{urllib.parse.urlencode(params)}"
            try:
                lines = get(url, token=token).strip().splitlines()
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    raise ExplorerError("Lichess asks to wait a minute (429)") from e
                raise ExplorerError(f"explorer: HTTP {e.code}") from e
            # the player database streams updates: the last one is complete
            self.cache[key] = json.loads(lines[-1])
        return self.cache[key]


def percent(part, total):
    return round(100 * part / total) if total else 0


def bar(white, draws, black, width=24):
    total = white + draws + black
    if not total:
        return ""
    w = round(width * white / total)
    d = round(width * draws / total)
    return (
        color((240, 240, 240), "█" * w)
        + color((128, 128, 128), "█" * d)
        + color((40, 40, 40), "█" * (width - w - d))
    )


def score_text(score):
    s = score.white()
    if s.is_mate():
        return f"#{s.mate()}"
    return f"{s.score() / 100:+.2f}"


def results(m):
    n = m["white"] + m["draws"] + m["black"]
    return (
        n,
        f"{percent(m['white'], n)}/{percent(m['draws'], n)}/{percent(m['black'], n)}",
    )


class Session:
    def __init__(self, args, board):
        self.explorer = Explorer(args)
        self.board = board
        self.start = board.root()
        self.flipped = False
        self.engine_on = True
        self.engine = Engine(args.engine, args.time)
        self.moves = []
        self.opening = None

    def analyse(self):
        if not self.engine_on or self.board.is_game_over():
            return []
        return self.engine.analyse(self.board, multipv=3)

    def show(self):
        clear()
        print(draw(self.board, self.flipped))
        try:
            data = self.explorer.query(self.board)
        except ExplorerError as e:
            data = None
            print(f"\n  {e}")
        if data:
            self.opening = data.get("opening") or self.opening
            total = data["white"] + data["draws"] + data["black"]
            name = (
                f"{self.opening['eco']} {self.opening['name']}" if self.opening else ""
            )
            print(f"\n  {name}")
            print(f"  {total:,} games, {self.explorer.describe()}\n")
            self.moves = [chess.Move.from_uci(m["uci"]) for m in data["moves"]]
            for i, m in enumerate(data["moves"], 1):
                n, wdb = results(m)
                print(
                    f"  {i:>2} {m['san']:<7} {percent(n, total):>3}% {n:>10,}  "
                    f"{bar(m['white'], m['draws'], m['black'])} {wdb:<9}"
                    f" {m.get('averageRating') or '':>5}"
                )
            if not data["moves"]:
                print("  out of book")
        lines = self.analyse()
        if lines:
            print(f"\n  {self.engine.name}", end="")
        for info in lines:
            pv = line_san(self.board, info.get("pv", []))
            print(f"\n  {score_text(info['score']):>6}  {pv}", end="")
        print("\n")

    def play(self, text):
        if text.isdigit():
            i = int(text) - 1
            if not 0 <= i < len(self.moves):
                raise ValueError(f"no move {text} in the table")
            self.board.push(self.moves[i])
            return
        try:
            self.board.push_san(text)
        except ValueError:
            try:
                self.board.push_uci(text)
            except ValueError:
                raise ValueError(f"not a move: {text}") from None

    def game(self):
        game = chess.pgn.Game()
        if self.start.fen() != chess.STARTING_FEN:
            game.setup(self.start)
        node = game
        for m in self.board.move_stack:
            node = node.add_variation(m)
        if self.opening:
            game.headers["Opening"] = self.opening["name"]
            game.headers["ECO"] = self.opening["eco"]
        game.headers["Event"] = "Repertoire"
        return game

    def tree(self, depth, width):
        def walk(board, level):
            if level == depth:
                return
            data = self.explorer.query(board)
            total = data["white"] + data["draws"] + data["black"]
            for m in data["moves"][:width]:
                n, wdb = results(m)
                num = f"{board.fullmove_number}{'.' if board.turn else '...'}"
                name = (m.get("opening") or {}).get("name", "")
                print(
                    f"{'  ' * level}{num}{m['san']:<6} {percent(n, total):>3}%  {wdb}  {name}"
                )
                board.push(chess.Move.from_uci(m["uci"]))
                walk(board, level + 1)
                board.pop()

        walk(self.board.copy(), 0)

    def command(self, text):
        cmd, *rest = text.split()
        if cmd == "q":
            raise EOFError
        if cmd in ("h", "?", "help"):
            print(HELP.format(engines=", ".join(sorted(ENGINES))))
            return False
        if cmd == "b":
            back = int(rest[0]) if rest else 1
            for _ in range(min(back, len(self.board.move_stack))):
                self.board.pop()
        elif cmd == "r":
            self.board = self.start.copy()
        elif cmd == "f":
            self.flipped = not self.flipped
        elif cmd == "e":
            self.engine_on = not self.engine_on
        elif cmd == "engine":
            if rest[0] not in ENGINES:
                raise ValueError(f"no engine {rest[0]}: {', '.join(sorted(ENGINES))}")
            seconds = self.engine.seconds
            self.engine.quit()
            self.engine = Engine(rest[0], seconds)
        elif cmd == "t":
            self.engine.seconds = float(rest[0])
        elif cmd == "db":
            self.explorer.db = rest[0]
            if rest[0] == "player":
                self.explorer.player = rest[1]
                self.explorer.color = rest[2] if len(rest) > 2 else "white"
        elif cmd == "tree":
            self.tree(int(rest[0]) if rest else 3, int(rest[1]) if len(rest) > 1 else 3)
            return False
        elif cmd == "pgn":
            print(self.game().accept(chess.pgn.StringExporter(headers=False)))
            return False
        elif cmd == "save":
            path = Path(rest[0]) if rest else CHESS_DIR / "repertoire.pgn"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as f:
                print(self.game(), file=f, end="\n\n")
            print(f"saved to {path}")
            return False
        elif cmd == "web":
            fen = self.board.fen().replace(" ", "_")
            subprocess.Popen(
                ["xdg-open", f"https://lichess.org/analysis/standard/{fen}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return False
        else:
            self.play(cmd)
        return True

    def run(self):
        redraw = True
        while True:
            if redraw:
                self.show()
            prompt = "white" if self.board.turn else "black"
            try:
                text = input(f"{prompt}> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not text:
                redraw = False
                continue
            try:
                redraw = self.command(text)
            except EOFError:
                break
            except (ValueError, IndexError, ExplorerError) as e:
                print(f"  {e or 'see h'}")
                redraw = False


def main():
    p = argparse.ArgumentParser(
        prog="chess-explore",
        description="Opening explorer: Lichess games plus an engine",
    )
    p.add_argument("moves", nargs="*", help="a line to start from: e4 e5 Nf3")
    p.add_argument("--fen", help="a position to start from")
    p.add_argument("--db", choices=["masters", "lichess", "player"], default="lichess")
    p.add_argument("--player", help="whose games, with --db player")
    p.add_argument("--color", choices=["white", "black"], default="white")
    p.add_argument("--speeds", default="blitz,rapid,classical")
    p.add_argument("--ratings", default="1800,2000,2200,2500")
    p.add_argument("--engine", default="stockfish", choices=sorted(ENGINES))
    p.add_argument(
        "--time", type=float, default=0.5, help="engine seconds per position"
    )
    p.add_argument(
        "--tree",
        nargs="*",
        type=int,
        metavar="N",
        help="print the tree (DEPTH WIDTH) and exit",
    )
    args = p.parse_args()
    if args.db == "player" and not args.player:
        p.error("--db player needs --player")

    board = chess.Board(args.fen) if args.fen else chess.Board()
    for m in args.moves:
        board.push_san(m)
    session = Session(args, board)
    try:
        if args.tree is not None:
            session.tree(*(args.tree or [3, 3]))
        else:
            session.run()
    except ExplorerError as e:
        sys.exit(f"chess-explore: {e}")
    finally:
        session.engine.quit()


if __name__ == "__main__":
    main()
