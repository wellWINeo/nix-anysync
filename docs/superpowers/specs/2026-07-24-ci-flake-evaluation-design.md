# Flake Evaluation CI Design

## Goal

Add GitHub Actions validation for pull requests and pushes to `main` that evaluates every supported flake system without building packages or running the existing NixOS integration test. Fix the current Darwin evaluation failure by exposing only valid package outputs for each target system.

## Current Problem

The current flake evaluates successfully for `x86_64-linux` and `aarch64-linux`, but fails for both Darwin systems during package derivation evaluation.

The failure was introduced when `/Users/o__ni/Code/Git/nix-anysync/flake.nix` changed from explicitly exporting the five Any-Sync packages to deriving package names from the complete overlay:

```nix
nixpkgs.lib.genAttrs packageNames (name: pkgs.${name})
```

The complete overlay now includes packages with different platform constraints:

- `anytype-agent-runtime` is Linux-only.
- `anytype-mcp` is Linux-only.
- `anytype-heart` lists Darwin in its platform metadata but inherits `broken = stdenv.hostPlatform.isDarwin` from nixpkgs.

The local `anytype-heart` override changes its version and source but preserves the inherited broken metadata. On Darwin, Nix therefore rejects `anytype-heart` before evaluating the remaining package outputs. If that check is bypassed, Nix rejects the Linux-only packages as unsupported. This is an output-selection problem, not a NixOS test failure.

The diagnostic command below confirms that the current all-system check only succeeds when both metadata guards are explicitly bypassed:

```bash
NIXPKGS_ALLOW_BROKEN=1 NIXPKGS_ALLOW_UNSUPPORTED_SYSTEM=1 \
  nix flake check --no-build --impure --all-systems
```

Those allowances are diagnostic evidence only and must not be used by the production flake or CI.

## Design Decision

Keep all four declared systems and retain dynamic package discovery, but filter the generated package set for each target system. A package is exported only when:

1. `nixpkgs.lib.meta.availableOn { inherit system; } package` reports that its platform metadata supports the target system.
2. The package does not have `meta.broken = true`.

The package output shape will follow this pattern:

```nix
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
```

This produces truthful per-system outputs without globally enabling broken or unsupported packages:

- Linux retains all currently exported packages.
- Darwin retains the packages whose metadata makes them evaluable there.
- Linux-only `anytype-agent-runtime` and `anytype-mcp` are omitted from Darwin outputs.
- Darwin-broken `anytype-heart` is omitted from Darwin outputs until its upstream or local metadata makes it valid there.

No package definition, nixpkgs configuration, or package metadata override is required for this fix.

## CI Workflow

Create `.github/workflows/check-flake.yml` with the following behavior:

- Trigger on every `pull_request`.
- Trigger on `push` to `main`.
- Grant only `contents: read` permissions.
- Run on `ubuntu-latest`.
- Check out the repository using the existing `actions/checkout@v4.2.2` convention.
- Install Nix with `cachix/install-nix-action@v31`.
- Run:

```bash
nix flake check --no-build --all-systems --show-trace
```

A single Linux runner is sufficient because this phase evaluates derivations for all four target systems and does not perform native builds. `--no-build` still evaluates flake outputs, including check derivations, but does not execute the NixOS test or build any package. The workflow must not set `NIXPKGS_ALLOW_BROKEN`, `NIXPKGS_ALLOW_UNSUPPORTED_SYSTEM`, `continue-on-error`, or equivalent bypasses.

The workflow does not publish releases, upload binary-cache artifacts, or invoke the existing package-update issue workflows.

## Documentation

Update the `README.md` CI/CD section to state that pull requests and pushes to `main` perform all-system flake evaluation, while package builds and integration tests remain out of scope for this initial CI job. Preserve the existing scheduled upstream-release checks and binary-cache description.

## Verification

After implementation, verify the package sets and evaluation with:

```bash
nix eval --json .#packages.x86_64-darwin --apply builtins.attrNames
nix eval --json .#packages.x86_64-linux --apply builtins.attrNames
nix flake check --no-build --all-systems --show-trace
```

Expected package names include:

- `x86_64-darwin`: the five Any-Sync packages, `anytype-cli`, and `valkey-bloom`; not `anytype-heart`, `anytype-agent-runtime`, or `anytype-mcp`.
- `x86_64-linux`: the five Any-Sync packages, `anytype-heart`, `anytype-cli`, `anytype-agent-runtime`, `anytype-mcp`, and `valkey-bloom`.

The all-system check must evaluate `x86_64-linux`, `aarch64-linux`, `x86_64-darwin`, and `aarch64-darwin` successfully without building or running tests.

Existing non-fatal warnings, including the deprecated singular `overlay` output and deprecated MinIO test options, are outside this change.

## Alternatives Rejected

- Enabling broken and unsupported packages globally would make CI green while retaining invalid outputs.
- Removing Darwin from `supportedSystems` would conceal the problem and contradict the declared platform support.
- Defining every package output explicitly per system would solve the immediate issue but duplicate package names and create manual drift.
- Running native Linux and macOS runner matrices would add cost and runner-availability constraints without improving this evaluation-only check.
- Clearing `anytype-heart`'s Darwin broken flag is not justified without a successful Darwin build and would not solve the Linux-only packages.

## Out Of Scope

- Building or testing Any-Sync packages.
- Running the NixOS VM integration test.
- Changing package versions, hashes, or platform metadata.
- Updating NixOS modules or integration-test configuration.
- Replacing or consolidating the five existing scheduled dependency-update workflows.
- Publishing releases or uploading to the S3 binary cache.
