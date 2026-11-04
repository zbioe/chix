# The board the chess app draws: squares as big as the terminal allows,
# moves made with the mouse (a piece, then where it goes) or typed; colored
# squares say what happened, and the legend says what each color means
import chess
from rich.text import Text
from textual.message import Message
from textual.widget import Widget

import analysis as an

# small squares: a glyph (the pawn asks for text, not its emoji)
GLYPHS = dict(zip("kqrbnp", ["♚", "♛", "♜", "♝", "♞", "♟\ufe0e"]))
# big squares: 7x6 pixels, two to a cell with half blocks
SPRITES = {
    "p": [".......", "...#...", "..###..", "...#...", "..###..", ".#####."],
    "r": [".#.#.#.", ".#####.", "..###..", "..###..", "..###..", ".#####."],
    "n": ["...##..", "..####.", ".##.##.", "...###.", "..###..", ".#####."],
    "b": ["...#...", "..###..", "..#.#..", "..###..", "...#...", ".#####."],
    "q": ["#..#..#", "##.#.##", ".#####.", "..###..", "..###..", ".#####."],
    "k": ["...#...", "..###..", "...#...", ".#####.", "..###..", ".#####."],
}
LIGHT, DARK = (238, 216, 180), (172, 128, 92)
WHITE_PIECE, BLACK_PIECE = (255, 255, 255), (16, 16, 16)
# what a colored square means: (tint, legend)
MARKS = {
    "last": ((230, 210, 60), "last move"),
    "selected": ((90, 150, 230), "selected"),
    "target": ((120, 180, 240), "can go there"),
    "hint": ((90, 200, 110), "the move to play"),
    "best": ((60, 200, 220), "best move"),
    "wrong": ((230, 70, 60), "not this one"),
    "check": ((240, 40, 40), "check"),
}


def mix(a, b, amount):
    return tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def rgb(c):
    return f"rgb({c[0]},{c[1]},{c[2]})"


def legend(names):
    """A line with a swatch per mark: the legend of what's on the board."""
    text = Text()
    for name in names:
        tint, label = MARKS[name]
        text.append("  ")
        text.append("  ", style=f"on {rgb(tint)}")
        text.append(f" {label}")
    return text


