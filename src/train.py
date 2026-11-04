# Your mistakes again (chess-review puts them in $CHESS_DIR/training.json):
# the position before it, to find a better move. Any move as good as the
# engine's counts; found, a position waits longer before coming back,
# missed (or helped), it comes back tomorrow. Then the board plays the best
# line, and what punished your move
import chess
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Static

import analysis as an
import deck
from board import BoardView, legend
from common import line_san, open_url


def good_enough(engine, board, move):
    """The move keeps what the position had: not even an inaccuracy."""
    before = engine.analyse(board)["score"]
    after_board = board.copy()
    after_board.push(move)
    if after_board.is_checkmate():
        return True
    after = engine.analyse(after_board)["score"]
    return an.judge(before, after, board.turn) is None


def select(cards, phase=None, tag=None, everything=False):
    todo = list(cards.values()) if everything else deck.due(cards)
    return [
        c
        for c in todo
        if (not phase or c["phase"] == phase) and (not tag or tag in c["tags"])
    ]


class LinePlayer:
    """Plays moves on a board view one by one."""

    def __init__(self, screen, view):
        self.screen = screen
        self.view = view
        self.timer = None

    def play(self, board, moves, marks=None, done=None):
        self.stop()
        board = board.copy()
        moves = list(moves)
        self.view.show(board.copy(), marks)

        def step():
            if not moves:
                self.stop()
                if done:
                    done()
                return
            board.push(moves.pop(0))
            self.view.show(board.copy())

        self.timer = self.screen.set_interval(0.9, step)

    def stop(self):
        if self.timer:
            self.timer.stop()
            self.timer = None


