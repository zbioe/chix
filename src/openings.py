# An opening by its name (Lichess' chess-openings: every named line), learned
# line by line: first shown, then played from memory, then brought back on
# the days spaced repetition says. The tree holds all its variations, to
# walk or pick from; the progress is kept in $CHESS_DIR/openings.json
import os
import random
import unicodedata
from pathlib import Path

import chess
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Input, OptionList, ProgressBar, Static, Tree
from textual.widgets.option_list import Option

import deck
from board import BoardView, legend
from common import open_url

DECK = "openings"
SOURCE = Path(os.environ["CHESS_OPENINGS"])


class Node:
    def __init__(self, move=None, san=None, parent=None):
        self.move = move
        self.san = san
        self.parent = parent
        self.children = {}
        self.name = None
        self.eco = None
        self.ply = parent.ply + 1 if parent else 0

    def path(self):
        node, out = self, []
        while node.parent:
            out.append(node)
            node = node.parent
        return out[::-1]

    def board(self):
        b = chess.Board()
        for n in self.path():
            b.push(n.move)
        return b

    def label(self):
        """The name of the line it's on: its own or the nearest above."""
        node = self
        while node and not node.name:
            node = node.parent
        return node.name if node else ""

    def leaves(self):
        if not self.children:
            return [self]
        return [leaf for c in self.branches() for leaf in c.leaves()]

    def branches(self):
        """The children, the ones with more lines under them first."""
        return sorted(self.children.values(), key=lambda c: -c.size())

    def size(self):
        if not hasattr(self, "_size"):
            self._size = sum(c.size() for c in self.children.values()) or 1
        return self._size

    def numbered(self):
        b = self.parent.ply
        return f"{b // 2 + 1}.{self.san}" if b % 2 == 0 else f"{b // 2 + 1}...{self.san}"


def fold(text):
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if c.isalnum() or c == " ")


def load():
    """{family: [(eco, name, [moves])]}: a family is the name before ':'."""
    families = {}
    for path in sorted(SOURCE.glob("[a-e].tsv")):
        for row in path.read_text().splitlines()[1:]:
            eco, name, pgn = row.split("\t")
            board = chess.Board()
            moves = []
            for token in pgn.split():
                if token[0].isdigit():
                    continue
                moves.append(board.push_san(token))
            families.setdefault(name.split(":")[0], []).append((eco, name, moves))
    return families


class Opening:
    """A family's tree: the lines that go through its first named position
    (the ones reached by transposition are left out)."""

    def __init__(self, family, lines):
        self.family = family
        exact = [ln for ln in lines if ln[1] == family] or lines
        root = min(exact, key=lambda ln: len(ln[2]))[2]
        self.start = Node()
        self.excluded = 0
        for eco, name, moves in lines:
            if moves[: len(root)] != root:
                self.excluded += 1
                continue
            node = self.start
            board = chess.Board()
            for m in moves:
                key = m.uci()
                if key not in node.children:
                    node.children[key] = Node(m, board.san(m), node)
                node = node.children[key]
                board.push(m)
            node.name, node.eco = name, eco
        self.root = self.start
        for _ in root:
            self.root = next(iter(self.root.children.values()))
        # the side whose move named it plays it: 1.e4 e5 2.Bc4 is White's
        self.color = chess.WHITE if len(root) % 2 else chess.BLACK
        # main branches first: the ones with the most lines under them
        self.leaves = self.root.leaves()

    def key(self, leaf, color):
        side = "white" if color == chess.WHITE else "black"
        return f"{side}:{self.family}:{' '.join(n.move.uci() for n in leaf.path())}"


def short(name, family):
    return name[len(family) + 2 :] if name.startswith(family + ": ") else name


