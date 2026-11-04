# chess-openings: the openings in a window of their own. The same lines
# and progress as the terminal's (openings.json), on a board you drag pieces
# on: learn a line with arrows, play it from memory, walk every variation
import sys
from pathlib import Path

import chess
import chess.svg
import webview

import deck
from openings import DECK, Opening, fold, load, short

WEB = Path(__file__).parent / "web"


def side(color):
    return "white" if color == chess.WHITE else "black"


class Api:
    def __init__(self, query=""):
        self.query = query
        self.families = load()
        self.trees = {}

    def tree(self, family):
        if family not in self.trees:
            self.trees[family] = Opening(family, self.families[family])
        return self.trees[family]

    def pieces(self):
        return {
            ("w" if p.isupper() else "b") + p.upper(): chess.svg.piece(chess.Piece.from_symbol(p))
            for p in "PNBRQKpnbrqk"
        }

    def catalog(self):
        """Every opening, with its variations' names and your progress."""
        progress = deck.load(DECK)
        learned, due = {}, {}
        for key, card in progress.items():
            family = key.split(":")[1]
            if card.get("box", 0) > 0:
                learned[family] = learned.get(family, 0) + 1
            if card.get("history") and deck.is_due(card):
                due[family] = due.get(family, 0) + 1
        out = []
        for family, lines in self.families.items():
            opening = self.tree(family)
            board = opening.root.board()
            out.append(
                {
                    "family": family,
                    "eco": min(eco for eco, _, _ in lines),
                    "lines": len(opening.leaves),
                    "color": side(opening.color),
                    "moves": " ".join(n.numbered() for n in opening.root.path()),
                    "fen": board.fen(),
                    "learned": learned.get(family, 0),
                    "due": due.get(family, 0),
                    "search": fold(family),
                    "variations": sorted(
                        {short(name, family) for _, name, _ in lines if name != family}
                    ),
                }
            )
        return out

    def opening(self, family):
        opening = self.tree(family)
        nodes = []

        def add(node, parent):
            i = len(nodes)
            board = node.board()
            item = {
                "id": i,
                "parent": parent,
                "san": node.san,
                "uci": node.move.uci() if node.move else None,
                "numbered": node.numbered() if node.move else "",
                "fen": board.fen(),
                "check": board.is_check(),
                "name": short(node.name, family) if node.name else None,
                "label": short(node.label(), family),
                "eco": node.eco,
                "ply": node.ply,
                "size": node.size(),
                "path": " ".join(n.move.uci() for n in node.path()),
                "children": [],
            }
            nodes.append(item)
            for child in node.branches():
                item["children"].append(add(child, i))
            return i

        add(opening.start, None)
        root = len(opening.root.path())
        return {
            "family": family,
            "color": side(opening.color),
            "root": root,
            "nodes": nodes,
            "progress": self.progress(family),
        }

    def progress(self, family):
        return {
            k: c for k, c in deck.load(DECK).items() if k.split(":")[1] == family
        }

    def answer(self, key, right):
        cards = deck.load(DECK)
        card = cards.setdefault(key, {"id": key})
        deck.answer(card, right)
        deck.save(cards, DECK)
        return card

    def move(self, fen, uci):
        """A move off the book: its SAN, or None when it isn't legal."""
        board = chess.Board(fen)
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            return None
        if move not in board.legal_moves:
            promoted = chess.Move.from_uci(uci + "q") if len(uci) == 4 else None
            if promoted not in board.legal_moves:
                return None
            move = promoted
        return {"san": board.san(move), "uci": move.uci()}

    def dests(self, fen):
        out = {}
        for m in chess.Board(fen).legal_moves:
            out.setdefault(chess.square_name(m.from_square), []).append(
                chess.square_name(m.to_square)
            )
        return out

    def intervals(self):
        return deck.INTERVALS

    def initial(self):
        """What `chess-openings-gui NAME` searches for."""
        return self.query


def main():
    webview.create_window(
        "Chess Openings",
        str(WEB / "index.html"),
        js_api=Api(" ".join(sys.argv[1:])),
        width=1400,
        height=900,
        min_size=(900, 600),
        background_color="#161512",
    )
    webview.start(gui="gtk")


if __name__ == "__main__":
    main()
