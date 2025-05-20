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
  version = "0.5.0";
  maintainers = import ../../maintainers/maintainer-list.nix;
in
pkgs.buildGoModule {
  pname = "any-sync-coordinator";
  inherit version;

  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-coordinator";
    tag = "v${version}";
    sha256 = "sha256-IpNHH0gelq781Fegv5LbV0sucyk9PPjPCY6T/ALFfvM=";
  };

  vendorHash = "sha256-7fm0nfuCccxLm2RiRLeF1N5vVhaOrIopPXWEZf14Klg=";

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
