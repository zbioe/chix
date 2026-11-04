# home-manager: programs.chix. The commands with your users and token, the
# launcher's entries, and the engines added to En Croissant and ChessX
# the commands are built with the home's nixpkgs
{ chess-openings, maia }:
{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.programs.chix;

  # what En Croissant and ChessX list. Maia plays from its policy alone: one
  # node a move
  gui =
    let
      engine = id: name: go: settings: {
        inherit
          id
          name
          go
          settings
          ;
        command = "${cfg.engines.binDir}/${if id == "gnuchess" then "gnuchessu" else id}";
      };
    in
    [
      (engine "stockfish" "Stockfish" { t = "Infinite"; } {
        MultiPV = 3;
        Threads = 8;
        Hash = 512;
      })
      (engine "lc0" "Lc0" { t = "Infinite"; } {
        MultiPV = 3;
        Threads = 2;
      })
      (engine "gnuchess" "GNU Chess" null { Hash = 64; })
    ]
    ++ map (
      n:
      engine n "Maia ${lib.removePrefix "maia-" n}"
        {
          t = "Nodes";
          c = 1;
        }
        {
          MultiPV = 1;
          Threads = 1;
        }
      // {
        elo = lib.toInt (lib.removePrefix "maia-" n);
      }
    ) cfg.engines.package.maia;

  entry = name: comment: exec: {
    inherit name comment exec;
    icon = "chess";
    categories = [
      "Game"
      "BoardGame"
    ];
  };
in
{
  options.programs.chix = {
    enable = lib.mkEnableOption "chix: chess openings learned by name, your games reviewed, training and puzzles";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ./package.nix {
        inherit chess-openings;
        engines = cfg.engines.package;
        users = lib.concatStringsSep " " (
          lib.optional (cfg.lichess.user != null) "lichess:${cfg.lichess.user}"
          ++ lib.optional (cfg.chesscom.user != null) "chesscom:${cfg.chesscom.user}"
        );
        inherit (cfg.lichess) tokenFile;
      };
      defaultText = lib.literalExpression "chix, with the engines, users and token set here";
      description = "The commands.";
    };

    lichess.user = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "Your Lichess user: your games, and the explorer's \"you\".";
    };
    lichess.tokenFile = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      example = "/run/user/1000/secrets/lichess-token";
      description = ''
        A file holding a Lichess token (a string, so it stays out of the
        store): the opening explorer, puzzles recorded on your account,
        playing from chess-tui. Scopes: puzzle:read, puzzle:write,
        board:play; never bot:play.
      '';
    };
    chesscom.user = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "Your chess.com user: your games.";
    };

    engines = {
      package = lib.mkOption {
        type = lib.types.package;
        default = pkgs.callPackage ./engines.nix { inherit maia; };
        defaultText = lib.literalExpression "stockfish, lc0, maia-1100..1900 and gnuchess";
        description = "The UCI engines, one command each, with `passthru.maia` naming the Maia ones.";
      };
      install = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = "Put the engines in the home profile (off when the system has them).";
      };
      binDir = lib.mkOption {
        type = lib.types.str;
        default = "${config.home.profileDirectory}/bin";
        defaultText = lib.literalExpression ''"''${config.home.profileDirectory}/bin"'';
        description = "Where En Croissant and ChessX run the engines from: a path that outlives rebuilds.";
      };
      seedGuis = lib.mkEnableOption ''
        adding the engines to En Croissant and ChessX at each switch (what you
        change or remove there is kept, but an engine removed comes back)'';
    };

    desktop = {
      terminal = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "foot";
        description = "What runs a command in a terminal (`foot`, `kitty`, `alacritty -e`): launcher entries for `chess` and chess-tui.";
      };
      webApp = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "brave --app=";
        description = "What opens a URL as an app, the URL appended: launcher entries for Lichess and chess.com.";
      };
    };
  };

  config = lib.mkIf cfg.enable {
    home.packages = [ cfg.package ] ++ lib.optional cfg.engines.install cfg.engines.package;

    home.activation.chixEngines = lib.mkIf cfg.engines.seedGuis (
      lib.hm.dag.entryAfter [ "writeBoundary" ] ''
        run ${cfg.package.python}/bin/python3 ${./seed.py} ${pkgs.writeText "chix-gui-engines.json" (builtins.toJSON gui)}
      ''
    );

    xdg.desktopEntries = lib.mkMerge [
      {
        chess-openings =
          entry "Chess Openings" "Learn an opening by its name, every variation"
            "chess-openings";
      }
      (lib.mkIf (cfg.desktop.terminal != null) {
        chess = entry "Chess" "Your games reviewed, training and puzzles" "${cfg.desktop.terminal} chess";
        chess-tui =
          entry "Chess (terminal)" "Play Lichess or an engine in the terminal"
            "${cfg.desktop.terminal} chess-tui";
      })
      # chess.com has no API to play: its site in a window of its own
      (lib.mkIf (cfg.desktop.webApp != null) {
        chess-com =
          entry "Chess.com" "Play on chess.com"
            "${cfg.desktop.webApp}https://www.chess.com/play/online";
        lichess = entry "Lichess" "Play on lichess.org" "${cfg.desktop.webApp}https://lichess.org";
      })
    ];
  };
}
