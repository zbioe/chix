# chess-review lichess|chesscom USER [-n N] | chess-review FILE.pgn [--me NAME]:
# an engine goes through each game and judges it as Lichess does (accuracy,
# by phase too; inaccuracies, mistakes, blunders), says where you left the
# opening book and what kind of mistakes you make. The annotated PGN goes to
# $CHESS_DIR/reviews; your mistakes and blunders become chess-train cards
import argparse
import io
import json
import re
import sys
import urllib.error
import urllib.parse
from collections import Counter
from pathlib import Path

import chess
import chess.pgn

import analysis as an
import deck
from common import CHESS_DIR, ENGINES, Engine, get, get_json, is_maia, lichess_token

PHASES = ("opening", "middlegame", "endgame")


def read_pgns(text):
    stream = io.StringIO(text)
    games = []
    while game := chess.pgn.read_game(stream):
        games.append(game)
    return games


def lichess_games(user, n):
    q = urllib.parse.urlencode({"max": n, "opening": "true", "clocks": "false"})
    url = f"https://lichess.org/api/games/user/{user}?{q}"
    return read_pgns(get(url, "application/x-chess-pgn", token=lichess_token()))


def chesscom_games(user, n):
    base = f"https://api.chess.com/pub/player/{user.lower()}"
    archives = get_json(f"{base}/games/archives")["archives"]
    games = []
    for url in reversed(archives):
        for g in reversed(get_json(url)["games"]):
            if g.get("rules") == "chess" and "pgn" in g:
                games += read_pgns(g["pgn"])
            if len(games) == n:
                return games
    return games


def opening(h):
    if "Opening" in h:
        return h["Opening"]
    # chess.com names it only in the URL
    slug = h.get("ECOUrl", "").rsplit("/", 1)[-1]
    name = re.split(r"\.\.\.|-\d+\.", slug)[0].replace("-", " ")
    return f"{h.get('ECO', '')} {name}".strip()


def link(h):
    return h.get("Link") or h.get("Site", "")


def filename(game):
    h = game.headers
    ident = link(h).rstrip("/").rsplit("/", 1)[-1] or "game"
    name = f"{h.get('Date', '').replace('.', '-')}-{h.get('White')}-{h.get('Black')}-{ident}"
    return re.sub(r"[^\w.-]+", "_", name) + ".pgn"


def numbered(board, move):
    dots = "." if board.turn == chess.WHITE else "..."
    return f"{board.fullmove_number}{dots}{board.san(move)}"


def book(game, me, ratings):
    """Where you left the Lichess games of your level, or None while in book."""
    token = lichess_token()
    if not token:
        return "needs the Lichess token"
    board = game.board()
    theirs = None
    for node in game.mainline():
        if board.turn == me:
            q = {
                "fen": board.fen(),
                "ratings": ratings,
                "speeds": "blitz,rapid,classical",
                "moves": 6,
                "topGames": 0,
                "recentGames": 0,
            }
            url = "https://explorer.lichess.ovh/lichess?" + urllib.parse.urlencode(q)
            try:
                data = json.loads(get(url, token=token))
            except urllib.error.HTTPError as e:
                return f"explorer: HTTP {e.code}"
            total = data["white"] + data["draws"] + data["black"]
            # by SAN: the explorer writes castling as the king taking the rook
            counts = {
                m["san"]: m["white"] + m["draws"] + m["black"] for m in data["moves"]
            }
            played = counts.get(board.san(node.move), 0)
            # your last move was in book: their reply took the game out
            if total < 20 and theirs:
                return f"they left it with {theirs} ({total} games reached it)"
            if total < 20 or played < max(5, total * 0.02):
                usual = ", ".join(
                    f"{m['san']} {round(100 * counts[m['san']] / total)}%"
                    for m in data["moves"][:3]
                )
                return (
                    f"you left it at {numbered(board, node.move)} ({played} of {total} "
                    f"games); usual: {usual or 'no games here'}"
                )
        else:
            theirs = numbered(board, node.move)
        board.push(node.move)
    return None


def phase_accuracy(infos, boards, division):
    out = {}
    for phase in PHASES:
        idx = [
            i
            for i in range(len(boards))
            if phase in (an.phase_of(i, division), an.phase_of(i + 1, division))
        ]
        if len(idx) > 1:
            cps = [infos[i]["cp"] for i in idx]
            out[phase] = an.game_accuracy(cps, boards[idx[0]].turn)
    return out


