# The UCI engines, each a command with no arguments (what the GUIs run):
# stockfish, lc0 with its network, maia-1100 to maia-1900 (Lc0 playing like
# people of that rating) and gnuchess (gnuchessu speaks UCI)
{
  lib,
  symlinkJoin,
  writeShellScriptBin,
  fetchurl,
  stockfish,
  lc0,
  openblas,
  gnuchess,
  # github:CSSLab/maia-chess (flake input)
  maia,
}:
let
  # on the CPU through OpenBLAS, twice eigen's speed; the OpenCL backend
  # can't run today's networks
  lc0Blas = lc0.overrideAttrs (old: {
    buildInputs = old.buildInputs ++ [ openblas ];
    mesonFlags = old.mesonFlags ++ [
      "-Dopenblas_libdirs=${openblas}/lib"
      "-Dopenblas_include=${openblas.dev}/include"
    ];
  });

  # lczero.org's smallest recommended network, the one a CPU can run
  network = fetchurl {
    url = "https://storage.lczero.org/files/networks-contrib/t1-256x10-distilled-swa-2432500.pb.gz";
    hash = "sha256-vCemyuitNvK5qApq2dq7DW/aJbHn9IGnm8NZ4U9WNAY=";
  };

  leela =
    name: weights:
    writeShellScriptBin name ''
      exec ${lc0Blas}/bin/lc0 --weights=${weights} --backend=blas "$@"
    '';

  ratings = map toString (lib.range 11 19);
in
symlinkJoin {
  name = "chess-engines";
  paths = [
    stockfish
    gnuchess
    (leela "lc0" network)
  ]
  ++ map (r: leela "maia-${r}00" "${maia}/maia_weights/maia-${r}00.pb.gz") ratings;
  passthru.maia = map (r: "maia-${r}00") ratings;
}
