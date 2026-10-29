#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
for package in any-sync-consensus any-sync-coordinator any-sync-filenode any-sync-node any-sync-tools; do
  echo "::group::Update $package"
  GITHUB_OUTPUT=/dev/null bash "$script_dir/update-package.sh" "$package"
  echo "::endgroup::"
done

if git diff --quiet -- pkgs/any-sync/*.nix; then
  echo "changed=false" >> "$GITHUB_OUTPUT"
else
  status=$?
  if [[ "$status" -ne 1 ]]; then
    exit "$status"
  fi
  echo "changed=true" >> "$GITHUB_OUTPUT"
fi