def card_of(game, i, boards, infos, node, mark, phase, tags, me):
    h = game.headers
    before, after = infos[i], infos[i + 1]
    return {
        "id": f"{link(h)}#{i}",
        "fen": boards[i].fen(),
        "played": node.move.uci(),
        "best": before["pv"][0].uci(),
        "best_pv": [m.uci() for m in before["pv"][:8]],
        "reply_pv": [m.uci() for m in after.get("pv", [])[:6]],
        "before": an.describe(before["cp"], before["score"]),
        "after": an.describe(after["cp"], after["score"]),
        "mark": mark,
        "phase": phase,
        "tags": tags,
        "game": link(h),
        "opening": opening(h),
        "date": h.get("Date", ""),
        "opponent": h.get("Black" if me == chess.WHITE else "White"),
    }


def judge_moves(game, nodes, boards, infos, division):
    marks = []
    for i, node in enumerate(nodes):
        before, after = infos[i], infos[i + 1]
        mover = boards[i].turn
        node.comment = f"[%eval {an.describe(after['cp'], after['score'])}]"
        if before["score"] is None or after["score"] is None:
            continue
        mark = an.judge(before["score"], after["score"], mover)
        best = (before.get("pv") or [None])[0]
        if not mark or best is None or best == node.move:
            continue
        tags = an.tags(
            boards[i],
            before["pv"],
            boards[i + 1],
            after.get("pv", []),
            before["score"],
            after["score"],
            mover,
        )
        best_san = boards[i].san(best)
        node.nags.add(an.NAGS[mark])
        node.comment = (
            f"{an.NAMES[mark].capitalize()}. {best_san} was best. {node.comment}"
        )
        line = node.parent.add_variation(best)
        for m in before["pv"][1:8]:
            line = line.add_variation(m)
        marks.append(
            {
                "i": i,
                "node": node,
                "mover": mover,
                "mark": mark,
                "phase": an.phase_of(i, division),
                "tags": tags,
                "move": numbered(boards[i], node.move),
                "best": best_san,
                "before": an.describe(before["cp"], before["score"]),
                "after": an.describe(after["cp"], after["score"]),
            }
        )
    return marks


def review(game, engine, me, args, cards, stats):
    def progress(i, total):
        print(f"\r  analysing {i}/{total}", end="", file=sys.stderr)

    # a PGN reviewed before: its marks and lines are made again
    for node in game.mainline():
        node.nags.clear()
        del node.parent.variations[1:]
    nodes, boards, infos = an.analyse(game, engine, progress)
    print("\r\033[K", end="", file=sys.stderr)
    division = an.divide(boards)
    accuracy = an.game_accuracy([i["cp"] for i in infos], boards[0].turn)
    by_phase = phase_accuracy(infos, boards, division)
    marks = judge_moves(game, nodes, boards, infos, division)

    for m in marks:
        if m["mover"] != me or m["mark"] == an.INACCURACY:
            continue
        stats["phases"][m["phase"]] += 1
        stats["tags"].update(
            m["tags"] + (["endgame"] if m["phase"] == "endgame" else [])
        )
        if not args.no_train:
            card = card_of(
                game,
                m["i"],
                boards,
                infos,
                m["node"],
                m["mark"],
                m["phase"],
                m["tags"],
                me,
            )
            stats["new"] += deck.add(cards, card)

    path = CHESS_DIR / "reviews" / filename(game)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(game) + "\n")

    h = game.headers
    print(
        f"\n{h.get('White')} ({h.get('WhiteElo', '?')}) - {h.get('Black')} "
        f"({h.get('BlackElo', '?')})  {h.get('Result')}"
    )
    print(f"  {opening(h)}  {link(h)}")
    for side in (chess.WHITE, chess.BLACK):
        if side not in accuracy:
            continue
        who = "you" if side == me else ("White" if side else "Black")
        phases = "  ".join(
            f"{p} {round(by_phase[p][side])}%"
            for p in PHASES
            if side in by_phase.get(p, {})
        )
        count = Counter(m["mark"] for m in marks if m["mover"] == side)
        counts = " ".join(
            f"{count[k]}{k}" for k in (an.INACCURACY, an.MISTAKE, an.BLUNDER)
        )
        print(f"  {who:<5} accuracy {round(accuracy[side])}%  {counts}   {phases}")
        if side == me:
            stats["accuracy"].append(accuracy[side])
            for p, accs in by_phase.items():
                if side in accs:
                    stats["by_phase"][p].append(accs[side])
    if me is not None and args.book:
        print(f"  book  {book(game, me, args.ratings) or 'stayed in book'}")
    for side in [me] if me is not None else [chess.WHITE, chess.BLACK]:
        for m in marks:
            if m["mover"] != side or m["mark"] == an.INACCURACY:
                continue
            who = "" if me is not None else ("W " if side else "B ")
            print(
                f"    {who}{m['move'] + m['mark']:<14} {m['phase']:<10} "
                f"{m['before']:>6} -> {m['after']:<6} best {m['best']:<7} "
                f"{', '.join(m['tags'])}"
            )
    print(f"  {path}")
    if args.upload:
        url = get_json(
            "https://lichess.org/api/import",
            data={"pgn": str(game)},
            token=lichess_token(),
        )["url"]
        print(f"  {url}")


