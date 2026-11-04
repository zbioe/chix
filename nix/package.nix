# The commands: `chess` (the terminal app), chess-openings (the window), the
# screens of `chess` straight, chess-review, chess-sync and chess-tui. What
# they know of you comes from the arguments: chix.override { users = ...; }
{
  lib,
  python3,
  writeShellApplication,
  writeText,
  symlinkJoin,
  xdg-utils,
  chess-tui,
  gtk3,
  webkitgtk_4_1,
  glib,
  gdk-pixbuf,
  pango,
  harfbuzz,
  at-spi2-core,
  libsoup_3,
  gobject-introspection,
  # github:lichess-org/chess-openings
  chess-openings,
  # the UCI engines, one command each (./engines.nix)
  engines,
  # "lichess:NAME chesscom:NAME": your games and the explorer's "you"
  users ? "",
  # a file holding a Lichess token: the explorer, puzzles on your account,
  # playing from chess-tui
  tokenFile ? null,
}:
let
  python = python3.withPackages (p: [
    p.chess
    p.textual
    # the openings' window: WebKitGTK
    p.pywebview
    p.pygobject3
  ]);

  # what pywebview's GTK window loads through GObject introspection
  typelibs = lib.makeSearchPath "lib/girepository-1.0" (
    map lib.getLib [
      gtk3
      webkitgtk_4_1
      glib
      gdk-pixbuf
      pango
      harfbuzz
      at-spi2-core
      libsoup_3
      gobject-introspection
    ]
  );

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
  enginesJson = writeText "chess-engines.json" (builtins.toJSON commands);

  # chess-tui [--engine NAME]: stockfish unless named; Maia searches no
  # deeper than one ply. The token is read on each run
  tui = writeShellApplication {
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
      ${lib.optionalString (tokenFile != null) ''args+=(-l "$(cat ${tokenFile})")''}
      exec ${lib.getExe chess-tui} "''${args[@]}" "$@"
    '';
  };

  # tool NAME "SCRIPT [ARGS]"; CHESS_DIR, where your games and progress
  # are kept, is ~/chess unless set
  tool =
    name: script:
    writeShellApplication {
      inherit name;
      runtimeInputs = [ xdg-utils ];
      text = ''
        export CHESS_ENGINES=${enginesJson}
        export CHESS_OPENINGS=${chess-openings}
        export CHESS_USERS="${users}"
        export CHESS_TUI=${lib.getExe tui}
        export CHESS_DIR="''${CHESS_DIR:-$HOME/chess}"
        export GI_TYPELIB_PATH=${typelibs}
        ${lib.optionalString (tokenFile != null) "export LICHESS_TOKEN_FILE=${tokenFile}"}
        exec ${python}/bin/python3 ${../src}/${script} "$@"
      '';
    };
in
symlinkJoin {
  name = "chix";
  paths = [
    tui
    (tool "chess" "app.py")
    # the openings in a window; `chess openings` is the terminal's
    (tool "chess-openings" "gui.py")
    # the screens of `chess`, straight
    (tool "chess-games" "app.py games")
    (tool "chess-train" "app.py train")
    (tool "chess-puzzle" "app.py puzzle")
    (tool "chess-explore" "app.py explore")
    (tool "chess-review" "review.py")
    (tool "chess-sync" "sync.py")
  ];
  passthru = { inherit python engines typelibs; };
  meta = {
    description = "Chess openings learned by name, your games reviewed, training and puzzles";
    mainProgram = "chess";
    platforms = lib.platforms.linux;
  };
}
