# chess-train [-n N] [--phase P] [--tag T] [--all]: the positions where you
# went wrong (chess-review puts them here), to find the better move again.
# Any move as good as the engine's counts; found, a position waits longer
# before coming back, missed, it comes back tomorrow
import argparse
import readline  # noqa: F401  line editing for input()
import subprocess

import chess

import analysis as an
import deck
from common import Engine, clear, draw, line_san

HELP = "  MOVE (Nf3, e2e4)   h hint   s give up   web the game   q quit"


def parse(board, text):
    try:
        return board.parse_san(text)
    except ValueError:
        return chess.Move.from_uci(text)


def good_enough(engine, board, move):
    """The move keeps what the position had: not even an inaccuracy."""
    before = engine.analyse(board)["score"]
    after_board = board.copy()
    after_board.push(move)
    if after_board.is_checkmate():
        return True
    after = engine.analyse(after_board)["score"]
    return an.judge(before, after, board.turn) is None


def explain(card, board):
    best = [chess.Move.from_uci(m) for m in card["best_pv"]]
    played = chess.Move.from_uci(card["played"])
    after = board.copy()
    after.push(played)
    reply = [chess.Move.from_uci(m) for m in card["reply_pv"]]
    print(f"\n  best:  {line_san(board, best)}")
    print(
        f"  your {line_san(board, [played])} ({card['before']} -> {card['after']}) ",
        end="",
    )
    print(f"ran into: {line_san(after, reply)}" if reply else "")
    if card["tags"]:
        print(f"  {', '.join(card['tags'])}")


def drill(card, engine):
    """True found, False missed, None quit."""
    board = chess.Board(card["fen"])
    flipped = board.turn == chess.BLACK
    played = chess.Move.from_uci(card["played"])
    note = HELP
    hinted = False
    while True:
        clear()
        print(draw(board, flipped))
        print(
            f"\n  vs {card['opponent']}, {card['date']}, {card['opening']}"
            f"\n  you played {line_san(board, [played])}, a {an.NAMES[card['mark']]}"
            f" ({card['phase']}): find better\n{note}\n"
        )
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if not text:
            continue
        if text == "q":
            return None
        if text == "web":
            subprocess.Popen(["xdg-open", card["game"]], stderr=subprocess.DEVNULL)
            continue
        if text == "h":
            best = chess.Move.from_uci(card["best"])
            piece = chess.piece_name(board.piece_type_at(best.from_square))
            note = f"  the {piece} on {chess.square_name(best.from_square)}"
            hinted = True
            continue
        if text == "s":
            explain(card, board)
            return False
        try:
            move = parse(board, text)
            if move not in board.legal_moves:
                raise ValueError
        except ValueError:
            note = f"  not a move: {text}"
            continue
        if move == played:
            note = "  that's what you played: look again"
            continue
        right = move.uci() == card["best"] or good_enough(engine, board, move)
        print("\n  right" if right else f"\n  {text} isn't it")
        explain(card, board)
        return right and not hinted


def main():
    p = argparse.ArgumentParser(
        prog="chess-train", description="Find again the moves you missed"
    )
    p.add_argument("-n", type=int, default=20, help="at most this many positions")
    p.add_argument("--phase", choices=["opening", "middlegame", "endgame"])
    p.add_argument("--tag", help="only this kind: lost material, missed mate...")
    p.add_argument("--all", action="store_true", help="also the ones not due today")
    p.add_argument("--time", type=float, default=0.5, help="engine seconds to judge")
    args = p.parse_args()

    cards = deck.load()
    todo = list(cards.values()) if args.all else deck.due(cards)
    todo = [
        c
        for c in todo
        if (not args.phase or c["phase"] == args.phase)
        and (not args.tag or args.tag in c["tags"])
    ][: args.n]
    if not todo:
        print(f"nothing due ({len(cards)} positions); chess-review adds yours")
        return

    engine = Engine("stockfish", args.time)
    right = done = 0
    try:
        for card in todo:
            result = drill(card, engine)
            if result is None:
                break
            deck.answer(cards[card["id"]], result)
            deck.save(cards)
            done += 1
            right += result
            try:
                if input("\n  Enter for the next one, q to stop: ").strip() == "q":
                    break
            except (EOFError, KeyboardInterrupt):
                break
    finally:
        engine.quit()
    print(f"\n{right}/{done} found; {len(deck.due(cards))} still due today")


if __name__ == "__main__":
    main()
