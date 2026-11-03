# chess-puzzle [lichess|chesscom] [--random | --theme THEME] [-n N]: the
# daily puzzle, or random ones (Lichess': of a theme, at a difficulty), solved
# on the terminal board; the replies are played for you. Lichess' are
# recorded on your account (rating included), as solved on the site: a wrong
# move, a hint or the solution makes it a failure
import argparse
import io
import readline  # noqa: F401  line editing for input()
import subprocess
import sys
import urllib.error
import urllib.parse

import chess
import chess.pgn

from common import clear, draw, get_json, lichess_token, post_json

HELP = "  MOVE (Nf3, e2e4)   h hint   s solution   web open it   q quit"


def lichess(args):
    if args.random:
        q = {"angle": args.theme, "difficulty": args.difficulty}
        url = "https://lichess.org/api/puzzle/next?" + urllib.parse.urlencode(q)
    else:
        url = "https://lichess.org/api/puzzle/daily"
    data = get_json(url, token=lichess_token())
    board = chess.Board()
    for san in data["game"]["pgn"].split():
        board.push_san(san)
    p = data["puzzle"]
    solution = [chess.Move.from_uci(m) for m in p["solution"]]
    about = f"Lichess {p['id']}, rated {p['rating']}: {', '.join(p['themes'])}"
    return p["id"], board, solution, about, f"https://lichess.org/training/{p['id']}"


def chesscom(args):
    url = "https://api.chess.com/pub/puzzle" + ("/random" if args.random else "")
    data = get_json(url)
    game = chess.pgn.read_game(io.StringIO(data["pgn"]))
    board = game.board()
    return None, board, list(game.mainline_moves()), data["title"], data["url"]


def parse(board, text):
    try:
        return board.parse_san(text)
    except ValueError:
        return chess.Move.from_uci(text)


def solve(board, solution, about, url):
    """(True solved clean | False failed | None left untried, whether quit)."""
    flipped = board.turn == chess.BLACK
    note = HELP
    failed = None
    i = 0
    while i < len(solution):
        clear()
        print(draw(board, flipped))
        print(f"\n  {about}\n  {'White' if board.turn else 'Black'} to play\n{note}\n")
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            return (False if failed else None), True
        expected = solution[i]
        if text == "q":
            return (False if failed else None), True
        if text == "h":
            piece = chess.piece_name(board.piece_type_at(expected.from_square))
            note = f"  the {piece} on {chess.square_name(expected.from_square)}"
            failed = True
            continue
        if text == "s":
            b = board.copy()
            note = "  " + " ".join(b.san_and_push(m) for m in solution[i:])
            failed = True
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
            failed = True
            continue
        failed = bool(failed)
        if board.is_checkmate():
            break
        i += 1
        if i < len(solution):
            note = f"  {board.san(solution[i])}, your move"
            board.push(solution[i])
            i += 1
    clear()
    print(draw(board, flipped))
    print(f"\n  {'solved' if not failed else 'done, not clean'}: {about}\n  {url}")
    return not failed, False


def record(puzzle_id, win, angle):
    token = lichess_token()
    if not token:
        print("  not recorded on Lichess: no token (dotnix.games.chess.lichess)")
        return
    try:
        res = post_json(
            f"https://lichess.org/api/puzzle/batch/{angle}",
            {"solutions": [{"id": puzzle_id, "win": win, "rated": True}]},
            token,
        )
    except urllib.error.HTTPError as e:
        sys.exit(f"chess-puzzle: not recorded on Lichess: HTTP {e.code}")
    diff = next((r.get("ratingDiff") for r in res.get("rounds", [])), None)
    result = "solved" if win else "failed"
    print(
        f"  recorded on Lichess as {result}, rating {diff:+d}"
        if diff is not None
        else f"  recorded on Lichess as {result}"
    )


def main():
    p = argparse.ArgumentParser(
        prog="chess-puzzle", description="Chess puzzles on the terminal"
    )
    p.add_argument(
        "site", nargs="?", choices=["lichess", "chesscom"], default="lichess"
    )
    p.add_argument(
        "--random", action="store_true", help="random puzzles, not the daily one"
    )
    p.add_argument(
        "--theme",
        help="Lichess only, random puzzles of a theme or opening: endgame, "
        "kingsideAttack, exposedKing, mateIn2, fork, Sicilian_Defense... "
        "(lichess.org/training/themes)",
    )
    p.add_argument(
        "--difficulty",
        choices=["easiest", "easier", "normal", "harder", "hardest"],
        default="normal",
        help="Lichess only, against your puzzle rating",
    )
    p.add_argument("-n", type=int, default=1, help="how many puzzles in a row")
    args = p.parse_args()
    if args.site == "chesscom" and args.theme:
        p.error("--theme is Lichess only")
    args.random = args.random or bool(args.theme) or args.n > 1

    for i in range(args.n):
        puzzle_id, *puzzle = (lichess if args.site == "lichess" else chesscom)(args)
        win, quit = solve(*puzzle)
        if puzzle_id and win is not None:
            record(puzzle_id, win, args.theme or "mix")
        if quit or i == args.n - 1:
            break
        try:
            if input("\n  Enter for the next one, q to stop: ").strip() == "q":
                break
        except (EOFError, KeyboardInterrupt):
            break
    print()


if __name__ == "__main__":
    main()
