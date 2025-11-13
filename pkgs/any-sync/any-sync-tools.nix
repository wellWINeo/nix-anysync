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
  version = "0.3.1";
  maintainers = import ../../maintainers/maintainer-list.nix;
in
pkgs.buildGoModule {
  pname = "any-sync-tools";
  inherit version;

  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-tools";
    tag = "v${version}";
    sha256 = "sha256-KnwJm7PQA6/zQaj8FC9GSxMIuykK4lcHOfk+mWYng6E=";
  };

  vendorHash = "sha256-Bx70/s1CFyXJ10PC7fAc1e71cxdKpaa32sX4j1b3ek4=";

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
