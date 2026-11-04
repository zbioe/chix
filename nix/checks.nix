# nix flake check: the package, the lint and the smoke test
{
  pkgs,
  chix,
  chess-openings,
}:
let
  src = ./..;
in
{
  inherit chix;
  ruff = pkgs.runCommand "chix-ruff" { nativeBuildInputs = [ pkgs.ruff ]; } ''
    ruff check --no-cache ${src}/src ${src}/tests
    touch $out
  '';
  smoke =
    pkgs.runCommand "chix-smoke"
      {
        nativeBuildInputs = [ chix.python ];
        CHESS_OPENINGS = chess-openings;
        CHESS_ENGINES = builtins.toFile "chess-engines.json" "{}";
        CHESS_USERS = "";
        GI_TYPELIB_PATH = chix.typelibs;
      }
      ''
        export HOME=$TMPDIR CHESS_DIR=$TMPDIR/chess
        python3 ${src}/tests/smoke.py
        touch $out
      '';
}
