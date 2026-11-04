{
  description = "chix: chess openings learned by name, your games reviewed, training and puzzles";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    systems.url = "github:nix-systems/default-linux";
    # every named opening line, as Lichess names them
    chess-openings = {
      url = "github:lichess-org/chess-openings";
      flake = false;
    };
    # Maia's networks: Lc0 playing like people of 1100 to 1900
    maia = {
      url = "github:CSSLab/maia-chess";
      flake = false;
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      systems,
      chess-openings,
      maia,
    }:
    let
      eachSystem = f: nixpkgs.lib.genAttrs (import systems) (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = eachSystem (pkgs: rec {
        engines = pkgs.callPackage ./nix/engines.nix { inherit maia; };
        chix = pkgs.callPackage ./nix/package.nix { inherit chess-openings engines; };
        default = chix;
      });

      homeModules.default = import ./nix/module.nix { inherit chess-openings maia; };

      checks = eachSystem (
        pkgs:
        import ./nix/checks.nix {
          inherit pkgs chess-openings;
          inherit (self.packages.${pkgs.stdenv.hostPlatform.system}) chix;
        }
      );

      devShells = eachSystem (pkgs: {
        default = pkgs.mkShell {
          packages = [
            self.packages.${pkgs.stdenv.hostPlatform.system}.chix.python
            pkgs.ruff
          ];
          # `python3 src/app.py` from here runs what you're editing
          shellHook = ''
            export CHESS_OPENINGS=${chess-openings}
            export CHESS_ENGINES=${
              pkgs.writeText "chess-engines.json" (
                builtins.toJSON { stockfish = nixpkgs.lib.getExe pkgs.stockfish; }
              )
            }
            export CHESS_DIR="''${CHESS_DIR:-$HOME/chess}"
            export GI_TYPELIB_PATH=${self.packages.${pkgs.stdenv.hostPlatform.system}.chix.typelibs}
          '';
        };
      });

      formatter = eachSystem (pkgs: pkgs.nixfmt-tree);
    };
}