class PickScreen(Screen):
    """The openings, searched by name; the ones you've started come first."""

    BINDINGS = [Binding("escape", "app.pop_screen", "back")]
    CSS = """
    PickScreen { align: center top; }
    #pick { width: 90; max-width: 100%; height: 1fr; padding: 1 2; }
    #search { margin-bottom: 1; }
    """

    def __init__(self, families, query=""):
        super().__init__()
        self.families = families
        self.initial = query

    def compose(self) -> ComposeResult:
        with Vertical(id="pick"):
            yield Static(
                "[b]Learn an opening[/b]: type part of its name "
                "(bishop, sicilian, caro, queen's gambit...), Enter or click to open"
            )
            yield Input(self.initial, placeholder="search", id="search")
            yield OptionList(id="list")
        yield Footer()

    def on_mount(self):
        self.progress = deck.load(DECK)
        self.trees = {}
        self.fill(self.initial)
        self.query_one(Input).focus()

    def on_screen_resume(self):
        self.progress = deck.load(DECK)
        self.fill(self.query_one(Input).value)

    def tree(self, family):
        if family not in self.trees:
            self.trees[family] = Opening(family, self.families[family])
        return self.trees[family]

    def learned(self, family):
        return sum(
            1 for k, c in self.progress.items()
            if k.split(":")[1] == family and c.get("box", 0) > 0
        )

    def fill(self, query):
        words = fold(query).split()
        found = [f for f in self.families if all(w in fold(f) for w in words)]
        found.sort(key=lambda f: (-self.learned(f), -len(self.families[f]), f))
        options = []
        for f in found[:150]:
            n = len(self.tree(f).leaves)
            done = self.learned(f)
            mark = f"  [green]{done} learned[/green]" if done else ""
            options.append(Option(f"[b]{f}[/b]  [dim]{n} lines[/dim]{mark}", id=f))
        # a variation by its name: the opening opens on it
        if words:
            variations = [
                (f, name)
                for f, lines in self.families.items()
                for _, name, _ in lines
                if f not in found and all(w in fold(name) for w in words)
            ]
            for f, name in sorted(set(variations))[:150]:
                options.append(
                    Option(f"{f}: [cyan]{short(name, f)}[/cyan]", id=f"{f}\t{name}")
                )
        ol = self.query_one(OptionList)
        ol.clear_options()
        ol.add_options(options)
        if options:
            ol.highlighted = 0

    def on_input_changed(self, event):
        self.fill(event.value)

    def on_input_submitted(self, event):
        ol = self.query_one(OptionList)
        if ol.highlighted is not None:
            self.open(ol.get_option_at_index(ol.highlighted).id)

    def on_option_list_option_selected(self, event):
        self.open(event.option.id)

    def on_key(self, event):
        # the arrows go to the list while typing
        if event.key in ("down", "up") and self.focused is self.query_one(Input):
            ol = self.query_one(OptionList)
            ol.action_cursor_down() if event.key == "down" else ol.action_cursor_up()
            event.stop()

    def open(self, key):
        family, _, name = key.partition("\t")
        self.app.push_screen(OpeningScreen(self.tree(family), name or None))


