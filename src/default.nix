# Chess from the terminal, the GUIs and Emacs: chess-tui (play Lichess or an
# engine), chess-explore (an opening's whole tree), chess-review (Lichess and
# chess.com games annotated by an engine), chess-puzzle and chess-sync (every
# game of a user, as a database). The engines come with the host
# (pkgs/chess-engines) and are added to En Croissant and ChessX; Emacs'
# packages are zmacs' (lisp/chess.el)
{
  config,
  lib,
  pkgs,
  osConfig,
  ...
}:
let
  cfg = config.dotnix.games.chess;
  secrets = ../../../secrets/chess.yaml;
  token = config.sops.secrets.lichess-token.path;
  inherit (osConfig.dotnix.packages.games.chess) engines;

  # name -> UCI command; gnuchess speaks UCI as gnuchessu
  commands =
    lib.genAttrs (
      [
        "stockfish"
        "lc0"
      ]
      ++ engines.maia
    ) (n: "${engines}/bin/${n}")
    // {
      gnuchess = "${engines}/bin/gnuchessu";
    };

  # what En Croissant and ChessX list; the system profile's paths survive
  # rebuilds. Maia plays from its policy alone: one node a move
  gui =
    let
      engine = id: name: go: settings: {
        inherit
          id
          name
          go
          settings
          ;
        command = "/run/current-system/sw/bin/${if id == "gnuchess" then "gnuchessu" else id}";
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
      let
        rating = lib.removePrefix "maia-" n;
      in
      engine n "Maia ${rating}"
        {
          t = "Nodes";
          c = 1;
        }
        {
          MultiPV = 1;
          Threads = 1;
        }
      // {
        elo = lib.toInt rating;
      }
    ) engines.maia;

  python = pkgs.python3.withPackages (p: [ p.chess ]);

  tool =
    name: script:
    pkgs.writeShellApplication {
      inherit name;
      runtimeInputs = [ pkgs.xdg-utils ];
      text = ''
        export CHESS_ENGINES=${pkgs.writeText "chess-engines.json" (builtins.toJSON commands)}
        export CHESS_DIR="$HOME/chess"
        ${lib.optionalString cfg.lichess.enable "export LICHESS_TOKEN_FILE=${token}"}
        exec ${python}/bin/python3 ${./.}/${script} "$@"
      '';
    };

  # chess-tui [--engine NAME]: stockfish unless named; Maia searches no
  # deeper than one ply. The token is passed on each run, so a new one in
  # secrets/chess.yaml is the one used
  tui = pkgs.writeShellApplication {
    name = "chess-tui";
    text = ''
      declare -A engines=(${lib.concatStrings (lib.mapAttrsToList (n: c: "[${n}]=${c} ") commands)})
      name=stockfish
      if [[ ''${1:-} == --engine ]]; then
        name=''${2:?--engine NAME}
        shift 2
      fi
      if [[ -z ''${engines[$name]:-} ]]; then
        echo "chess-tui: no engine $name:" "$(printf '%s\n' "''${!engines[@]}" | sort | paste -sd ' ')" >&2
        exit 1
      fi
      args=(-e "''${engines[$name]}")
      [[ $name == maia-* ]] && args+=(-d 1)
      ${lib.optionalString cfg.lichess.enable ''args+=(-l "$(cat ${token})")''}
      exec ${lib.getExe pkgs.chess-tui} "''${args[@]}" "$@"
    '';
  };

  # what opens the terminal tools and the sites from the launcher
  terminal =
    {
      foot = "foot";
      alacritty = "alacritty -e";
      ghostty = "ghostty -e";
      kitty = "kitty";
    }
    .${config.dotnix.desktop.terminals.default};
  site =
    url:
    {
      brave = "brave --app=${url}";
      chromium = "chromium --app=${url}";
      librewolf = "librewolf --new-window ${url}";
    }
    .${osConfig.dotnix.desktop.browsers.default};

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
  options.dotnix.games.chess = {
    enable = lib.mkEnableOption "the chess tools (chess-tui, chess-explore, chess-review...)" // {
      default = osConfig.dotnix.packages.games.chess.enable;
    };
    lichess.enable = lib.mkEnableOption ''
      the Lichess token, `lichess-token` in secrets/chess.yaml: playing from
      chess-tui and Emacs, the opening explorer of chess-explore'';
  };

  config = lib.mkIf cfg.enable (
    lib.mkMerge [
      {
        home.packages = [
          tui
          (tool "chess-explore" "explore.py")
          (tool "chess-review" "review.py")
          (tool "chess-puzzle" "puzzle.py")
          (tool "chess-sync" "sync.py")
        ];

        # added once: what you change or remove there afterwards is kept,
        # except an engine removed comes back at the next switch
        home.activation.chessEngines = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
          run ${python}/bin/python3 ${./seed.py} ${pkgs.writeText "chess-gui-engines.json" (builtins.toJSON gui)}
        '';

        xdg.desktopEntries = lib.mkMerge [
          (lib.mkIf (config.dotnix.desktop.terminals.default != null) {
            chess-tui =
              entry "Chess (terminal)" "Play Lichess or an engine in the terminal"
                "${terminal} chess-tui";
            chess-explore =
              entry "Chess Openings" "Every move played from a position, with an engine"
                "${terminal} chess-explore";
            chess-puzzle =
              entry "Chess Puzzle" "The Lichess daily puzzle in the terminal"
                "${terminal} chess-puzzle";
          })
          # chess.com has no API to play: its site in a window of its own
          (lib.mkIf (osConfig.dotnix.desktop.browsers.default != null) {
            chess-com = entry "Chess.com" "Play on chess.com" (site "https://www.chess.com/play/online");
            lichess = entry "Lichess" "Play on lichess.org" (site "https://lichess.org");
          })
        ];
      }

      (lib.mkIf cfg.lichess.enable {
        assertions = [
          {
            assertion = builtins.pathExists secrets;
            message = "dotnix.games.chess.lichess needs secrets/chess.yaml (sops secrets/chess.yaml, key lichess-token)";
          }
        ];
        sops.secrets.lichess-token.sopsFile = secrets;
        # lichess.el reads it with auth-source
        sops.templates.authinfo = {
          path = "${config.home.homeDirectory}/.authinfo";
          content = ''
            machine lichess.org login lichess password ${config.sops.placeholder.lichess-token}
          '';
        };
      })
    ]
  );
}
