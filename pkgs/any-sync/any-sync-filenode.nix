{
  pkgs,
  fetchFromGitHub,
  lib,
}:

###
# Package for any-sync-filenode
# provides: any-sync-filenode
###

let
  version = "0.9.2";
  maintainers = import ../../maintainers/maintainer-list.nix;
in
pkgs.buildGoModule {
  pname = "any-sync-filenode";
  inherit version;

  # disabled bacuse of integration tests
  doCheck = false;

  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-filenode";
    tag = "v${version}";
    sha256 = "sha256-K0X0psvmHzcaCpgrAoOiVZKkxzY2P/Mw6IJz8B8BiPg=";
  };

  vendorHash = "sha256-ILA6Z/G7sfGpfYwZjkPX+i90HR0IJ4a1AAjTVdu9YBw=";

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