def summary(stats, games):
    if not stats["accuracy"]:
        return
    mean = sum(stats["accuracy"]) / len(stats["accuracy"])
    phases = "  ".join(
        f"{p} {round(sum(v) / len(v))}%" for p, v in stats["by_phase"].items() if v
    )
    print(f"\nyou, over {games} games: accuracy {round(mean)}%   {phases}")
    mistakes = "  ".join(f"{p} {stats['phases'][p]}" for p in PHASES)
    print(f"  mistakes and blunders by phase: {mistakes}")
    if stats["tags"]:
        common = stats["tags"].most_common()
        print("  of which: " + ", ".join(f"{t} {n}" for t, n in common))
        themes = []
        for tag, _ in common[:3]:
            themes += [t for t in an.THEMES.get(tag, []) if t not in themes][:2]
        print("  train them:")
        for t in themes[:4]:
            print(f"    chess-puzzle --theme {t} -n 10")
    if stats["new"]:
        print(f"  {stats['new']} new positions to find again: chess-train")


def main():
    p = argparse.ArgumentParser(
        prog="chess-review", description="Engine review of your games"
    )
    p.add_argument("source", help="lichess, chesscom or a PGN file")
    p.add_argument("user", nargs="?", help="whose games (lichess, chesscom)")
    p.add_argument("-n", type=int, default=1, help="how many of the latest games")
    p.add_argument("--me", help="your name in the PGN file's games")
    p.add_argument(
        "--time", type=float, default=0.5, help="engine seconds per position"
    )
    # Maia guesses people's moves, its evals don't judge them
    p.add_argument(
        "--engine",
        default="stockfish",
        choices=sorted(e for e in ENGINES if not is_maia(e)),
    )
    p.add_argument(
        "--ratings",
        default="1400,1600,1800,2000",
        help="the Lichess games your opening is compared with",
    )
    p.add_argument(
        "--no-book",
        dest="book",
        action="store_false",
        help="don't look for where you left the opening book",
    )
    p.add_argument(
        "--no-train",
        action="store_true",
        help="don't add your mistakes to chess-train",
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
        fetch = lichess_games if args.source == "lichess" else chesscom_games
        games = fetch(args.user, args.n)
        name = args.user
    else:
        games = read_pgns(Path(args.source).read_text())
        name = args.me
    if not games:
        sys.exit("chess-review: no games")

    engine = Engine(args.engine, args.time)
    cards = deck.load()
    stats = {
        "accuracy": [],
        "by_phase": {p: [] for p in PHASES},
        "phases": Counter(),
        "tags": Counter(),
        "new": 0,
    }
    try:
        for game in games:
            h = game.headers
            me = None
            if name:
                if h.get("White", "").lower() == name.lower():
                    me = chess.WHITE
                elif h.get("Black", "").lower() == name.lower():
                    me = chess.BLACK
            review(game, engine, me, args, cards, stats)
    finally:
        engine.quit()
        deck.save(cards)
    summary(stats, len(games))


if __name__ == "__main__":
    main()
