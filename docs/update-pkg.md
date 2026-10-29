# Any-Sync package maintenance

The `Update Any-Sync packages` workflow runs daily and can also be started with
`workflow_dispatch`. Each of the five packages is updated independently with
`nix-update` from the flake's pinned nixpkgs. A changed package gets its own
`automation/update-<package>` branch and pull request; no change creates no PR.
The GitHub App token makes the existing PR evaluation and NixOS VM checks run
without manual workflow approval. Review and merge PRs manually.

A failed update job leaves its package name and error in the Actions run. A
failure after the PR is opened appears in that PR's checks. The project skill
`/skill:investigating-package-updates` guides Pi through either failure. Hermes
polling and automatic agent invocation are not part of this workflow.

## Update manually

Run from the repository root, replacing the package name:

```sh
nix shell --inputs-from . nixpkgs#nix-update --command nix-update --flake any-sync-node
nix build --print-build-logs .#any-sync-node
nix flake check --no-build --all-systems --show-trace
```

On an x86_64 Linux host with KVM, also run the stack integration test:

```sh
nix build --show-trace --print-build-logs .#checks.x86_64-linux.any-sync-test
```

Inspect the diff and upstream release notes, including compatibility and local
patches. Some package expressions disable upstream tests; a successful build is
not evidence that those tests ran. Do not change `flake.lock` as part of a
package-only update.
