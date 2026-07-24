# Consolidated packages entrypoint
# This is an overlay function that should be merged with other overlays
final: prev:
{
  any-sync-tools = final.callPackage ./any-sync/any-sync-tools.nix {};
  any-sync-coordinator = final.callPackage ./any-sync/any-sync-coordinator.nix {};
  any-sync-consensus = final.callPackage ./any-sync/any-sync-consensus.nix {};
  any-sync-node = final.callPackage ./any-sync/any-sync-node.nix {};
  any-sync-filenode = final.callPackage ./any-sync/any-sync-filenode.nix {};
  anytype-agent-runtime = final.callPackage ./anytype/anytype-agent-runtime.nix {};
  anytype-mcp = final.callPackage ./anytype/anytype-mcp.nix {};
  valkey-bloom = final.callPackage ./valkey-bloom {};
}
