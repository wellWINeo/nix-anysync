#!/usr/bin/env bash
set -euo pipefail

kvm_device="${1:-/dev/kvm}"
if [[ ! -c "$kvm_device" ]]; then
  echo "::error::The runner does not provide $kvm_device" >&2
  exit 1
fi

# Nix's daemon may run the build as a nixbld user rather than as the GitHub Actions runner.
if [[ ! -r "$kvm_device" || ! -w "$kvm_device" ]]; then
  sudo chmod o+rw "$kvm_device"
fi

build_users="$(getent passwd | awk -F: '$1 ~ /^nixbld[0-9]+$/ { print $1 }')"
build_users="$(printf '%s\n%s\n' "$(id -un)" "$build_users")"

while IFS= read -r build_user; do
  [[ -n "$build_user" ]] || continue
  if ! sudo -u "$build_user" -- bash -c '[[ -r "$1" && -w "$1" ]]' _ "$kvm_device"; then
    sudo chmod a+rw "$kvm_device"
    break
  fi
done <<< "$build_users"

while IFS= read -r build_user; do
  [[ -n "$build_user" ]] || continue
  sudo -u "$build_user" -- bash -c '[[ -r "$1" && -w "$1" ]]' _ "$kvm_device"
done <<< "$build_users"
