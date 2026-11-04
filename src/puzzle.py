# Puzzles on the board: Lichess' (the daily one, or of a theme at a
# difficulty) or chess.com's; the replies are played for you. Lichess' are
# recorded on your account, rating included, as on the site: a wrong move,
# a hint or the solution makes it a failure
import io
import urllib.error
import urllib.parse

import chess
import chess.pgn
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Select, Static

from board import BoardView, legend
from common import get_json, lichess_token, open_url, post_json

THEMES = [
    ("any", "mix"),
    ("opening", "opening"),
    ("middlegame", "middlegame"),
    ("endgame", "endgame"),
    ("rook endgame", "rookEndgame"),
    ("pawn endgame", "pawnEndgame"),
    ("mate in 1", "mateIn1"),
    ("mate in 2", "mateIn2"),
    ("mate in 3", "mateIn3"),
    ("fork", "fork"),
    ("pin", "pin"),
    ("skewer", "skewer"),
    ("discovered attack", "discoveredAttack"),
    ("hanging piece", "hangingPiece"),
    ("defensive move", "defensiveMove"),
    ("exposed king", "exposedKing"),
    ("kingside attack", "kingsideAttack"),
    ("sacrifice", "sacrifice"),
    ("deflection", "deflection"),
    ("quiet move", "quietMove"),
]
DIFFICULTIES = ["easiest", "easier", "normal", "harder", "hardest"]


def lichess(daily, theme, difficulty):
    if daily:
        url = "https://lichess.org/api/puzzle/daily"
    else:
        q = {"angle": theme, "difficulty": difficulty}
        url = "https://lichess.org/api/puzzle/next?" + urllib.parse.urlencode(q)
    data = get_json(url, token=lichess_token())
    board = chess.Board()
    for san in data["game"]["pgn"].split():
        board.push_san(san)
    p = data["puzzle"]
    return {
        "id": p["id"],
        "board": board,
        "solution": [chess.Move.from_uci(m) for m in p["solution"]],
        "about": f"Lichess puzzle, rated {p['rating']}",
        # told once it's over: they give the answer away
        "themes": ", ".join(p["themes"]),
        "url": f"https://lichess.org/training/{p['id']}",
    }


def chesscom(daily):
    url = "https://api.chess.com/pub/puzzle" + ("" if daily else "/random")
    data = get_json(url)
    game = chess.pgn.read_game(io.StringIO(data["pgn"]))
    return {
        "id": None,
        "board": game.board(),
        "solution": list(game.mainline_moves()),
        "about": f"chess.com: {data['title']}",
        "themes": "",
        "url": data["url"],
    }


def record(puzzle_id, win, angle):
    token = lichess_token()
    if not token:
        return "not recorded on Lichess: no token"
    try:
        res = post_json(
            f"https://lichess.org/api/puzzle/batch/{angle}",
            {"solutions": [{"id": puzzle_id, "win": win, "rated": True}]},
            token,
        )
    except urllib.error.HTTPError as e:
        return f"not recorded on Lichess: HTTP {e.code}"
    diff = next((r.get("ratingDiff") for r in res.get("rounds", [])), None)
    return f"rating {diff:+d}" if diff is not None else "recorded on Lichess"


