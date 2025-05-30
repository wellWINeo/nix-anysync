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
  version = "0.2.3";
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
    sha256 = "sha256-5cZgXdRsL3jLaDXigdC5KKSmpddXWGOdzsxgysdrHfY=";
  };

  vendorHash = "sha256-KKBT2gQzpoIM8zc3nuzyDxXknKnMum1I6aLRdcYSIig=";

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
