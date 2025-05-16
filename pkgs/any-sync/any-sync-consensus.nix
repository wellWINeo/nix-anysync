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
  version = "0.2.2";
  maintainers = import ../../maintainers/maintainer-list.nix;
in
pkgs.buildGoModule {
  pname = "any-sync-consensus";
  inherit version;

  doCheck = false;

  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-consensusnode";
    rev = "v${version}";
    sha256 = "sha256-N+v/uiwYoGBd1jcT5IK+mKQ1TmLeUSaR5YmJedI3hkw=";
  };

  # git clone https://github.com/anyproto/any-sync-consensusnode
  # git checkout v0.2.2
  # go mod tidy
  # go mod vendor
  # nix hash path ./vendor
  vendorHash = "sha256-GHJdwSI1tG33BUHqG51g0TflflLVnptLaJ5wh/tr00k=";

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
