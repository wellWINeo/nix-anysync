{
  pkgs,
  fetchFromGitHub,
  lib,
}:

###
# Package for any-sync-tools, includes
# any-sync-network and any-sync-netcheck
###

let
  version = "0.4.5";
  maintainers = import ../../maintainers/maintainer-list.nix;
in
pkgs.buildGoModule {
  pname = "any-sync-tools";
  inherit version;

  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-tools";
    tag = "v${version}";
    sha256 = "sha256-bjWu6cmUrRVJf33ACi75t1GGG0kSoXfjCZ3b7F7jD4g=";
  };

  vendorHash = "sha256-n/u9Tr7nx2VTEfMBp9u63CtZ55czaiaJFoPv+Sd0re4=";

  subPackages = [
    "any-sync-network"
    "any-sync-netcheck"
    "anyconf"
  ];

  meta = {
    description = "Configuration builder and network issues debugger for Any-Sync";
    homepage = "https://github.com/anyproto/any-sync-tools";
    license = lib.licenses.mit;
    maintainers = [ maintainers.wellWINeo ];
  };
}
