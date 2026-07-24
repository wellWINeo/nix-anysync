{
  pkgs,
}:

pkgs.buildGoModule rec {
  pname = "anytype-agent-runtime";
  version = "0.1.4";

  # Fetch source code from GitHub using the v0.1.4 tag
  src = pkgs.fetchFromGitHub {
    owner = "anyproto";
    repo = "anytype-agent-runtime";
    rev = "v${version}";
    sha256 = "wXStHLy/0EWHZjUnXoKf1SkTqyiDHmjpoBNZi71x5Ug=";
  };

  vendorHash = "sha256-eWfMuCJG1cBBV1alcnQDvqeELwQJHOh+uVCsEzySR7o=";

  # Disable tests
  doCheck = false;

  meta = with pkgs.lib; {
    description = "Anytype Agent Runtime - JavaScript agent runtime for Anytype";
    homepage = "https://github.com/anyproto/anytype-agent-runtime";
    license = licenses.mit;
    maintainers = with maintainers; [ ];
    platforms = platforms.linux;
    mainProgram = pname;
  };
}
