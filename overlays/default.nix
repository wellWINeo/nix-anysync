# Consolidated overlays entry point
# Includes anytype overlay with the anytype-heart patch
final: prev:

(import ./anytype {inherit final prev;}) // {}
