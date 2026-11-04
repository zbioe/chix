# chess: one app for everything chess on the terminal, mouse included.
# `chess` opens the menu; `chess openings [NAME]`, `chess games`,
# `chess train`, `chess puzzle`, `chess explore [MOVES]` go straight there
import argparse
import os
import subprocess
import sys
from pathlib import Path

import chess
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

import deck
import games
from common import ENGINES, Engine, is_maia, open_url
from explore import ExploreScreen
from openings import PickScreen, load
from puzzle import THEMES, PuzzleScreen
from train import TrainScreen, select

TUI = os.environ.get("CHESS_TUI", "chess-tui")


class HomeScreen(Screen):
    BINDINGS = [Binding("q", "app.quit", "quit")]
    CSS = """
    HomeScreen { align: center middle; }
    #menu-box { width: 76; max-width: 100%; height: auto; max-height: 100%; }
    #hello { padding: 0 1 1 1; }
    #menu { height: auto; max-height: 100%; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="menu-box"):
            yield Static(id="hello")
            yield OptionList(id="menu")
        yield Footer()

    def on_screen_resume(self):
        self.fill()

    def fill(self):
        mistakes = len(deck.due(deck.load()))
        lines = deck.load("openings")
        lines_due = len([c for c in deck.due(lines) if c.get("history")])
        self.query_one("#hello").update(
            "[b]♞ Chess[/b]   [dim]click or Enter; Esc goes back, the bar below "
            "lists the keys of each screen[/dim]"
        )

        def item(key, title, about):
            return Option(f"[b]{title}[/b]\n  [dim]{about}[/dim]", id=key)

        menu = self.query_one(OptionList)
        menu.clear_options()
        menu.add_options(
            [
                item(
                    "window",
                    "Learn an opening, in a window",
                    "the same lines and progress, on a board you drag pieces on",
                ),
                item(
                    "openings",
                    "Learn an opening, here",
                    f"by its name, every variation, line by line ({lines_due} to review)",
                ),
                item(
                    "train",
                    f"Train your mistakes  ({mistakes} due)",
                    "the positions where you went wrong, to find better",
                ),
                item("puzzle", "Puzzles", "Lichess: daily, or by theme and difficulty"),
                item("games", "My games", "Lichess and chess.com, reviewed move by move"),
                item("explore", "Explorer", "what's played from a position, and the engine"),
                None,
                item("play", "Play in the terminal", "Lichess or an engine (chess-tui)"),
                item("maia", "Play a human-like bot", "Maia 1500, offline (chess-tui)"),
                item("lichess", "Lichess", "in the browser"),
                item("chesscom", "chess.com", "in the browser"),
            ]
        )
        menu.focus()

    def on_option_list_option_selected(self, event):
        key = event.option.id
        app = self.app
        if key == "window":
            subprocess.Popen(
                [sys.executable, Path(__file__).parent / "gui.py"],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.notify("Chess Openings opens in a window")
        elif key == "openings":
            app.push_screen(PickScreen(app.families()))
        elif key == "train":
            cards = deck.load()
            app.push_screen(TrainScreen(cards, select(cards)))
        elif key == "puzzle":
            app.push_screen(PuzzleScreen(daily=False))
        elif key == "games":
            app.push_screen(games.GamesScreen())
        elif key == "explore":
            app.push_screen(ExploreScreen(user=app.lichess_user()))
        elif key in ("play", "maia"):
            args = [TUI] + (["--engine", "maia-1500"] if key == "maia" else [])
            with app.suspend():
                subprocess.run(args)
        elif key == "lichess":
            open_url("https://lichess.org")
        elif key == "chesscom":
            open_url("https://www.chess.com/play/online")


class ChessApp(App):
    TITLE = "chess"

    def __init__(self, first=None):
        super().__init__()
        self.first = first
        self.engines = {}
        self._families = None

    def families(self):
        if self._families is None:
            self._families = load()
        return self._families

    def lichess_user(self):
        return next((u for s, u in games.USERS if s == "lichess"), None)

    def engine(self, name="stockfish", seconds=0.5):
        if name not in self.engines:
            self.engines[name] = Engine(name, seconds)
        self.engines[name].seconds = seconds
        return self.engines[name]

    def on_mount(self):
        self.push_screen(HomeScreen())
        if self.first:
            self.push_screen(self.first(self))

    def on_unmount(self):
        for e in self.engines.values():
            e.quit()


def main():
    p = argparse.ArgumentParser(prog="chess", description="Chess on the terminal")
    sub = p.add_subparsers(dest="screen")
    o = sub.add_parser("openings", help="learn an opening by its name")
    o.add_argument("name", nargs="*", help="part of its name: bishop, caro...")
    sub.add_parser("games", help="your games, reviewed")
    t = sub.add_parser("train", help="find again the moves you missed")
    t.add_argument("--phase", choices=["opening", "middlegame", "endgame"])
    t.add_argument("--tag", help="only this kind: lost material, missed mate...")
    t.add_argument("--all", action="store_true", help="also the ones not due today")
    t.add_argument("--time", type=float, default=0.5, help="engine seconds to judge")
    z = sub.add_parser("puzzle", help="puzzles")
    z.add_argument("site", nargs="?", choices=["lichess", "chesscom"], default="lichess")
    z.add_argument("--daily", action="store_true", help="the daily one first")
    z.add_argument("--theme", default="mix", choices=[v for _, v in THEMES])
    z.add_argument(
        "--difficulty",
        default="normal",
        choices=["easiest", "easier", "normal", "harder", "hardest"],
    )
    e = sub.add_parser("explore", help="the opening explorer and an engine")
    e.add_argument("moves", nargs="*", help="a line to start from: e4 e5 Nf3")
    e.add_argument("--fen", help="a position to start from")
    e.add_argument(
        "--engine", default="stockfish", choices=sorted(n for n in ENGINES if not is_maia(n))
    )
    args = p.parse_args()

    first = None
    if args.screen == "openings":
        query = " ".join(args.name)

        def first(app):
            return PickScreen(app.families(), query)
    elif args.screen == "games":

        def first(app):
            return games.GamesScreen()
    elif args.screen == "train":
        cards = deck.load()
        todo = select(cards, args.phase, args.tag, args.all)

        def first(app):
            return TrainScreen(cards, todo, args.time)
    elif args.screen == "puzzle":
        daily = args.daily

        def first(app):
            return PuzzleScreen(args.site, args.theme, args.difficulty, daily)
    elif args.screen == "explore":
        board = chess.Board(args.fen) if args.fen else chess.Board()
        for m in args.moves:
            board.push_san(m)

        def first(app):
            return ExploreScreen(board, args.engine, app.lichess_user())

    ChessApp(first).run()


if __name__ == "__main__":
    main()
