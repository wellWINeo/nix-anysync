#!/usr/bin/env bash
set -euo pipefail

package="${1:?expected an Any-Sync package name}"
case "$package" in
  any-sync-consensus|any-sync-coordinator|any-sync-filenode|any-sync-node|any-sync-tools) ;;
  *) echo "Unsupported package: $package" >&2; exit 2 ;;
esac

nix shell --inputs-from . nixpkgs#nix-update --command nix-update --flake "$package"

if git diff --quiet -- "pkgs/any-sync/$package.nix"; then
  echo "changed=false" >> "$GITHUB_OUTPUT"
else
  status=$?
  if [[ "$status" -ne 1 ]]; then
    exit "$status"
  fi
  echo "changed=true" >> "$GITHUB_OUTPUT"
fi
