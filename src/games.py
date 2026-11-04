# Your games, Lichess' and chess.com's (CHESS_USERS: site:user ...), kept in
# $CHESS_DIR/games by chess-sync: a list to search, and each game on the
# board with its review: the eval graph, the marked moves, the best ones,
# where you left the book; `t` at a mistake of yours to find better
import os
import re

import chess
import chess.pgn
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Input, ProgressBar, Sparkline, Static

import analysis as an
import deck
from board import BoardView, EvalBar, legend
from common import AGENTS, CHESS_DIR, line_san, open_url
from review import PHASES, filename, link, opening, run
from sync import sync
from train import good_enough

USERS = [u.split(":", 1) for u in os.environ.get("CHESS_USERS", "").split()]
MARKS = {6: an.INACCURACY, 2: an.MISTAKE, 4: an.BLUNDER}
MARK_STYLE = {an.INACCURACY: "yellow", an.MISTAKE: "dark_orange", an.BLUNDER: "red"}
EVAL = re.compile(r"\[%eval ([^\]]+)\]")


def site_of(h):
    return "chesscom" if "chess.com" in link(h) else "lichess"


def my_color(h):
    names = {u.lower() for site, u in USERS if site == site_of(h)}
    if h.get("White", "").lower() in names:
        return chess.WHITE
    if h.get("Black", "").lower() in names:
        return chess.BLACK
    return None


def review_path(h):
    return CHESS_DIR / "reviews" / filename(h)


def index():
    """Every game's headers and where it is, the newest first."""
    games = []
    for path in sorted((CHESS_DIR / "games").glob("*.pgn")):
        with path.open() as f:
            while True:
                offset = f.tell()
                h = chess.pgn.read_headers(f)
                if h is None:
                    break
                games.append((path, offset, h))
    games.sort(
        key=lambda g: (
            g[2].get("UTCDate", g[2].get("Date", "")),
            g[2].get("UTCTime", g[2].get("StartTime", "")),
        ),
        reverse=True,
    )
    return games


def read_game(path, offset):
    with path.open() as f:
        f.seek(offset)
        return chess.pgn.read_game(f)


def speed(h):
    tc = h.get("TimeControl", "-")
    if "+" in tc:
        base, inc = tc.split("+")
        return f"{int(base) // 60}+{inc}"
    if tc.isdigit():
        return f"{int(tc) // 60}+0" if int(tc) < 86400 else "daily"
    return tc


def outcome(h, me):
    result = h.get("Result", "*")
    if me is None or result == "*":
        return Text(result)
    if result == "1/2-1/2":
        return Text("draw", style="grey62")
    won = (result == "1-0") == (me == chess.WHITE)
    return Text("win", style="green") if won else Text("loss", style="red")


