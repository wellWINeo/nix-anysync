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
  version = "0.6.8";
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
    sha256 = "sha256-cRgxoIoyF1DJ20wN/QW4qkY4aqe4sKlRMg/pO4vGqFU=";
  };

  vendorHash = "sha256-9kpnf4KimW/jZWR1AbrE8NzsYEAPZ24aTQfOei5XLAY=";

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
