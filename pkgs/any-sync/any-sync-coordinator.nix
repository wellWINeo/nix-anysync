{
  pkgs,
  fetchFromGitHub,
  lib,
}:

###
# Package for any-sync-coordinator node
# provides: any-sync-coordinator, any-sync-confapply
###

let
  version = "0.8.0";
  maintainers = import ../../maintainers/maintainer-list.nix;
in
pkgs.buildGoModule {
  pname = "any-sync-coordinator";
  inherit version;

  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-coordinator";
    tag = "v${version}";
    sha256 = "sha256-ijdRzYe5FaAP7BRNBNrFzU5Y1qr4/SSWggAYoY1OgZA=";
  };

  vendorHash = "sha256-tTuc5FYRPgrf65BVkAN9KkD0mDiLQ6uWbbKaQg3xnE4=";

  subPackages = [
    "cmd/confapply"
    "cmd/coordinator"
  ];

  postInstall = ''
    mv $out/bin/confapply $out/bin/any-sync-confapply
    mv $out/bin/coordinator $out/bin/any-sync-coordinator
  '';

  meta = {
    description = "Implementation of coordinator node from any-sync protocol";
    homepage = "https://github.com/anyproto/any-sync-coordinator";
    license = lib.licenses.mit;
    maintainers = [ maintainers.wellWINeo ];
  };
}
