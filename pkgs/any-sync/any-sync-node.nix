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
  version = "0.9.3";
  maintainers = import ../../maintainers/maintainer-list.nix;
in
pkgs.buildGoModule {
  pname = "any-sync-node";
  inherit version;

  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-node";
    tag = "v${version}";
    sha256 = "sha256-9Y87gS/fCylJoCfoJLkOyGluGi7GkvOmvHY1m+wrWqw=";
  };

  vendorHash = "sha256-PJl4fUAIdRgaEiGaf2rIGDxpGcHn0PRuGpQ7Wc4a9bg=";

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
