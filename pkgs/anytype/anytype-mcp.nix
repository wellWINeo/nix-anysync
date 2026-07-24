{
  pkgs,
  lib,
}:

pkgs.buildNpmPackage rec {
  pname = "anytype-mcp";
  version = "1.2.9";

  src = pkgs.fetchFromGitHub {
    owner = "anyproto";
    repo = "anytype-mcp";
    tag = "v${version}";
    sha256 = "sha256-azSZToElWdwTUuy/gP7k6rAtZEMA7JzQ+ZDfSZgT7Jg=";
  };

  npmDepsHash = "sha256-z8bZsS8w8cKFSoqbxEHwU1y0ZFIxNNcxLlQQ+BFLz64=";

  # patches = [
  #   (pkgs.fetchurl {
  #     url = "https://patch-diff.githubusercontent.com/raw/anyproto/anytype-mcp/pull/59.patch";
  #     hash = "sha256-geiIOeC3chLh2RMjpevSlGJWiA8c6v7Xl7xDNcsJ8x8=";
  #   })
  # ];

  # Disable tests
  doCheck = false;

  meta = with lib; {
    description = "MCP server enabling AI assistants to interact with Anytype";
    homepage = "https://github.com/anyproto/anytype-mcp";
    license = licenses.mit;
    platforms = platforms.linux;
    mainProgram = "anytype-mcp";
  };
}