class TrainScreen(Screen):
    BINDINGS = [
        Binding("h", "hint", "hint"),
        Binding("s", "give_up", "show me"),
        Binding("b", "best_line", "best line"),
        Binding("y", "your_line", "what you played"),
        Binding("n", "next", "next"),
        Binding("w", "web", "the game"),
        Binding("escape", "app.pop_screen", "back"),
    ]
    CSS = """
    #left { width: 3fr; }
    #side { width: 2fr; padding: 0 1; }
    #title { text-style: bold; }
    #card { margin: 1 0; }
    #status { min-height: 2; }
    #explain { margin-top: 1; }
    """

    def __init__(self, cards, todo, seconds=0.5):
        super().__init__()
        self.cards = cards
        self.todo = todo
        self.seconds = seconds
        self.i = -1
        self.found = 0
        self.done = 0

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="left"):
                yield BoardView(id="board")
                yield Static(legend(["last", "hint", "best", "wrong", "selected"]))
            with Vertical(id="side"):
                yield Static(id="title")
                yield Static(id="card")
                yield Static(id="status")
                yield Static(id="explain")
        yield Footer()

    def on_mount(self):
        self.view = self.query_one(BoardView)
        self.player = LinePlayer(self, self.view)
        self.action_next()

    def say(self, text):
        self.query_one("#status").update(text)

    def position(self):
        return chess.Board(self.card["fen"])

    def action_next(self):
        self.player.stop()
        self.i += 1
        if self.i >= len(self.todo):
            self.finish_all()
            return
        self.card = self.todo[self.i]
        self.answered = False
        self.helped = False
        board = self.position()
        self.view.flipped = board.turn == chess.BLACK
        self.view.player = {board.turn}
        self.view.show(board)
        played = chess.Move.from_uci(self.card["played"])
        c = self.card
        tags = f"\n[dim]{', '.join(c['tags'])}[/dim]" if c["tags"] else ""
        self.query_one("#card").update(
            f"vs {c['opponent']}, {c['date']}\n[dim]{c['opening']}[/dim]\n\n"
            f"You played [red b]{line_san(board, [played])}[/red b], a "
            f"[b]{an.NAMES[c['mark']]}[/b] in the {c['phase']} "
            f"({c['before']} → {c['after']}){tags}\n\n"
            f"[b]{'White' if board.turn else 'Black'} to play: find better[/b]"
        )
        self.say("")
        self.query_one("#explain").update("")
        self.update_title()

    def update_title(self):
        self.query_one("#title").update(
            f"Your mistakes  [dim]{self.i + 1} of {len(self.todo)}[/dim]   "
            f"found [green b]{self.found}[/green b] of {self.done}"
        )

    def finish_all(self):
        self.view.player = set()
        left = len(deck.due(self.cards))
        self.query_one("#card").update(
            f"[b]That's all for now.[/b] {self.found} of {self.done} found.\n"
            f"{left} still due today.\n\n"
            "[dim]chess review / My games adds more from your games[/dim]"
        )
        self.say("")
        self.query_one("#explain").update("")

    def on_board_view_moved(self, event):
        if self.answered:
            return
        move = event.move
        board = self.position()
        if move.uci() == self.card["played"]:
            self.view.mark({move.to_square: "wrong"})
            self.say("[yellow]That's what you played[/yellow]: look again")
            return
        if move.uci() == self.card["best"]:
            self.answer(True, move)
            return
        self.say("[dim]checking...[/dim]")
        self.view.player = set()
        self.judge(board, move)

    @work(thread=True, exclusive=True, group="judge")
    def judge(self, board, move):
        right = good_enough(self.app.engine("stockfish", self.seconds), board, move)
        self.app.call_from_thread(self.answer, right, move)

    def answer(self, right, move=None):
        self.answered = True
        self.view.player = set()
        board = self.position()
        right = right and not self.helped
        self.done += 1
        self.found += right
        deck.answer(self.cards[self.card["id"]], right)
        deck.save(self.cards)
        best = chess.Move.from_uci(self.card["best"])
        if move is not None and move != best and right:
            head = f"[green b]✔ {board.san(move)}[/green b] works too"
        elif right:
            head = f"[green b]✔ {board.san(move)}[/green b], the best move"
        elif move is not None and not self.helped:
            head = f"[red b]✘ {board.san(move)}[/red b] isn't good enough"
        else:
            head = "[yellow]Shown[/yellow]: it comes back tomorrow"
        box = self.cards[self.card["id"]]["box"]
        when = f"back in {deck.INTERVALS[box]} days" if right else "back tomorrow"
        self.say(f"{head}  [dim]{when}[/dim]")
        self.explain(board, best)
        self.update_title()

    def explain(self, board, best):
        c = self.card
        best_pv = [chess.Move.from_uci(m) for m in c["best_pv"]]
        played = chess.Move.from_uci(c["played"])
        after = board.copy()
        after.push(played)
        reply = [chess.Move.from_uci(m) for m in c["reply_pv"]]
        text = f"[b]best[/b]   {line_san(board, best_pv)}"
        if reply:
            text += f"\n[b]yours[/b]  {line_san(board, [played])} {line_san(after, reply)}"
        text += "\n\n[dim]b plays the best line, y yours; n next[/dim]"
        self.query_one("#explain").update(text)
        self.view.show(board, {best.from_square: "best", best.to_square: "best"})

    def action_hint(self):
        if self.answered or self.i >= len(self.todo):
            return
        self.helped = True
        board = self.position()
        best = chess.Move.from_uci(self.card["best"])
        piece = chess.piece_name(board.piece_type_at(best.from_square))
        self.view.mark({best.from_square: "hint"})
        self.say(f"The {piece} on {chess.square_name(best.from_square)} [dim](a hint counts as missed)[/dim]")

    def action_give_up(self):
        if not self.answered and self.i < len(self.todo):
            self.helped = True
            self.answer(False)

    def action_best_line(self):
        if self.answered:
            moves = [chess.Move.from_uci(m) for m in self.card["best_pv"]]
            self.player.play(self.position(), moves)

    def action_your_line(self):
        if self.answered:
            moves = [chess.Move.from_uci(self.card["played"])]
            moves += [chess.Move.from_uci(m) for m in self.card["reply_pv"]]
            self.player.play(self.position(), moves)

    def action_web(self):
        if self.i < len(self.todo):
            open_url(self.card["game"])
