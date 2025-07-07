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
  version = "0.2.10";
  maintainers = import ../../maintainers/maintainer-list.nix;
in
pkgs.buildGoModule {
  pname = "any-sync-tools";
  inherit version;

  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-tools";
    tag = "v${version}";
    sha256 = "sha256-Dlm+xGOTttZRnVTeYAFuCi0aQ6mQXcFGTL5CNo/IWKY=";
  };

  vendorHash = "sha256-in6qI0xUTj8MkmQRDI2OSlHDQ/M4a40xk8l5weaGVds=";

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
