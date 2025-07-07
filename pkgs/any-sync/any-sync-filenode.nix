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
  version = "0.8.12";
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
    sha256 = "sha256-xiYezOiJXemgt3MgsG/8/j0az9RdGMnjbe5lW9w1fbw=";
  };

  vendorHash = "sha256-FY9O2GbaEpjovbExecM8erYieqGfVES7amZaEPheHLE=";

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
