# The openings load and build, the window's API answers, and the terminal
# app opens an opening and plays its first move; no network, no display
import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
os.environ.setdefault("CHESS_DIR", tempfile.mkdtemp())

import chess  # noqa: E402

import gui  # noqa: E402
from app import ChessApp  # noqa: E402
from board import BoardView  # noqa: E402
from openings import OpeningScreen, PickScreen  # noqa: E402

api = gui.Api("bishop")
catalog = api.catalog()
assert len(catalog) > 100, len(catalog)
for o in catalog:
    tree = api.opening(o["family"])
    root = tree["nodes"][tree["root"]]
    assert root["fen"] == o["fen"], o["family"]
bishop = api.opening("Bishop's Opening")
assert bishop["color"] == "white"
assert api.move(chess.STARTING_FEN, "e2e5") is None
assert api.move(chess.STARTING_FEN, "e2e4")["san"] == "e4"
key = "white:Bishop's Opening:e2e4 e7e5 f1c4 d7d5"
assert api.answer(key, True)["box"] == 1
assert key in api.progress("Bishop's Opening")
# a move order the book doesn't have still finds the position's name
italian = chess.Board()
for san in "Nf3 Nc6 e4 e5 Bc4".split():
    italian.push_san(san)
assert api.named(italian.fen())["name"].startswith("Italian Game"), api.named(italian.fen())
after = api.move(italian.fen(), "f8c5")
assert after["fen"].startswith("r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2"), after
best = api.analyse(italian.fen(), 0.1)["lines"]
assert len(best) == 3 and best[0]["pv"], best
judged = api.analyse(italian.fen(), 0.1, ["f8c5", "g8f6"])["lines"]
assert {line["uci"] for line in judged} == {"f8c5", "g8f6"}, judged
api.close()
print(f"window api: {len(catalog)} openings, names and the engine")


async def terminal():
    app = ChessApp(lambda app: PickScreen(app.families(), "bishop's opening"))
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, OpeningScreen), screen
        view = screen.query_one(BoardView)
        move = screen.expected().move
        view.post_message(BoardView.Moved(view, move))
        await pilot.pause()
        assert screen.node.move == move, screen.node
    print("terminal app: an opening opened and played")


asyncio.run(terminal())
