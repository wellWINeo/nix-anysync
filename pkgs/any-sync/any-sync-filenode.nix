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
  version = "0.8.6";
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
    sha256 = "sha256-YNMxXov6hWaMaZ9H9NmydRJNwV5gU+O4KrDFPn3q6Js=";
  };

  vendorHash = "sha256-Cdk87leezza8UPJhhompGJa32a3ikL9/Itr9hH+ngV4=";

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
