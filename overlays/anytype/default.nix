{ final, prev }:

{
  # Override anytype-heart from nixpkgs with the patch from PR #3220
  # https://patch-diff.githubusercontent.com/raw/anyproto/anytype-heart/pull/3220.patch
  anytype-heart = prev.anytype-heart.overrideAttrs (oldAttrs: rec {
    version = "0.50.17";
    src = final.fetchFromGitHub {
      owner = "anyproto";
      repo = "anytype-heart";
      tag = "v${version}";
      sha256 = "sha256-2DXYpBc14z+q+kJNLScWSTqVSObolj/80FrVEwNU4cY=";
    };
    # patches = (oldAttrs.patches or [ ]) ++ [
    #   (final.fetchurl {
    #     url = "https://patch-diff.githubusercontent.com/raw/anyproto/anytype-heart/pull/3220.patch";
    #     hash = "sha256-YkpfoZiu9RjDqxzOZd4w1w9rVg+1Ema4zwb8NNtcB3c=";
    #   })
    # ];
  });

  # Override anytype-cli from nixpkgs to use v0.3.6 instead of v0.3.5
  # and patch go.mod to use the locally patched anytype-heart source
  anytype-cli = prev.anytype-cli.overrideAttrs (oldAttrs: rec {
    version = "0.3.6";
    src = final.fetchFromGitHub {
      owner = "anyproto";
      repo = "anytype-cli";
      tag = "v${version}";
      sha256 = "sha256-T/mdF+pzApm15Cg2g1ybgU7pEHLsTC4jD7WuXzNqM2M=";
    };
    # Set vendorHash to null to force go mod tidy after go.mod modifications
    vendorHash = "sha256-ufOSCNpBExmuhqiFwyyyVbDNf3xr+m9m8mWw9gZc8r4=";
    preBuild = oldAttrs.postPatch or "" + ''
      echo 'preBuild - rewriting go.mod'
      # Patch go.mod to use the locally patched anytype-heart source from nix store
      go mod edit -replace github.com/anyproto/anytype-heart="${final.anytype-heart.src}"
      go mod tidy
    '';
  });
}