class PuzzleScreen(Screen):
    BINDINGS = [
        Binding("h", "hint", "hint"),
        Binding("s", "solution", "solution"),
        Binding("n", "next", "next puzzle"),
        Binding("w", "web", "open it"),
        Binding("escape", "app.pop_screen", "back"),
    ]
    CSS = """
    #left { width: 3fr; }
    #side { width: 2fr; padding: 0 1; }
    #title { text-style: bold; }
    #choose { height: auto; }
    #choose Select { width: 1fr; }
    #about { margin: 1 0; }
    #status { min-height: 3; }
    """

    def __init__(self, site="lichess", theme="mix", difficulty="normal", daily=True):
        super().__init__()
        self.site = site
        self.theme = theme
        self.difficulty = difficulty
        self.daily = daily
        self.solved = self.tried = 0
        self.puzzle = None

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="left"):
                yield BoardView(id="board")
                yield Static(legend(["last", "hint", "wrong", "selected"]))
            with Vertical(id="side"):
                yield Static(id="title")
                if self.site == "lichess":
                    with Horizontal(id="choose"):
                        yield Select(
                            THEMES, value=self.theme, allow_blank=False, id="theme"
                        )
                        yield Select(
                            [(d, d) for d in DIFFICULTIES],
                            value=self.difficulty,
                            allow_blank=False,
                            id="difficulty",
                        )
                yield Static(id="about")
                yield Static(id="status")
        yield Footer()

    def on_mount(self):
        self.view = self.query_one(BoardView)
        self.update_title()
        self.fetch()

    def on_select_changed(self, event):
        if event.select.id == "theme":
            self.theme = event.value
        else:
            self.difficulty = event.value

    def say(self, text):
        self.query_one("#status").update(text)

    def update_title(self):
        what = "daily puzzle" if self.daily else "puzzles"
        self.query_one("#title").update(
            f"{'Lichess' if self.site == 'lichess' else 'chess.com'} {what}   "
            f"solved [green b]{self.solved}[/green b] of {self.tried}"
        )

    @work(thread=True, exclusive=True, group="fetch")
    def fetch(self):
        self.app.call_from_thread(self.say, "[dim]fetching...[/dim]")
        try:
            if self.site == "lichess":
                p = lichess(self.daily, self.theme, self.difficulty)
            else:
                p = chesscom(self.daily)
        except (urllib.error.URLError, KeyError) as e:
            self.app.call_from_thread(self.say, f"[red]couldn't fetch it: {e}[/red]")
            return
        self.app.call_from_thread(self.start, p)

    def start(self, p):
        self.puzzle = p
        self.i = 0
        self.failed = False
        self.over = False
        self.board = p["board"].copy()
        self.me = self.board.turn
        self.view.flipped = self.me == chess.BLACK
        self.view.player = {self.me}
        self.view.show(self.board.copy())
        self.query_one("#about").update(p["about"])
        self.say(f"[b]{'White' if self.me else 'Black'} to play[/b]: find the best move")
        self.update_title()

    def expected(self):
        return self.puzzle["solution"][self.i]

    def on_board_view_moved(self, event):
        if not self.puzzle or self.over:
            return
        move = event.move
        expected = self.expected()
        san = self.board.san(move)
        after = self.board.copy()
        after.push(move)
        # any mate solves it, not only the one in the solution
        if move != expected and not after.is_checkmate():
            self.failed = True
            self.view.mark({move.to_square: "wrong"})
            self.say(f"[red]✘ {san}[/red] isn't it, try again")
            return
        self.board = after
        self.view.show(self.board.copy())
        self.i += 1
        if self.board.is_checkmate() or self.i >= len(self.puzzle["solution"]):
            return self.finish()
        self.say(f"[green]✔ {san}[/green]")
        self.view.player = set()
        self.set_timer(0.5, self.reply)

    def reply(self):
        move = self.expected()
        san = self.board.san(move)
        self.board.push(move)
        self.i += 1
        self.view.show(self.board.copy())
        self.view.player = {self.me}
        self.say(f"They answer [b]{san}[/b]: your move")
        if self.i >= len(self.puzzle["solution"]):
            self.finish()

    def finish(self):
        self.over = True
        self.view.player = set()
        self.tried += 1
        self.solved += not self.failed
        head = (
            "[green b]Solved![/green b]"
            if not self.failed
            else "[yellow]Done, not clean[/yellow]"
        )
        themes = f"\n[dim]{self.puzzle['themes']}[/dim]" if self.puzzle["themes"] else ""
        self.say(f"{head}  [dim]n: next puzzle[/dim]{themes}")
        self.update_title()
        if self.puzzle["id"]:
            self.send(self.puzzle["id"], not self.failed)

    @work(thread=True, group="record")
    def send(self, puzzle_id, win):
        note = record(puzzle_id, win, self.theme if not self.daily else "mix")
        self.app.call_from_thread(self.notify, note)

    def action_hint(self):
        if self.puzzle and not self.over:
            self.failed = True
            sq = self.expected().from_square
            self.view.mark({sq: "hint"})
            piece = chess.piece_name(self.board.piece_type_at(sq))
            self.say(f"The {piece} on {chess.square_name(sq)}")

    def action_solution(self):
        if not self.puzzle or self.over:
            return
        self.failed = True
        b = self.board.copy()
        line = " ".join(b.san_and_push(m) for m in self.puzzle["solution"][self.i:])
        m = self.expected()
        self.view.mark({m.from_square: "hint", m.to_square: "hint"})
        self.say(f"Solution: [b]{line}[/b]\n[dim]play it to go on[/dim]")

    def action_next(self):
        # left after a wrong move it's failed, as on the site; untried, nothing
        if self.puzzle and not self.over and self.failed and self.puzzle["id"]:
            self.send(self.puzzle["id"], False)
        self.daily = False
        self.puzzle = None
        self.fetch()

    def action_web(self):
        if self.puzzle:
            open_url(self.puzzle["url"])
