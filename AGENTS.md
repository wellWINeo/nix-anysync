# AGENTS.md

## Project Overview

**nix-anysync** is a Nix flake for self-hosting the [Any-Sync](https://anytype.io) infrastructure. It packages 5 Go-based components from the [anyproto](https://github.com/anyproto) organization and provides NixOS modules for running them as systemd services.

### Components

| Package | Description |
|---------|-------------|
| `any-sync-tools` | Config builder and network debugger (`anyconf`, `any-sync-network`, `any-sync-netcheck`) |
| `any-sync-node` | Tree node (supports multiple replicas) |
| `any-sync-coordinator` | Coordinator node |
| `any-sync-consensus` | Consensus node |
| `any-sync-filenode` | File storage node |

## Repository Structure

```
flake.nix                          # Flake definition (inputs, outputs, overlay, modules, devShell)
pkgs/any-sync/*.nix                # Package definitions (all use buildGoModule)
nixos/modules/any-sync/*.nix       # NixOS service modules (systemd units)
nixos/modules/any-sync/common.nix  # Shared module helpers (user/group, config path)
nixos/tests/any-sync-test.nix      # Integration test (2 VMs, full stack)
maintainers/maintainer-list.nix    # Maintainer metadata
docs/update-pkg.md                 # How to update package versions
Makefile                           # Build + upload to S3 binary cache
.github/                           # CI: daily version-check workflows per package
```

## Build System

- **Single input**: `nixpkgs` (nixos-25.05)
- **Supported systems**: x86_64-linux, x86_64-darwin, aarch64-linux, aarch64-darwin
- **Dev shell**: `nixfmt-rfc-style` (formatter) + `nixd` (LSP)

### Common Commands

```bash
nix build .#any-sync-node         # Build a single package
nix build .#any-sync-tools        # Build tools package
nix flake check                   # Run integration test
nix develop                       # Enter dev shell with formatter + LSP
```

## Code Conventions

### Nix Style
- Format with `nixfmt-rfc-style` (available in dev shell)
- 2-space indentation, UTF-8, LF line endings
- Makefile uses tabs (per standard)

### Package Definitions (`pkgs/any-sync/*.nix`)
All packages follow the same template:
```nix
{ pkgs, fetchFromGitHub, lib }:
let
  version = "X.Y.Z";
  maintainers = import ../../maintainers/maintainer-list.nix;
in
pkgs.buildGoModule {
  pname = "any-sync-<name>";
  inherit version;
  src = fetchFromGitHub {
    owner = "anyproto";
    repo = "any-sync-<name>";
    tag = "v${version}";
    sha256 = "sha256-...";
  };
  vendorHash = "sha256-...";
  meta = { description = "..."; homepage = "..."; license = lib.licenses.mit; maintainers = [ maintainers.wellWINeo ]; };
}
```

When updating a package version, follow the 4-step process in `docs/update-pkg.md`:
1. Update `version`
2. Clear `sha256`, build to get new hash, update it
3. Clear `vendorHash`, build to get new hash, update it
4. Test the build

### NixOS Modules (`nixos/modules/any-sync/*.nix`)
- All services run as `any-sync:any-sync` user/group
- Systemd hardening: PrivateTmp, ProtectSystem=full, NoNewPrivileges, LimitNOFILE=65536
- Config via `config` attribute (inline) or `configPath` (external file)
- `any-sync-node` supports multiple replicas via list config
- Shared helpers live in `common.nix`

## Testing

Integration test in `nixos/tests/any-sync-test.nix`:
- 2 NixOS VMs (server + client)
- Server runs all 5 Any-Sync services + MongoDB, Redis, MinIO
- Client validates connectivity via `any-sync-netcheck`
- Run with `nix flake check`

**Note**: Tests exist but are not fully validated yet.

## CI/CD

- 5 GitHub Actions workflows (one per package) run daily to check for upstream releases
- New releases trigger issue creation with label `dependency-update`
- Binary cache uploads go to S3 on Yandex Cloud (see Makefile)

## External Dependencies (Runtime)

The Any-Sync stack requires:
- **MongoDB** - storage backend for consensus and coordinator
- **Redis** (with RedisBloom module in production) - indexing for filenode
- **S3-compatible storage** (MinIO or similar) - file storage backend
