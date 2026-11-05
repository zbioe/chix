# chess-openings: the openings in a window of their own. The same lines
# and progress as the terminal's (openings.json), on a board you drag pieces
# on: learn a line with arrows, play it from memory, walk every variation
import sys
import threading
from pathlib import Path

import chess
import chess.engine
import chess.svg
import webview

import analysis as an
import deck
from common import Engine, Explorer, ExplorerError, line_san, score_text
from openings import DECK, Opening, fold, load, short

WEB = Path(__file__).parent / "web"


def side(color):
    return "white" if color == chess.WHITE else "black"


def _reply(board, pv):
    """The answer to the line's first move, in SAN."""
    if len(pv) < 2:
        return None
    b = board.copy(stack=False)
    b.push(pv[0])
    return b.san(pv[1])


class Api:
    def __init__(self, query=""):
        self.query = query
        self.families = load()
        self.trees = {}
        self._names = None
        self._engine = None
        self._engine_lock = threading.Lock()
        # the position the board shows: older searches give up
        self._wanted = None
        self._explorers = {
            "lichess": Explorer(),
            "masters": Explorer("masters"),
        }

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
        san = board.san(move)
        board.push(move)
        return {"san": san, "uci": move.uci(), "fen": board.fen(), "check": board.is_check()}

    def dests(self, fen):
        out = {}
        for m in chess.Board(fen).legal_moves:
            out.setdefault(chess.square_name(m.from_square), []).append(
                chess.square_name(m.to_square)
            )
        return out

    def named(self, fen):
        """The name of a position, by any move order: (eco, name) or None."""
        if self._names is None:
            names = {}
            for lines in self.families.values():
                for eco, name, moves in lines:
                    board = chess.Board()
                    for m in moves:
                        board.push(m)
                    names[board.epd()] = (eco, name)
            self._names = names
        hit = self._names.get(chess.Board(fen).epd())
        return {"eco": hit[0], "name": hit[1]} if hit else None

    def explorer(self, fen, db="lichess", ratings="1600,1800,2000,2200,2500"):
        """What's played from here: each move's games and results."""
        explorer = self._explorers[db]
        explorer.ratings = ratings
        board = chess.Board(fen)
        try:
            data = explorer.query(board, moves=12)
        except ExplorerError as e:
            return {"error": str(e)}
        total = data["white"] + data["draws"] + data["black"]
        moves = []
        for m in data["moves"]:
            n = m["white"] + m["draws"] + m["black"]
            # by SAN: Lichess' UCI puts the castling king onto its rook
            move = board.parse_san(m["san"])
            moves.append(
                {
                    "uci": move.uci(),
                    "san": m["san"],
                    "games": n,
                    "share": n / total if total else 0,
                    "white": m["white"],
                    "draws": m["draws"],
                    "black": m["black"],
                    "rating": m.get("averageRating"),
                }
            )
        return {
            "db": db,
            "total": total,
            "white": data["white"],
            "draws": data["draws"],
            "black": data["black"],
            "opening": data.get("opening"),
            "moves": moves,
        }

    def analyse(self, fen, seconds=1.0, moves=None):
        """Stockfish's best lines here, or its verdict on the moves given
        (the explorer's): white-POV scores, the line each one leads to."""
        self._wanted = fen
        board = chess.Board(fen)
        if board.is_game_over():
            return {"fen": fen, "lines": [], "over": board.result()}
        root = [chess.Move.from_uci(u) for u in moves] if moves else None
        with self._engine_lock:
            if self._wanted != fen:
                return None
            if self._engine is None:
                self._engine = Engine("stockfish", seconds)
            with self._engine.uci.analysis(
                board,
                chess.engine.Limit(time=seconds),
                multipv=len(root) if root else 3,
                root_moves=root,
            ) as search:
                for _ in search:
                    # another position asked: this one gives up
                    if self._wanted != fen:
                        return None
                infos = search.multipv
        lines = []
        for info in infos:
            pv = info.get("pv") or []
            if not pv:
                continue
            score = info["score"].white()
            lines.append(
                {
                    "uci": pv[0].uci(),
                    "san": board.san(pv[0]),
                    "cp": an.cp_of(score),
                    "mate": score.mate(),
                    "text": score_text(info["score"]),
                    "pv": line_san(board, pv, limit=10),
                    "pvUci": [m.uci() for m in pv[:10]],
                    "reply": _reply(board, pv),
                    "depth": info.get("depth"),
                }
            )
        return {"fen": fen, "lines": lines}

    def intervals(self):
        return deck.INTERVALS

    def initial(self):
        """What `chess-openings NAME` searches for."""
        return self.query

    def close(self):
        if self._engine:
            self._engine.quit()


def main():
    api = Api(" ".join(sys.argv[1:]))
    window = webview.create_window(
        "Chess Openings",
        str(WEB / "index.html"),
        js_api=api,
        width=1400,
        height=900,
        min_size=(900, 600),
        background_color="#161512",
    )
    window.events.closed += api.close
    webview.start(gui="gtk")


if __name__ == "__main__":
    main()
