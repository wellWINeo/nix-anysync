{
  pkgs,
  fetchFromGitHub,
  lib,
}:

###
# Package for any-sync-filenode
# provides: any-sync-filenode
###

let
  version = "0.10.0";
  maintainers = import ../../maintainers/maintainer-list.nix;
in
pkgs.buildGoModule {
  pname = "any-sync-filenode";
  inherit version;

  # disabled bacuse of integration tests
  doCheck = false;

  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-filenode";
    tag = "v${version}";
    sha256 = "sha256-x8Um+2NKTH/AWJoaNlo7TNE8VSVHB8LNnYABQeZn7PI=";
  };

  vendorHash = "sha256-8UD7lO/vbSv+vcxdj1Jo0v/QZiLTV/ESsgeVqjYWXxY=";

  postInstall = ''
    mv $out/bin/cmd $out/bin/any-sync-filenode
  '';

  meta = {
    description = "Implementation of file node from any-sync protocol";
    homepage = "https://github.com/anyproto/any-sync-filenode";
    license = lib.licenses.mit;
    maintainers = [ maintainers.wellWINeo ];
  };
}
