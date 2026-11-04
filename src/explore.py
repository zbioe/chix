# The opening explorer: every move played from the position (Lichess' games,
# the masters' or a player's), with its results, next to an engine's best
# lines. Click a move on the board or in the table to go on
import chess
import chess.pgn
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static

import analysis as an
from board import BoardView, EvalBar, legend
from common import CHESS_DIR, Explorer, ExplorerError, line_san, open_url, score_text

DBS = ["lichess", "masters", "player"]


def wdb_bar(m, width=10):
    total = m["white"] + m["draws"] + m["black"]
    text = Text()
    if not total:
        return text
    w = round(width * m["white"] / total)
    d = round(width * m["draws"] / total)
    text.append("█" * w, style="grey93")
    text.append("█" * d, style="grey50")
    text.append("█" * (width - w - d), style="grey15")
    pct = lambda n: round(100 * n / total)  # noqa: E731
    text.append(f" {pct(m['white'])}/{pct(m['draws'])}/{pct(m['black'])}", style="dim")
    return text


class ExploreScreen(Screen):
    BINDINGS = [
        Binding("left", "back", "back", priority=True),
        Binding("home", "start", "start", priority=True),
        Binding("f", "flip", "flip"),
        Binding("e", "engine", "engine on/off"),
        Binding("d", "db", "games: lichess/masters/you"),
        Binding("s", "save", "save line"),
        Binding("w", "web", "lichess"),
        Binding("escape", "app.pop_screen", "back"),
    ]
    CSS = """
    #left { width: 3fr; }
    #side { width: 2fr; padding: 0 1; }
    #name { text-style: bold; }
    #moves { height: 1fr; }
    #engine { height: auto; min-height: 4; border-top: solid $primary-darken-2; }
    """

    def __init__(self, board=None, engine="stockfish", user=None):
        super().__init__()
        self.start = (board or chess.Board()).copy()
        self.position = self.start.copy()
        self.engine_name = engine
        self.engine_on = True
        self.explorer = Explorer()
        self.user = user
        self.opening = None
        self.rows = []

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield EvalBar(id="eval")
            with Vertical(id="left"):
                yield BoardView(self.position.copy(), player=(chess.WHITE, chess.BLACK))
                yield Static(legend(["last", "best", "selected"]))
            with Vertical(id="side"):
                yield Static(id="name")
                yield Static(id="db")
                yield DataTable(id="moves", cursor_type="row", zebra_stripes=True)
                yield Static(id="engine")
        yield Footer()

    def on_mount(self):
        table = self.query_one(DataTable)
        table.add_columns("move", "played", "games", "white / draw / black", "rating")
        self.board = self.query_one(BoardView)
        self.refresh_all()

    def refresh_all(self):
        self.board.show(self.position.copy())
        self.query_one("#db").update(f"[dim]{self.explorer.describe()}[/dim]")
        self.load_moves(self.position.copy())
        self.load_engine(self.position.copy())

    @work(thread=True, exclusive=True, group="explorer")
    def load_moves(self, board):
        try:
            data = self.explorer.query(board)
        except ExplorerError as e:
            self.app.call_from_thread(self.show_moves, board, None, str(e))
            return
        self.app.call_from_thread(self.show_moves, board, data, None)

    def show_moves(self, board, data, error):
        if board.fen() != self.position.fen():
            return
        table = self.query_one(DataTable)
        table.clear()
        self.rows = []
        if error:
            self.query_one("#name").update(f"[red]{error}[/red]")
            return
        self.opening = data.get("opening") or self.opening
        total = data["white"] + data["draws"] + data["black"]
        name = f"{self.opening['eco']} {self.opening['name']}" if self.opening else ""
        self.query_one("#name").update(f"{name}\n[dim]{total:,} games[/dim]")
        for m in data["moves"]:
            n = m["white"] + m["draws"] + m["black"]
            table.add_row(
                Text(m["san"], style="bold"),
                f"{round(100 * n / total) if total else 0}%",
                f"{n:,}",
                wdb_bar(m),
                str(m.get("averageRating") or ""),
            )
            self.rows.append(chess.Move.from_uci(m["uci"]))
        if not data["moves"]:
            table.add_row("out of book", "", "", "", "")

    @work(thread=True, exclusive=True, group="engine")
    def load_engine(self, board):
        if not self.engine_on or board.is_game_over():
            self.app.call_from_thread(self.show_engine, board, None)
            return
        lines = self.app.engine(self.engine_name).analyse(board, multipv=3)
        self.app.call_from_thread(self.show_engine, board, lines)

    def show_engine(self, board, lines):
        if board.fen() != self.position.fen():
            return
        bar = self.query_one(EvalBar)
        bar.flipped = self.board.flipped
        if not lines:
            bar.set(None, "")
            self.query_one("#engine").update("[dim]engine off (e)[/dim]")
            return
        cp = an.cp_of(lines[0]["score"].white())
        bar.set(cp, score_text(lines[0]["score"]))
        out = [f"[b]{self.engine_name}[/b]"]
        for info in lines:
            pv = line_san(board, info.get("pv", []))
            out.append(f"[b]{score_text(info['score']):>6}[/b]  {pv}")
        self.query_one("#engine").update("\n".join(out))
        best = (lines[0].get("pv") or [None])[0]
        if best:
            self.board.mark({best.from_square: "best", best.to_square: "best"})

    def play(self, move):
        self.position.push(move)
        self.refresh_all()

    def on_board_view_moved(self, event):
        self.play(event.move)

    def on_data_table_row_selected(self, event):
        i = event.cursor_row
        if 0 <= i < len(self.rows):
            self.play(self.rows[i])

    def action_back(self):
        if len(self.position.move_stack) > len(self.start.move_stack):
            self.position.pop()
            self.refresh_all()

    def action_start(self):
        self.position = self.start.copy()
        self.refresh_all()

    def action_flip(self):
        self.board.flip()
        self.query_one(EvalBar).flipped = self.board.flipped
        self.query_one(EvalBar).refresh()

    def action_engine(self):
        self.engine_on = not self.engine_on
        self.load_engine(self.position.copy())

    def action_db(self):
        dbs = DBS if self.user else DBS[:2]
        self.explorer.db = dbs[(dbs.index(self.explorer.db) + 1) % len(dbs)]
        if self.explorer.db == "player":
            self.explorer.player = self.user
            self.explorer.color = "white" if not self.board.flipped else "black"
        self.refresh_all()

    def action_save(self):
        game = chess.pgn.Game()
        if self.start.root().fen() != chess.STARTING_FEN:
            game.setup(self.start.root())
        node = game
        for m in self.position.move_stack:
            node = node.add_variation(m)
        if self.opening:
            game.headers["Opening"] = self.opening["name"]
            game.headers["ECO"] = self.opening["eco"]
        game.headers["Event"] = "Repertoire"
        path = CHESS_DIR / "repertoire.pgn"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            print(game, file=f, end="\n\n")
        moves = line_san(self.position.root(), self.position.move_stack, limit=40)
        self.notify(f"{moves}\nsaved to {path}")

    def action_web(self):
        fen = self.position.fen().replace(" ", "_")
        open_url(f"https://lichess.org/analysis/standard/{fen}")
