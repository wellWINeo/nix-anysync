{
  description = "Any-Sync NixOS flake";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-26.05";
  };

  outputs =
    { self, nixpkgs, ... }:
    let
      # System types to support.
      supportedSystems = [
        "x86_64-linux"
        "x86_64-darwin"
        "aarch64-linux"
        "aarch64-darwin"
      ];

      # Helper function to generate an attrset '{ x86_64-linux = f "x86_64-linux"; ... }'.
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;

      # Import consolidated overlays and packages
      localOverlays = import ./overlays;
      localPackages = import ./pkgs;
      localModules = import ./nixos/modules;

      # Define the overlay by merging all overlay components
      overlay = final: prev:
        (localOverlays final prev)
        // (localPackages final prev);

      # Get overlay package names via fake-evaluation (lazy evaluation allows this)
      # We use a dummy overlay context - since we only evaluate keys, the RHS is never forced
      packageNames = builtins.attrNames (overlay null null);

      # Nixpkgs instantiated for supported system types.
      nixpkgsFor = forAllSystems (
        system:
        import nixpkgs {
          inherit system;
          overlays = [ overlay ];
          config = {
            allowUnfree = true;
            allowUnfreePredicate = _: true;
            permittedInsecurePackages = [
              # MinIO is used in tests and is marked insecure
              "minio-2025-10-15T17-29-55Z"
            ];
          };
        }
      );
    in
    {
      inherit overlay;
      packages = forAllSystems (
        system:
        let
          pkgs = nixpkgsFor.${system};
          allPackages = nixpkgs.lib.genAttrs packageNames (name: pkgs.${name});
        in
        nixpkgs.lib.filterAttrs (
          _: package:
          nixpkgs.lib.meta.availableOn { inherit system; } package
          && !(package.meta.broken or false)
        ) allPackages
      );

      checks = forAllSystems (
        system:
        let
          pkgs = nixpkgsFor.${system};
        in
        {
          any-sync-test = pkgs.callPackage ./nixos/tests/any-sync-test.nix {
            inherit pkgs;
            nixosModules = localModules;
          };
        }
      );

      nixosModules = localModules;

      devShells = forAllSystems (
        system:
        let
          pkgs = nixpkgsFor.${system};
        in
        {
          default = pkgs.mkShell {
            nativeBuildInputs = with pkgs; [
              nixfmt
              nixd
            ];
          };
        }
      );
    };
}
