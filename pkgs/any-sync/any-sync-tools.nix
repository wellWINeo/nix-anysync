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
  version = "0.2.8";
  maintainers = import ../../maintainers/maintainer-list.nix;
in
pkgs.buildGoModule {
  pname = "any-sync-tools";
  inherit version;

  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-tools";
    rev = "v${version}";
    sha256 = "sha256-y582GwDPx9h6Zz+QGxZRXiB7pAHl7YxIi9nRl7Tpytk=";
  };

  # git clone https://github.com/anyproto/any-sync-tools
  # git checkout v0.2.8
  # go mod tidy
  # go mod vendor
  # nix hash path ./vendor
  vendorHash = "sha256-Kfq+EV8r2w4hi271Vw4DqsWP4dYcTse3/aQcYbU9TDQ=";

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