class OpeningScreen(Screen):
    BINDINGS = [
        Binding("n", "next_line", "next line"),
        Binding("h", "hint", "hint"),
        Binding("r", "restart", "again"),
        Binding("t", "train_here", "train from here"),
        Binding("c", "switch_color", "play the other side"),
        Binding("left", "back", "back", show=False, priority=True),
        Binding("f", "flip", "flip"),
        Binding("x", "explore", "explorer"),
        Binding("w", "web", "lichess"),
        Binding("escape", "app.pop_screen", "back"),
    ]
    CSS = """
    #left { width: 3fr; height: 1fr; }
    #side { width: 2fr; padding: 0 1; }
    #title { text-style: bold; }
    #quest { margin-top: 1; }
    #status { margin: 1 0; min-height: 3; }
    #line { color: $text-muted; min-height: 2; }
    #tree { height: 1fr; border: round $primary-darken-2; }
    ProgressBar Bar { width: 1fr; }
    """

    def __init__(self, opening, variation=None):
        super().__init__()
        self.opening = opening
        self.variation = variation
        self.color = opening.color
        self.progress = deck.load(DECK)
        self.leaf = None
        self.node = opening.start
        self.mode = "browse"
        self.mistakes = 0
        self.tries = 0
        self.score = 0
        self.streak = 0
        self.waiting = None

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="left"):
                yield BoardView(id="board")
                yield Static(legend(["last", "hint", "wrong", "selected"]))
            with Vertical(id="side"):
                yield Static(id="title")
                yield ProgressBar(show_eta=False, id="progress")
                yield Static(id="quest")
                yield Static(id="status")
                yield Static(id="line")
                yield Tree("", id="tree")
        yield Footer()

    def on_mount(self):
        self.board = self.query_one(BoardView)
        self.board.flipped = self.color == chess.BLACK
        self.fill_tree()
        target = self.find(self.variation) if self.variation else None
        if target:
            self.browse(target)
        else:
            self.action_next_line()

    def find(self, name):
        stack = [self.opening.root]
        while stack:
            node = stack.pop()
            if node.name == name:
                return node
            stack += node.children.values()
        return None

    # the side panel

    def card(self, leaf):
        return self.progress.get(self.opening.key(leaf, self.color))

    def update_title(self):
        side = "White" if self.color == chess.WHITE else "Black"
        leaves = self.opening.leaves
        learned = sum(1 for leaf in leaves if deck.stars(self.card(leaf)))
        due = sum(
            1 for leaf in leaves
            if (c := self.card(leaf)) and c.get("box", 0) and deck.is_due(c)
        )
        self.query_one("#title").update(
            f"{self.opening.family}  [dim]as {side}[/dim]   "
            f"score [b]{self.score}[/b]   streak [b]{self.streak}[/b]\n"
            f"[dim]{learned} of {len(leaves)} lines learned, {due} to review today[/dim]"
        )
        bar = self.query_one(ProgressBar)
        bar.update(total=len(leaves), progress=learned)

    def fill_tree(self):
        tree = self.query_one(Tree)
        tree.clear()
        self.tree_nodes = {id(self.opening.root): tree.root}
        family = self.opening.family
        tree.root.set_label(f"{family}  [dim]{len(self.opening.leaves)} lines[/dim]")
        tree.root.data = self.opening.root

        def label(node):
            text = node.numbered()
            if node.name:
                text += f"  [cyan]{short(node.name, family)}[/cyan]"
            if not node.children:
                n = deck.stars(self.card(node))
                text += f"  [yellow]{'★' * n}[/yellow][dim]{'☆' * (3 - n)}[/dim]"
            return text

        def add(parent, node, depth):
            for child in node.branches():
                if child.children:
                    branch = parent.add(label(child), data=child, expand=depth < 2)
                    self.tree_nodes[id(child)] = branch
                    add(branch, child, depth + 1)
                else:
                    self.tree_nodes[id(child)] = parent.add_leaf(label(child), data=child)

        add(tree.root, self.opening.root, 0)
        tree.root.expand()
        self.update_title()

    def say(self, text):
        self.query_one("#status").update(text)

    def show_line(self):
        moves = []
        for n in self.node.path():
            text = n.numbered() if n.parent.ply % 2 == 0 or not moves else n.san
            moves.append(f"[b]{text}[/b]" if n is self.node else text)
        name = self.node.label()
        self.query_one("#line").update(
            " ".join(moves) + (f"\n[cyan]{name}[/cyan]" if name else "")
        )

    # training a line

    def start_line(self, leaf, mode=None):
        self.cancel_wait()
        self.leaf = leaf
        card = self.card(leaf)
        self.mode = mode or ("drill" if card and card.get("history") else "learn")
        self.mistakes = 0
        self.tries = 0
        self.node = self.opening.start
        self.board.player = {self.color}
        self.board.show(chess.Board())
        name = short(leaf.label(), self.opening.family)
        if self.mode == "learn":
            how = "[green]new line[/green]: follow the green squares"
        else:
            how = "[yellow]from memory[/yellow]: play the line without help"
        n = deck.stars(card)
        self.query_one("#quest").update(
            f"[b]{name}[/b]  [yellow]{'★' * n}[/yellow][dim]{'☆' * (3 - n)}[/dim]\n{how}"
        )
        first = "Your move" if self.color == chess.WHITE else ""
        self.say(first if self.mode == "drill" else "")
        self.advance()

    def expected(self):
        path = self.leaf.path()
        return path[self.node.ply] if self.node.ply < len(path) else None

    def advance(self):
        self.show_line()
        nxt = self.expected()
        if nxt is None:
            return self.finish()
        if self.board.board.turn != self.color:
            self.board.mark({})
            self.waiting = self.set_timer(0.5, self.reply)
            return
        if self.mode == "learn":
            self.show_hint(nxt)
            self.say(f"Play [b]{nxt.san}[/b]")

    def show_hint(self, node):
        self.board.mark({node.move.from_square: "hint", node.move.to_square: "hint"})

    def reply(self):
        self.waiting = None
        nxt = self.expected()
        self.go(nxt)
        news = f"  [cyan]{nxt.name}[/cyan]" if nxt.name else ""
        self.say(f"They answer [b]{nxt.san}[/b]{news}")
        self.advance()

    def go(self, node):
        self.node = node
        self.board.show(node.board())
        # the tree follows: where you are in the opening
        tree_node = self.tree_nodes.get(id(node))
        if tree_node:
            parent = tree_node.parent
            while parent:
                parent.expand()
                parent = parent.parent
            self.query_one(Tree).move_cursor(tree_node)

    def finish(self):
        self.board.player = set()
        key = self.opening.key(self.leaf, self.color)
        if self.mode == "learn":
            self.say(
                "[green]Line seen.[/green] Now from memory: it starts again in a moment"
            )
            self.waiting = self.set_timer(1.6, lambda: self.start_line(self.leaf, "drill"))
            return
        right = self.mistakes == 0
        card = self.progress.setdefault(key, {"id": key})
        deck.answer(card, right)
        deck.save(self.progress, DECK)
        if right:
            bonus = 20 * (1 + deck.stars(card))
            self.score += bonus
            n = deck.stars(card)
            self.say(
                f"[green b]Perfect![/green b] +{bonus}  "
                f"[yellow]{'★' * n}[/yellow]  back in {deck.INTERVALS[card['box']]} days"
                "\n[dim]n: next line[/dim]"
            )
        else:
            self.say(
                f"[yellow]Done with {self.mistakes} slip(s)[/yellow]: it comes back tomorrow"
                "\n[dim]r: once more   n: next line[/dim]"
            )
        self.fill_tree()

    def on_board_view_moved(self, event):
        move = event.move
        if self.mode == "browse":
            child = self.node.children.get(move.uci())
            if child:
                self.go(child)
                self.browse_info()
            else:
                self.say(f"[red]{self.node.board().san(move)}[/red] isn't a line of this opening")
            return
        nxt = self.expected()
        if nxt is None or self.waiting:
            return
        san = self.board.board.san(move)
        if move == nxt.move:
            self.tries = 0
            self.streak += 1
            self.score += 5 * (1 + min(self.streak, 20) // 5)
            self.go(nxt)
            news = f"  [cyan]{nxt.name}[/cyan]" if nxt.name else ""
            self.say(f"[green]✔ {san}[/green]{news}")
            self.update_title()
            self.advance()
            return
        other = self.node.children.get(move.uci())
        if other:
            self.say(
                f"[yellow]{san}[/yellow] is book too ([cyan]"
                f"{short(other.label() or other.leaves()[0].label(), self.opening.family)}"
                "[/cyan]), but this line goes another way"
            )
            return
        self.streak = 0
        self.mistakes += 1
        self.tries += 1
        marks = {move.to_square: "wrong"}
        if self.tries >= 2 or self.mode == "learn":
            marks |= {nxt.move.from_square: "hint", nxt.move.to_square: "hint"}
        self.board.mark(marks)
        self.say(f"[red]✘ {san}[/red] isn't the move" + ("" if self.tries < 2 and self.mode != "learn" else ": the green one"))
        self.update_title()

    # browsing the tree

    def browse(self, node):
        self.cancel_wait()
        self.mode = "browse"
        self.leaf = None
        self.board.player = {chess.WHITE, chess.BLACK}
        self.go(node)
        self.query_one("#quest").update(
            "[b]Browsing[/b]: click a move or a branch of the tree; "
            "t trains the lines from here"
        )
        self.browse_info()

    def browse_info(self):
        self.show_line()
        children = self.node.branches()
        marks = {}
        parts = []
        for c in children:
            marks[c.move.to_square] = "hint"
            name = short(c.label() or c.leaves()[0].label(), self.opening.family)
            parts.append(f"[b]{c.san}[/b] [dim]{name}, {c.size()} lines[/dim]")
        self.board.mark(marks)
        self.say("next: " + ("\n      ".join(parts) if parts else "the end of the line"))

    def on_tree_node_selected(self, event):
        node = event.node.data
        if node is None:
            return
        if not node.children:
            self.start_line(node)
        else:
            self.browse(node)

    def cancel_wait(self):
        if self.waiting:
            self.waiting.stop()
            self.waiting = None

    # actions

    def lines_from(self, node):
        leaves = set(map(id, node.leaves()))
        return [leaf for leaf in self.opening.leaves if id(leaf) in leaves]

    def pick(self, leaves):
        due = [
            leaf for leaf in leaves
            if (c := self.card(leaf)) and c.get("history") and deck.is_due(c)
        ]
        if due:
            return min(due, key=lambda leaf: self.card(leaf)["due"])
        new = [leaf for leaf in leaves if not self.card(leaf)]
        if new:
            return new[0]
        return random.choice(leaves)

    def action_next_line(self):
        self.start_line(self.pick(self.opening.leaves))

    def action_train_here(self):
        self.start_line(self.pick(self.lines_from(self.node)))

    def action_restart(self):
        if self.leaf:
            self.start_line(self.leaf, "drill")

    def action_hint(self):
        nxt = self.expected() if self.leaf else None
        if nxt and self.board.board.turn == self.color:
            self.mistakes += 1
            self.show_hint(nxt)
            self.say(f"Play [b]{nxt.san}[/b] [dim](a hint counts as a slip)[/dim]")

    def action_switch_color(self):
        self.color = not self.color
        self.board.flipped = self.color == chess.BLACK
        self.fill_tree()
        self.action_next_line()

    def action_back(self):
        if self.mode == "browse" and self.node.parent:
            self.go(self.node.parent)
            self.browse_info()

    def action_flip(self):
        self.board.flip()

    def action_explore(self):
        from explore import ExploreScreen

        self.app.push_screen(ExploreScreen(self.node.board()))

    def action_web(self):
        fen = self.node.board().fen().replace(" ", "_")
        open_url(f"https://lichess.org/analysis/standard/{fen}")
