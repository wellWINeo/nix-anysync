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
  version = "0.6.4";
  maintainers = import ../../maintainers/maintainer-list.nix;
in
pkgs.buildGoModule {
  pname = "any-sync-node";
  inherit version;

  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-node";
    rev = "v${version}";
    sha256 = "sha256-dWvrpHHh3+zRzbIkKQr+1VtxIenZfdly2m0SpaW5nFY=";
  };

  # git clone https://github.com/anyproto/any-sync-node
  # git checkout v0.6.4
  # go mod tidy
  # go mod vendor
  # nix hash path ./vendor
  vendorHash = "sha256-bmOXsCIofybZKPCUgSZSom9TI2vmVatjNaX7jrDyddQ=";

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
