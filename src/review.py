# chess-review lichess|chesscom USER [-n N] | chess-review FILE.pgn: the
# engine goes through each game, marks inaccuracies, mistakes and blunders
# with the better move, and writes the annotated PGN to $CHESS_DIR/reviews
import argparse
import io
import math
import re
import sys
import urllib.parse
from pathlib import Path

import chess
import chess.pgn

from common import CHESS_DIR, ENGINES, Engine, get, get_json, is_maia, lichess_token

# drops in win chance (points of 100) that make a move ?!, ? and ??,
# Lichess' thresholds
JUDGEMENTS = [
    (15, "??", chess.pgn.NAG_BLUNDER),
    (10, "?", chess.pgn.NAG_MISTAKE),
    (5, "?!", chess.pgn.NAG_DUBIOUS_MOVE),
]


def read_pgns(text):
    stream = io.StringIO(text)
    games = []
    while game := chess.pgn.read_game(stream):
        games.append(game)
    return games


def lichess_games(user, n):
    q = urllib.parse.urlencode(
        {"max": n, "opening": "true", "clocks": "false", "evals": "false"}
    )
    url = f"https://lichess.org/api/games/user/{user}?{q}"
    return read_pgns(get(url, "application/x-chess-pgn", token=lichess_token()))


def chesscom_games(user, n):
    base = f"https://api.chess.com/pub/player/{user.lower()}"
    archives = get_json(f"{base}/games/archives")["archives"]
    games = []
    for url in reversed(archives):
        month = get_json(url)["games"]
        for g in reversed(month):
            if g.get("rules") == "chess" and "pgn" in g:
                games += read_pgns(g["pgn"])
            if len(games) == n:
                return games
    return games


def win_chance(cp):
    cp = max(-1000, min(1000, cp))
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def move_accuracy(drop):
    return max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * drop) - 3.1669))


def white_cp(board, info):
    if board.is_checkmate():
        return -10000 if board.turn else 10000
    if board.is_game_over():
        return 0
    return info["score"].white().score(mate_score=10000)


def describe(cp):
    if abs(cp) >= 9000:
        return f"#{'-' if cp < 0 else ''}{(10000 - abs(cp) + 1) // 2}"
    return f"{cp / 100:+.2f}"


def opening(h):
    if "Opening" in h:
        return h["Opening"]
    # chess.com names it only in the URL
    slug = h.get("ECOUrl", "").rsplit("/", 1)[-1]
    name = re.split(r"\.\.\.|-\d+\.", slug)[0].replace("-", " ")
    return f"{h.get('ECO', '')} {name}".strip()


def review(game, engine):
    board = game.board()
    nodes = list(game.mainline())
    # a PGN reviewed before: its marks and lines are made again
    for node in nodes:
        node.nags.clear()
        del node.parent.variations[1:]
    infos = []
    for i in range(len(nodes) + 1):
        b = nodes[i - 1].board() if i else board
        info = {} if b.is_game_over() else engine.analyse(b)
        infos.append((b, info, white_cp(b, info)))
        print(f"\r  move {i}/{len(nodes)}", end="", file=sys.stderr)
    print("\r\033[K", end="", file=sys.stderr)

    stats = {chess.WHITE: [], chess.BLACK: []}
    marks = {chess.WHITE: [], chess.BLACK: []}
    for i, node in enumerate(nodes):
        before, info, cp_before = infos[i]
        _, _, cp_after = infos[i + 1]
        mover = before.turn
        sign = 1 if mover == chess.WHITE else -1
        drop = max(0.0, win_chance(sign * cp_before) - win_chance(sign * cp_after))
        stats[mover].append(move_accuracy(drop))
        node.comment = f"[%eval {describe(cp_after)}]"
        best = info.get("pv", [None])[0]
        if best is None or best == node.move:
            continue
        for threshold, symbol, nag in JUDGEMENTS:
            if drop >= threshold:
                node.nags.add(nag)
                line = node.parent.add_variation(best)
                for m in info["pv"][1:8]:
                    line = line.add_variation(m)
                num = f"{before.fullmove_number}{'.' if mover else '...'}"
                marks[mover].append(
                    (
                        symbol,
                        f"{num}{before.san(node.move)}{symbol}",
                        describe(cp_before),
                        describe(cp_after),
                        before.san(best),
                    )
                )
                break
    return stats, marks


def report(game, stats, marks, path):
    h = game.headers
    print(
        f"\n{h.get('White')} ({h.get('WhiteElo', '?')}) - {h.get('Black')} ({h.get('BlackElo', '?')})  {h.get('Result')}"
    )
    print(f"  {opening(h)}  {h.get('Link') or h.get('Site', '')}")
    for side, name in ((chess.WHITE, "White"), (chess.BLACK, "Black")):
        acc = sum(stats[side]) / len(stats[side]) if stats[side] else 100
        counts = "  ".join(
            f"{sum(1 for m in marks[side] if m[0] == s)}{s}"
            for _, s, _ in reversed(JUDGEMENTS)
        )
        print(f"  {name}: accuracy {acc:.0f}%  {counts}")
        for symbol, move, before, after, best in marks[side]:
            if symbol != "?!":
                print(f"    {move:<12} {before:>6} -> {after:<6} best {best}")
    print(f"  {path}")


def filename(game):
    h = game.headers
    site = h.get("Link") or h.get("Site", "")
    ident = site.rstrip("/").rsplit("/", 1)[-1] or "game"
    name = f"{h.get('Date', '').replace('.', '-')}-{h.get('White')}-{h.get('Black')}-{ident}"
    return re.sub(r"[^\w.-]+", "_", name) + ".pgn"


def main():
    p = argparse.ArgumentParser(
        prog="chess-review", description="Engine review of your games"
    )
    p.add_argument("source", help="lichess, chesscom or a PGN file")
    p.add_argument("user", nargs="?", help="whose games (lichess, chesscom)")
    p.add_argument("-n", type=int, default=1, help="how many of the latest games")
    p.add_argument(
        "--time", type=float, default=0.3, help="engine seconds per position"
    )
    # Maia guesses people's moves, its evals don't judge them
    p.add_argument(
        "--engine",
        default="stockfish",
        choices=sorted(e for e in ENGINES if not is_maia(e)),
    )
    p.add_argument(
        "--upload",
        action="store_true",
        help="also import each game into Lichess, for its board",
    )
    args = p.parse_args()

    if args.source in ("lichess", "chesscom"):
        if not args.user:
            p.error(f"{args.source} needs a user")
        games = (lichess_games if args.source == "lichess" else chesscom_games)(
            args.user, args.n
        )
    else:
        games = read_pgns(Path(args.source).read_text())
    if not games:
        sys.exit("chess-review: no games")

    out = CHESS_DIR / "reviews"
    out.mkdir(parents=True, exist_ok=True)
    engine = Engine(args.engine, args.time)
    try:
        for game in games:
            original = str(game)
            stats, marks = review(game, engine)
            path = out / filename(game)
            path.write_text(str(game) + "\n")
            report(game, stats, marks, path)
            if args.upload:
                url = get_json(
                    "https://lichess.org/api/import",
                    data={"pgn": original},
                    token=lichess_token(),
                )["url"]
                print(f"  {url}")
    finally:
        engine.quit()


if __name__ == "__main__":
    main()
