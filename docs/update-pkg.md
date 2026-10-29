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

## Set up the GitHub App

A repository administrator must complete this once before updates can create
PRs. GitHub's [app registration guide](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app)
and [private key guide](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/managing-private-keys-for-github-apps)
cover the current GitHub interface.

1. In GitHub **Settings → Developer settings → GitHub Apps**, register a new
   app. Give it a unique name and a homepage URL. Disable the webhook; it is not
   needed.
2. Under **Repository permissions**, grant **Contents: Read and write** and
   **Pull requests: Read and write**. GitHub also grants metadata read access.
   No Actions, workflow, or administration write permission is required.
3. Create the app and note its **App ID** from its General settings. In
   **Private keys**, generate a private key; keep the downloaded PEM file
   private and never commit it.
4. Install the app on the repository owner's account, choosing **Only select
   repositories** and selecting this repository.
5. In the repository's **Settings → Secrets and variables → Actions**, add:

   | Type | Name | Value |
   | --- | --- | --- |
   | Variable | `PACKAGE_UPDATE_APP_ID` | App ID |
   | Secret | `PACKAGE_UPDATE_APP_PRIVATE_KEY` | Complete PEM private key |
   | Variable | `PACKAGE_UPDATE_AUTHOR_NAME` | Maintainer's Git author name |
   | Variable | `PACKAGE_UPDATE_AUTHOR_EMAIL` | Maintainer's Git author email |

   The author variables identify the human maintainer on update commits; use an
   email associated with the maintainer's GitHub account if attribution there is
   desired. The app creates the PR and authenticates the push.
6. After this workflow is on the default branch, run it from the Actions tab.
   If an update exists, verify that the PR is created and both PR workflows
   start automatically. If no updates exist, there will be no PR or token step;
   test again when an update is available. Check the failed job log for missing
   credentials or permissions.

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
