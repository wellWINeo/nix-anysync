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
  version = "0.5.1";
  maintainers = import ../../maintainers/maintainer-list.nix;
in
pkgs.buildGoModule {
  pname = "any-sync-coordinator";
  inherit version;

  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-coordinator";
    tag = "v${version}";
    sha256 = "sha256-1s9I0O3ReUUcEHOqMxGO0/cVXaEPoCu2SHdJaOnPCu4=";
  };

  vendorHash = "sha256-Z8p7SX/gtP8vt+g05WX6Xqfa22S1EtfaZlW/uUYGmqw=";

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
