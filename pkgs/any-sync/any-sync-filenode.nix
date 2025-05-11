{ pkgs, fetchFromGitHub, lib }:

###
# Package for any-sync-filenode
# provides: any-sync-filenode
###

let
  version = "0.8.5";
  maintainers = import ../../maintainers/maintainer-list.nix;
in pkgs.buildGoModule {
  pname = "any-sync-filenode";
  inherit version;

  # disabled bacuse of integration tests
  doCheck = false;

  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-filenode";
    rev = "v${version}";
    sha256 = "sha256-h4e7T2Hiok3f9zUr8pPW8SrtOzmAzLD0j+xL6rqzyF4=";
  };

  # git clone https://github.com/anyproto/any-sync-filenode
  # git checkout v0.8.5
  # go mod tidy
  # go mod vendor
  # nix hash path ./vendor
  vendorHash = "sha256-4S8fZgDI9i5+qDx/ciNi25X/CeNrA9RNZK0vnRq0KxI=";

  postInstall = ''
    mv $out/bin/cmd $out/bin/any-sync-filenode
  '';

  meta = {
    description = "Implementation of file node from any-sync protocol";
    homepage = "https://github.com/anyproto/any-sync-filenode";
    license = lib.licenses.mit;
    maintainers = [ maintainers.wellWINeo ];
  };
}