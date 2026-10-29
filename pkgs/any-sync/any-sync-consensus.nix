{
  pkgs,
  fetchFromGitHub,
  lib,
}:

###
# Package for any-sync-consensus node
# provides: any-sync-consensus
###

let
  version = "0.13.3";
  maintainers = import ../../maintainers/maintainer-list.nix;
in
pkgs.buildGoModule {
  pname = "any-sync-consensus";
  inherit version;

  doCheck = false;

  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-consensusnode";
    tag = "v${version}";
    sha256 = "sha256-Wpj6kM6x9r8pWKvx/i7dR7pescEl2N8aD4iTlGYOPjE=";
  };

  vendorHash = "sha256-2FL65lGDJzo7wnLHSnfW1T/0zO8ThgjDUNutXJPLx4Q=";

  postInstall = ''
    mv $out/bin/cmd $out/bin/any-sync-consensus
  '';

  meta = {
    description = "Implementation of consensus node from any-sync protocol";
    homepage = "https://github.com/anyproto/any-sync-consensusnode";
    license = lib.licenses.mit;
    maintainers = [ maintainers.wellWINeo ];
  };
}