class BoardView(Widget):
    """`player`: the colors the mouse may move (none: only looked at)."""

    DEFAULT_CSS = """
    BoardView { width: 1fr; height: 1fr; min-width: 28; min-height: 9; }
    """

    class Moved(Message):
        def __init__(self, board_view, move):
            super().__init__()
            self.board_view = board_view
            self.move = move

    def __init__(self, board=None, *, flipped=False, player=(), **kw):
        super().__init__(**kw)
        self.board = board or chess.Board()
        self.flipped = flipped
        self.player = set(player)
        self.selected = None
        # square -> mark, on top of the last move and the check
        self.marks = {}

    def show(self, board, marks=None):
        self.board = board
        self.selected = None
        self.marks = dict(marks or {})
        self.refresh()

    def mark(self, marks):
        self.marks = dict(marks)
        self.refresh()

    def flip(self):
        self.flipped = not self.flipped
        self.refresh()

    # the squares: h rows high, 2h + 1 columns wide (terminal cells are tall)
    def cell(self):
        h = max(1, min((self.size.height - 1) // 8, (self.size.width - 10) // 16))
        return h, 2 * h + 1

    def order(self):
        ranks = list(range(8)) if self.flipped else list(range(7, -1, -1))
        files = list(range(7, -1, -1)) if self.flipped else list(range(8))
        return ranks, files

    def tints(self):
        tints = {}
        if self.board.move_stack:
            last = self.board.peek()
            tints[last.from_square] = tints[last.to_square] = "last"
        if self.board.is_check():
            tints[self.board.king(self.board.turn)] = "check"
        tints |= self.marks
        if self.selected is not None:
            tints[self.selected] = "selected"
        return tints

    def targets(self):
        if self.selected is None:
            return set()
        return {
            m.to_square
            for m in self.board.legal_moves
            if m.from_square == self.selected
        }

    def render(self):
        h, w = self.cell()
        ranks, files = self.order()
        tints = self.tints()
        targets = self.targets()
        text = Text()
        for rank in ranks:
            for row in range(h):
                label = str(rank + 1) if row == h // 2 else " "
                text.append(f"{label} ", style="dim")
                for file in files:
                    sq = chess.square(file, rank)
                    base = LIGHT if (file + rank) % 2 else DARK
                    bg = base
                    if sq in tints:
                        tint, _ = MARKS[tints[sq]]
                        bg = mix(base, tint, 0.55)
                    piece = self.board.piece_at(sq)
                    self.square(text, row, h, w, base, bg, piece, sq in targets)
                text.append("\n")
        text.append("  ")
        for file in files:
            text.append("abcdefgh"[file].center(w), style="dim")
        return text

    def square(self, text, row, h, w, base, bg, piece, target):
        tint, _ = MARKS["target"]
        if target and piece:
            bg = mix(base, tint, 0.7)
        on = f"on {rgb(bg)}"
        if piece and h >= 3:
            fg = rgb(WHITE_PIECE if piece.color else BLACK_PIECE)
            top = (h - 3) // 2
            if not top <= row < top + 3:
                text.append(" " * w, style=on)
                return
            sprite = SPRITES[piece.symbol().lower()]
            upper, lower = sprite[2 * (row - top)], sprite[2 * (row - top) + 1]
            pad = (w - 7) // 2
            text.append(" " * pad, style=on)
            for a, b in zip(upper, lower):
                cell = {("#", "#"): "█", ("#", "."): "▀", (".", "#"): "▄"}.get((a, b), " ")
                text.append(cell, style=f"{fg} {on}")
            text.append(" " * (w - 7 - pad), style=on)
            return
        mid = w // 2
        if row != h // 2:
            text.append(" " * w, style=on)
        elif piece:
            fg = WHITE_PIECE if piece.color else BLACK_PIECE
            glyph = GLYPHS[piece.symbol().lower()]
            text.append(" " * mid, style=on)
            text.append(glyph, style=f"bold {rgb(fg)} {on}")
            text.append(" " * (w - mid - 1), style=on)
        elif target:
            text.append(" " * mid, style=on)
            text.append("●", style=f"{rgb(mix(base, tint, 0.85))} {on}")
            text.append(" " * (w - mid - 1), style=on)
        else:
            text.append(" " * w, style=on)

    def square_at(self, x, y):
        h, w = self.cell()
        x -= 2
        if x < 0 or y < 0 or x >= 8 * w or y >= 8 * h:
            return None
        ranks, files = self.order()
        return chess.square(files[x // w], ranks[y // h])

    def on_click(self, event):
        offset = event.get_content_offset(self)
        if offset is None:
            return
        sq = self.square_at(offset.x, offset.y)
        if sq is None or self.board.turn not in self.player:
            return
        piece = self.board.piece_at(sq)
        if self.selected is not None and sq in self.targets():
            move = chess.Move(self.selected, sq)
            if (
                self.board.piece_type_at(self.selected) == chess.PAWN
                and chess.square_rank(sq) in (0, 7)
            ):
                move.promotion = chess.QUEEN
            self.selected = None
            self.refresh()
            self.post_message(self.Moved(self, move))
            return
        if piece and piece.color == self.board.turn and sq != self.selected:
            self.selected = sq
        else:
            self.selected = None
        self.refresh()


class EvalBar(Widget):
    """White's share of the bar: its chances to win, as Lichess draws them."""

    DEFAULT_CSS = """
    EvalBar { width: 6; height: 1fr; margin-right: 1; }
    """

    def __init__(self, **kw):
        super().__init__(**kw)
        self.cp = None
        self.label = ""
        self.flipped = False

    def set(self, cp, label):
        self.cp = cp
        self.label = label
        self.refresh()

    def render(self):
        rows = max(1, self.size.height - 1)
        text = Text()
        if self.cp is None:
            for _ in range(rows):
                text.append("      \n", style="on grey23")
            return text
        white = round(rows * an.win_percent(self.cp) / 100)
        for i in range(rows):
            # White's side of the bar is the side White sits on
            is_white = i < white if self.flipped else rows - 1 - i < white
            text.append("      \n", style="on grey93" if is_white else "on grey11")
        text.append(self.label[:6], style="bold")
        return text
