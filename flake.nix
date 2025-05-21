{
  description = "Any-Sync NixOS flake";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-24.11";
  };

  outputs =
    { nixpkgs, ... }:
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

      # Define the overlay
      overlay = final: prev: {
        any-sync-tools = final.callPackage ./pkgs/any-sync/any-sync-tools.nix { };
        any-sync-coordinator = final.callPackage ./pkgs/any-sync/any-sync-coordinator.nix { };
        any-sync-consensus = final.callPackage ./pkgs/any-sync/any-sync-consensus.nix { };
        any-sync-node = final.callPackage ./pkgs/any-sync/any-sync-node.nix { };
        any-sync-filenode = final.callPackage ./pkgs/any-sync/any-sync-filenode.nix { };
      };

      # Nixpkgs instantiated for supported system types.
      nixpkgsFor = forAllSystems (
        system:
        import nixpkgs {
          inherit system;
          overlays = [ overlay ];
          config = {
            allowUnfree = true;
            allowUnfreePredicate = _: true;
          };
        }
      );
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = nixpkgsFor.${system};
        in
        {
          any-sync-tools = pkgs.any-sync-tools;
          any-sync-coordinator = pkgs.any-sync-coordinator;
          any-sync-consensus = pkgs.any-sync-consensus;
          any-sync-node = pkgs.any-sync-node;
          any-sync-filenode = pkgs.any-sync-filenode;
        }
      );

      checks = forAllSystems (
        system:
        let
          pkgs = nixpkgsFor.${system};
        in
        {
          any-sync-test = pkgs.callPackage ./nixos/tests/any-sync-test.nix {
            inherit pkgs;
            modules = {
              any-sync-consensus = ./nixos/modules/any-sync/any-sync-consensus.nix;
              any-sync-coordinator = ./nixos/modules/any-sync/any-sync-coordinator.nix;
              any-sync-filenode = ./nixos/modules/any-sync/any-sync-filenode.nix;
              any-sync-node = ./nixos/modules/any-sync/any-sync-node.nix;
            };
          };
        }
      );

      nixosModules = {
        any-sync-consensus = ./nixos/modules/any-sync/any-sync-consensus.nix;
        any-sync-coordinator = ./nixos/modules/any-sync/any-sync-coordinator.nix;
        any-sync-filenode = ./nixos/modules/any-sync/any-sync-filenode.nix;
        any-sync-node = ./nixos/modules/any-sync/any-sync-node.nix;
      };

      devShells = forAllSystems (
        system:
        let
          pkgs = nixpkgsFor.${system};
        in
        {
          default = pkgs.mkShell {
            nativeBuildInputs = with pkgs; [
              nixfmt-rfc-style
              nixd
            ];
          };
        }
      );
    };
}
