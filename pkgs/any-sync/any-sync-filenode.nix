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
  version = "0.13.2";
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
    sha256 = "sha256-WbQ67BFL3/AHwCEUvLJiL/kNrmQ4t8/slIYhSUh3RRY=";
  };

  vendorHash = "sha256-CG6YWktUsOD4q+j/zVYzosOwQXqZNJnHCcCi016NZyk=";

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
