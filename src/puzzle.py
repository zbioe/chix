# chess-puzzle [lichess|chesscom] [--random]: the daily puzzle (or a random
# one) solved on the terminal board; the replies are played for you
import argparse
import io
import readline  # noqa: F401  line editing for input()
import subprocess

import chess
import chess.pgn

from common import clear, draw, get_json, lichess_token

HELP = "  MOVE (Nf3, e2e4)   h hint   s solution   web open it   q quit"


def lichess(random):
    url = "https://lichess.org/api/puzzle/" + ("next" if random else "daily")
    data = get_json(url, token=lichess_token())
    board = chess.Board()
    for san in data["game"]["pgn"].split():
        board.push_san(san)
    p = data["puzzle"]
    solution = [chess.Move.from_uci(m) for m in p["solution"]]
    about = f"Lichess {p['id']}, rated {p['rating']}: {', '.join(p['themes'])}"
    return board, solution, about, f"https://lichess.org/training/{p['id']}"


def chesscom(random):
    url = "https://api.chess.com/pub/puzzle" + ("/random" if random else "")
    data = get_json(url)
    game = chess.pgn.read_game(io.StringIO(data["pgn"]))
    return game.board(), list(game.mainline_moves()), data["title"], data["url"]


def parse(board, text):
    try:
        return board.parse_san(text)
    except ValueError:
        return chess.Move.from_uci(text)


def solve(board, solution, about, url):
    flipped = board.turn == chess.BLACK
    note = HELP
    i = 0
    while i < len(solution):
        clear()
        print(draw(board, flipped))
        print(f"\n  {about}\n  {'White' if board.turn else 'Black'} to play\n{note}\n")
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        expected = solution[i]
        if text == "q":
            return
        if text == "h":
            note = f"  the {chess.piece_name(board.piece_type_at(expected.from_square))} on {chess.square_name(expected.from_square)}"
            continue
        if text == "s":
            b = board.copy()
            note = "  " + " ".join(b.san_and_push(m) for m in solution[i:])
            continue
        if text == "web":
            subprocess.Popen(["xdg-open", url], stderr=subprocess.DEVNULL)
            continue
        try:
            move = parse(board, text)
        except ValueError:
            note = f"  not a move: {text}"
            continue
        board.push(move)
        # any mate solves it, not only the one in the solution
        if move != expected and not board.is_checkmate():
            board.pop()
            note = f"  {text} is not it, try again"
            continue
        if board.is_checkmate():
            break
        i += 1
        if i < len(solution):
            note = f"  {board.san(solution[i])}, your move"
            board.push(solution[i])
            i += 1
    clear()
    print(draw(board, flipped))
    print(f"\n  solved: {about}\n  {url}\n")


def main():
    p = argparse.ArgumentParser(
        prog="chess-puzzle", description="Chess puzzles on the terminal"
    )
    p.add_argument(
        "site", nargs="?", choices=["lichess", "chesscom"], default="lichess"
    )
    p.add_argument(
        "--random", action="store_true", help="a random puzzle, not the daily one"
    )
    args = p.parse_args()
    solve(*(lichess if args.site == "lichess" else chesscom)(args.random))


if __name__ == "__main__":
    main()
