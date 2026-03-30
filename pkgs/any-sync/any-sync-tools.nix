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
  version = "0.6.1";
  maintainers = import ../../maintainers/maintainer-list.nix;
in
pkgs.buildGoModule {
  pname = "any-sync-tools";
  inherit version;

  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-tools";
    tag = "v${version}";
    sha256 = "sha256-b8UxZEsy/CMHABhPbswdQZ9ftbUR87NbXrGYkhUzwKM=";
  };

  vendorHash = "sha256-5AueL3gPLmPpglXs9EBzuT3EyLhGFWwCLZGuHmfMr60=";

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
