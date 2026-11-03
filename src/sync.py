# chess-sync lichess|chesscom USER: every game of USER into
# $CHESS_DIR/games/SITE-USER.pgn, a database for En Croissant, ChessX and
# chess-review; later runs fetch only the new games
import argparse
import io
import json
import sys
from datetime import datetime, timezone

import chess.pgn

from common import CHESS_DIR, get_json, lichess_token, request


def game_id(game):
    return game.headers.get("Link") or game.headers.get("Site", "")


def lichess(user, state):
    since = state.get("since", 0)
    url = f"https://lichess.org/api/games/user/{user}?since={since}&sort=dateAsc&opening=true"
    # a stream: the games are written as they come
    with request(url, "application/x-chess-pgn", token=lichess_token()) as r:
        stream = io.TextIOWrapper(r, encoding="utf-8")
        while game := chess.pgn.read_game(stream):
            h = game.headers
            when = datetime.strptime(
                f"{h['UTCDate']} {h['UTCTime']}", "%Y.%m.%d %H:%M:%S"
            )
            state["since"] = int(when.replace(tzinfo=timezone.utc).timestamp() * 1000)
            yield game


def chesscom(user, state):
    base = f"https://api.chess.com/pub/player/{user.lower()}"
    archives = get_json(f"{base}/games/archives")["archives"]
    done = set(state.get("months", []))
    for url in archives:
        if url in done:
            continue
        for g in get_json(url)["games"]:
            if g.get("rules") == "chess" and "pgn" in g:
                yield chess.pgn.read_game(io.StringIO(g["pgn"]))
        # the current month still grows: fetched again next time
        if url != archives[-1]:
            done.add(url)
    state["months"] = sorted(done)


def main():
    p = argparse.ArgumentParser(
        prog="chess-sync", description="Download all of a user's games"
    )
    p.add_argument("site", choices=["lichess", "chesscom"])
    p.add_argument("user")
    args = p.parse_args()

    out = CHESS_DIR / "games"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{args.site}-{args.user.lower()}.pgn"
    state_path = out / f".{args.site}-{args.user.lower()}.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    seen = set(state.get("ids", []))

    fetch = lichess if args.site == "lichess" else chesscom
    new = 0
    # what was written is remembered even when stopped (Ctrl-C) halfway
    try:
        with path.open("a") as f:
            for game in fetch(args.user, state):
                if game_id(game) in seen:
                    continue
                print(game, file=f, end="\n\n")
                seen.add(game_id(game))
                new += 1
                print(f"\r  {new} games", end="", file=sys.stderr)
    except KeyboardInterrupt:
        print("\r  stopped, run it again to go on", file=sys.stderr)
    finally:
        state["ids"] = sorted(seen)
        state_path.write_text(json.dumps(state))
    print(f"\r{new} new games, {len(seen)} in {path}")


if __name__ == "__main__":
    main()