class GamesScreen(Screen):
    BINDINGS = [
        Binding("s", "sync", "fetch new games"),
        Binding("slash", "search", "search"),
        Binding("escape", "app.pop_screen", "back"),
    ]
    CSS = """
    #top { height: auto; }
    #search { width: 1fr; }
    #info { padding: 0 1; height: auto; }
    #table { height: 1fr; }
    """

    def compose(self) -> ComposeResult:
        yield Static(id="info")
        yield Input(placeholder="search: opponent, opening, win/loss, 3+2...", id="search")
        yield DataTable(id="table", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self):
        table = self.query_one(DataTable)
        table.add_columns("date", "site", "you", "opponent", "result", "time", "opening", "accuracy")
        self.games = []
        self.load()
        table.focus()
        if not self.games and USERS:
            self.action_sync()

    def load(self):
        self.games = index()
        self.fill(self.query_one(Input).value)

    def fill(self, query):
        table = self.query_one(DataTable)
        table.clear()
        words = query.lower().split()
        self.rows = []
        for path, offset, h in self.games:
            me = my_color(h)
            them = "Black" if me == chess.WHITE else "White"
            result = outcome(h, me)
            row_text = " ".join(
                [h.get(them, ""), opening(h), result.plain, speed(h), h.get("Date", "")]
            ).lower()
            if not all(w in row_text for w in words):
                continue
            acc = ""
            rp = review_path(h)
            if rp.exists():
                with rp.open() as f:
                    rh = chess.pgn.read_headers(f)
                key = "WhiteAccuracy" if me != chess.BLACK else "BlackAccuracy"
                acc = f"{rh.get(key)}%" if rh and rh.get(key) else ""
            table.add_row(
                h.get("UTCDate", h.get("Date", "")).replace(".", "-"),
                "li" if site_of(h) == "lichess" else "cc",
                "white" if me == chess.WHITE else "black" if me == chess.BLACK else "",
                f"{h.get(them, '?')} ({h.get(them + 'Elo', '?')})",
                result,
                speed(h),
                opening(h)[:40],
                acc,
            )
            self.rows.append((path, offset, h))
        users = ", ".join(f"{u} on {s}" for s, u in USERS) or "no CHESS_USERS"
        self.query_one("#info").update(
            f"[b]My games[/b]  [dim]{len(self.rows)} of {len(self.games)}, {users}; "
            "Enter or click to open, s fetches the new ones[/dim]"
        )

    def on_input_changed(self, event):
        self.fill(event.value)

    def on_input_submitted(self, event):
        self.query_one(DataTable).focus()

    def action_search(self):
        self.query_one(Input).focus()

    def on_data_table_row_selected(self, event):
        path, offset, h = self.rows[event.cursor_row]
        self.app.push_screen(GameScreen(path, offset, h), lambda _: self.load())

    @work(thread=True, exclusive=True, group="sync")
    def action_sync(self):
        for site, user in USERS:
            def progress(n, site=site):
                self.app.call_from_thread(
                    self.query_one("#info").update, f"fetching {site}: {n} new games"
                )

            try:
                new, total, _ = sync(site, user, progress)
            except OSError as e:
                self.app.call_from_thread(self.notify, f"{site}: {e}", severity="error")
                continue
            self.app.call_from_thread(self.notify, f"{site}: {new} new, {total} in all")
        self.app.call_from_thread(self.load)


