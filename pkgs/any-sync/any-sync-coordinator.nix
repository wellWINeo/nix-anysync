{ pkgs, fetchFromGitHub, lib }:

###
# Package for any-sync-coordinator node
# provides: any-sync-coordinator, any-sync-confapply
###

let
  version = "0.4.4";
  maintainers = import ../../maintainers/maintainer-list.nix;
in pkgs.buildGoModule {
  pname = "any-sync-coordinator";
  inherit version;

  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-coordinator";
    rev = "v${version}";
    sha256 = "sha256-JRiIM4UP92R+PI00XI6+yTIKaK1Q1pgkSp+6k9QWa+E=";
  };

  # git clone https://github.com/anyproto/any-sync-coordinator
  # git checkout v0.4.4
  # go mod tidy
  # go mod vendor
  # nix hash path ./vendor
  vendorHash = "sha256-6qzqeYaaU2IwTLabPMebRjnsXitKlcCAZoIWCs4mOds=";

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