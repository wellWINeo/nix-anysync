{
  pkgs,
  fetchFromGitHub,
  lib,
}:

###
# Package for any-sync-node
# provides: any-sync-node
###

let
  version = "0.7.1";
  maintainers = import ../../maintainers/maintainer-list.nix;
in
pkgs.buildGoModule {
  pname = "any-sync-node";
  inherit version;

  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-node";
    tag = "v${version}";
    sha256 = "sha256-z5pF2f7JgqYH/mNjaToJdWnKxU9qL7LSjfUtuhkU7Oc=";
  };

  vendorHash = "sha256-tnQT928b6QN+vrBFJF8ec3WRgN4zlWyKTJYux+KANIU=";

  postInstall = ''
    mv $out/bin/cmd $out/bin/any-sync-node
    mv $out/bin/util $out/bin/any-sync-migrationcheck
  '';

  meta = {
    description = "Implementation of node from any-sync protocol";
    homepage = "https://github.com/anyproto/any-sync-node";
    license = lib.licenses.mit;
    maintainers = [ maintainers.wellWINeo ];
  };
}