class GameScreen(Screen):
    BINDINGS = [
        Binding("left", "move(-1)", "back", priority=True),
        Binding("right", "move(1)", "forward", priority=True),
        Binding("up", "mistake(-1)", "previous mistake", priority=True),
        Binding("down", "mistake(1)", "next mistake", priority=True),
        Binding("home", "goto(0)", "start", show=False, priority=True),
        Binding("end", "goto(-1)", "end", show=False, priority=True),
        Binding("a", "analyse", "review"),
        Binding("t", "try", "find better"),
        Binding("f", "flip", "flip"),
        Binding("w", "web", "open it"),
        Binding("escape", "app.pop_screen", "back"),
    ]
    CSS = """
    #left { width: 3fr; }
    #side { width: 2fr; padding: 0 1; }
    #head { height: auto; }
    #graph { height: 4; margin: 1 0 0 0; }
    #progress { display: none; }
    #moves { height: 1fr; }
    #now { height: auto; min-height: 4; border-top: solid $primary-darken-2; }
    """

    def __init__(self, path, offset, headers):
        super().__init__()
        self.source = (path, offset)
        self.h = headers
        self.me = my_color(headers)
        self.ply = 0
        self.trying = False

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield EvalBar()
            with Vertical(id="left"):
                yield BoardView(flipped=self.me == chess.BLACK)
                yield Static(legend(["last", "wrong", "best", "selected"]))
            with Vertical(id="side"):
                yield Static(id="head")
                yield Sparkline([], id="graph")
                yield ProgressBar(id="progress", show_eta=False)
                yield DataTable(id="moves", cursor_type="cell", show_header=False)
                yield Static(id="now")
        yield Footer()

    def on_mount(self):
        self.view = self.query_one(BoardView)
        self.query_one(EvalBar).flipped = self.view.flipped
        self.load()

    def load(self):
        rp = review_path(self.h)
        reviewed = rp.exists() and read_game(rp, 0)
        # reviews from before the accuracy headers are made again
        self.reviewed = bool(reviewed) and reviewed.headers.get("Annotator") in AGENTS
        self.game = reviewed if self.reviewed else read_game(*self.source)
        self.nodes = list(self.game.mainline())
        self.boards = [self.game.board()] + [n.board() for n in self.nodes]
        self.cps = []
        for n in self.nodes:
            m = EVAL.search(n.comment)
            self.cps.append(an.parse_eval(m.group(1)) if m else None)
        self.marks = {
            i: MARKS[nag] for i, n in enumerate(self.nodes) for nag in n.nags if nag in MARKS
        }
        self.fill_head()
        self.fill_moves()
        graph = self.query_one(Sparkline)
        graph.data = [an.win_percent(c) for c in self.cps if c is not None] or [50]
        self.goto(self.ply)

    def fill_head(self):
        h = self.game.headers
        lines = [
            f"[b]{h.get('White')}[/b] ({h.get('WhiteElo', '?')}) – "
            f"[b]{h.get('Black')}[/b] ({h.get('BlackElo', '?')})  {h.get('Result')}  "
            f"[dim]{h.get('Date', '')} {speed(h)}[/dim]",
            f"[dim]{opening(h)}[/dim]",
        ]
        if self.reviewed:
            acc = []
            for side, key in ((chess.WHITE, "WhiteAccuracy"), (chess.BLACK, "BlackAccuracy")):
                who = "you" if side == self.me else h.get("White" if side else "Black")
                if key in h:
                    count = [self.marks[i] for i in self.marks if self.boards[i].turn == side]
                    marks = " ".join(
                        f"[{MARK_STYLE[k]}]{count.count(k)}{k}[/]"
                        for k in (an.INACCURACY, an.MISTAKE, an.BLUNDER)
                    )
                    acc.append(f"{who} [b]{h[key]}%[/b] {marks}")
            lines.append("accuracy  " + "    ".join(acc))
            if "BookExit" in h:
                lines.append(f"[dim]book: {h['BookExit']}[/dim]")
        else:
            lines.append("[yellow]not reviewed yet: a reviews it[/yellow] [dim](about a minute)[/dim]")
        self.query_one("#head").update("\n".join(lines))

    def fill_moves(self):
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.add_columns("n", "white", "black")
        row = []
        for i, node in enumerate(self.nodes):
            san = self.boards[i].san(node.move)
            mark = self.marks.get(i)
            cell = Text(san + (mark or ""), style=MARK_STYLE.get(mark, ""))
            if i % 2 == 0:
                row = [Text(f"{i // 2 + 1}.", style="dim"), cell]
            else:
                row.append(cell)
                table.add_row(*row)
                row = []
        if row:
            table.add_row(*row, "")

    def goto(self, ply):
        n = len(self.nodes)
        self.ply = n if ply < 0 else max(0, min(n, ply))
        self.trying = False
        board = self.boards[self.ply]
        marks = {}
        text = []
        i = self.ply - 1
        if i >= 0:
            node = self.nodes[i]
            san = self.boards[i].san(node.move)
            mark = self.marks.get(i)
            num = f"{i // 2 + 1}{'.' if i % 2 == 0 else '...'}"
            if mark:
                best = node.parent.variations[1]
                marks = {
                    node.move.from_square: "wrong",
                    node.move.to_square: "wrong",
                    best.move.from_square: "best",
                    best.move.to_square: "best",
                }
                pv = [best.move] + [v.move for v in best.mainline()]
                mine = self.boards[i].turn == self.me
                text.append(
                    f"[{MARK_STYLE[mark]} b]{num}{san}{mark}[/] {an.NAMES[mark]}"
                    + ("  [dim]t: find better yourself[/dim]" if mine else "")
                )
                text.append(f"[b]best[/b] {line_san(self.boards[i], pv)}")
            else:
                text.append(f"[b]{num}{san}[/b]")
            cp = self.cps[i]
            bar = self.query_one(EvalBar)
            if cp is not None:
                bar.set(cp, an.describe(cp))
        else:
            self.query_one(EvalBar).set(None, "")
            text.append("[dim]start: → to go on, ↓ to the next mistake[/dim]")
        self.view.player = set()
        self.view.show(board, marks)
        self.now_text = "\n".join(text)
        self.query_one("#now").update(self.now_text)
        if i >= 0:
            table = self.query_one(DataTable)
            table.move_cursor(row=i // 2, column=1 + i % 2, animate=False)

    def on_data_table_cell_selected(self, event):
        row, col = event.coordinate.row, event.coordinate.column
        if col == 0:
            col = 1
        ply = row * 2 + col
        if ply != self.ply:
            self.goto(ply)

    def action_move(self, step):
        self.goto(self.ply + step)

    def action_goto(self, ply):
        self.goto(ply)

    def action_mistake(self, step):
        mine = [
            i + 1
            for i, m in sorted(self.marks.items())
            if m != an.INACCURACY and (self.me is None or self.boards[i].turn == self.me)
        ]
        if not mine:
            self.notify("no mistakes marked" if self.reviewed else "review it first: a")
            return
        nxt = [p for p in mine if p > self.ply] if step > 0 else [p for p in mine if p < self.ply]
        if nxt:
            self.goto(nxt[0] if step > 0 else nxt[-1])

    def action_flip(self):
        self.view.flip()
        bar = self.query_one(EvalBar)
        bar.flipped = self.view.flipped
        bar.refresh()

    def action_web(self):
        open_url(link(self.h))

    # finding the better move at a mistake of yours

    def action_try(self):
        i = self.ply - 1
        if i < 0 or i not in self.marks or self.boards[i].turn != self.me:
            self.notify("go to a mistake of yours first (↓)")
            return
        self.trying = True
        board = self.boards[i]
        self.view.show(board)
        self.view.player = {board.turn}
        self.query_one("#now").update(
            f"[b]Find better than {board.san(self.nodes[i].move)}[/b]: play it on the board"
        )

    def on_board_view_moved(self, event):
        if not self.trying:
            return
        i = self.ply - 1
        board = self.boards[i]
        if event.move == self.nodes[i].move:
            self.notify("that's what you played")
            return
        self.view.player = set()
        self.query_one("#now").update("[dim]checking...[/dim]")
        self.judge(i, board, event.move)

    @work(thread=True, exclusive=True, group="judge")
    def judge(self, i, board, move):
        right = good_enough(self.app.engine("stockfish"), board, move)
        self.app.call_from_thread(self.judged, i, board, move, right)

    def judged(self, i, board, move, right):
        san = board.san(move)
        self.goto(i + 1)
        head = f"[green b]✔ {san}[/green b] keeps it" if right else f"[red b]✘ {san}[/red b] isn't enough either"
        self.query_one("#now").update(head + "\n" + self.now_text)

    # the review

    @work(thread=True, exclusive=True, group="review")
    def action_analyse(self):
        if self.reviewed:
            self.app.call_from_thread(self.notify, "reviewed already")
            return
        bar = self.query_one(ProgressBar)
        self.app.call_from_thread(setattr, bar.styles, "display", "block")

        def progress(i, total):
            self.app.call_from_thread(bar.update, total=total, progress=i)

        game = read_game(*self.source)
        ratings = "1400,1600,1800,2000" if self.me is not None else None
        result = run(game, self.app.engine("stockfish"), self.me, ratings, progress)
        cards = deck.load()
        new = sum(deck.add(cards, c) for c in result["cards"])
        deck.save(cards)
        self.app.call_from_thread(setattr, bar.styles, "display", "none")
        phases = ""
        if self.me is not None:
            by = result["by_phase"]
            phases = "  ".join(
                f"{p} {round(by[p][self.me])}%" for p in PHASES if self.me in by.get(p, {})
            )
        self.app.call_from_thread(
            self.notify, f"{phases}\n{new} new positions for training", timeout=8
        )
        self.app.call_from_thread(self.load)
