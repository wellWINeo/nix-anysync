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
  version = "0.7.0";
  maintainers = import ../../maintainers/maintainer-list.nix;
in
pkgs.buildGoModule {
  pname = "any-sync-tools";
  inherit version;

  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-tools";
    tag = "v${version}";
    sha256 = "sha256-GANZiEtpGC1kflunE3M0JiXRI7PL9O9I4iPxaE0OzLQ=";
  };

  vendorHash = "sha256-yNvuCxN3VjboLPbrjuF29izJ4UqreIh2q0IxeCzmwWU=";

  patches = [ ./patches/any-sync-netcheck-exit-status.patch ];

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
