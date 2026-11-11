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
  version = "0.13.5";
  maintainers = import ../../maintainers/maintainer-list.nix;
in
pkgs.buildGoModule {
  pname = "any-sync-node";
  inherit version;

  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-node";
    tag = "v${version}";
    sha256 = "sha256-l0W+4B0Gfc+kUCdDATPX1URJs81mTRhB1sRWzj+9h08=";
  };

  vendorHash = "sha256-bXit5CZiANBxvNNdZNcQlKNGig/DhlnwQFOtes8UyEU=";

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
