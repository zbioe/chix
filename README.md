# chix

Chess to learn and train, on Nix:

- **chess-openings**: a window where you learn an opening by its name
  (`chess-openings bishop`). You learn it line by line, and every variation
  is there. The board shows the move to play with an arrow. Then you play the
  same line from memory, and it comes back on the days spaced repetition
  says. You can also walk the whole tree of variations, and play on past
  the book: Stockfish's lines and eval bar, the moves people play there
  (Lichess or masters' games, with their results), and the traps (moves
  played a lot that the engine refutes).
- **chess**: a terminal app, with mouse support, that covers:
  - the openings;
  - your Lichess and chess.com games, reviewed as Lichess does (accuracy,
    mistakes, the better move);
  - your mistakes, to find again;
  - puzzles, recorded on your Lichess account;
  - the opening explorer, next to an engine.
- **chess-review** and **chess-sync**: the review and your games, run from
  the shell.
- **chess-tui**: plays Lichess or an engine in the terminal.
- **engines**: stockfish, lc0, Maia 1100 to 1900 (Lc0 playing like people of
  that rating) and gnuchess.

Your games and progress are kept in `$CHESS_DIR` (by default `~/chess`).

## Use

```sh
nix run github:zbioe/chix#chix -- openings   # or: nix shell, then chess-openings
```

With home-manager:

```nix
{
  inputs.chix = {
    url = "github:zbioe/chix";
    inputs.nixpkgs.follows = "nixpkgs";
  };
  # modules = [ inputs.chix.homeModules.default ];
}
```

```nix
programs.chix = {
  enable = true;
  lichess.user = "you";
  # a string, so the token stays out of the store
  lichess.tokenFile = config.sops.secrets.lichess-token.path;
  chesscom.user = "you";
  desktop.terminal = "foot";        # launchers for `chess` and chess-tui
  desktop.webApp = "brave --app=";  # launchers for Lichess and chess.com
  engines.seedGuis = true;          # adds the engines to En Croissant and ChessX
};
```

The Lichess token needs these scopes: `puzzle:read`, `puzzle:write` and
`board:play`. Never give it `bot:play`.

## Develop

```sh
nix develop                    # the Python of the package, and ruff
python3 src/gui.py bishop      # the window, from the sources
python3 src/app.py             # the terminal app
nix flake check                # lint, and a smoke test of both
```

To try the module from a checkout:

```sh
nix build .#homeConfigurations.HOST.activationPackage --override-input chix path:$HOME/dev/chix
```
