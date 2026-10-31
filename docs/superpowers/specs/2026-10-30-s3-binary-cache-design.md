# AWS S3 Binary Cache Design

## Goal

Publish reusable, signed Nix binaries to a publicly readable AWS S3 cache so that users on small machines can install the flake's packages without building them and CI can reuse the NixOS VM test's expensive dependencies, including its customized Valkey build. Preserve current and previous package versions and VM stacks while eventually removing unneeded cache objects.

## Current state

- `.github/workflows/test-nixos.yml` runs the x86_64 Linux VM test for pull requests and pushes to `main`; it does not configure a project binary cache.
- `Makefile` has a manual S3-compatible upload to Yandex Cloud, not AWS, and does not publish from CI. AWS is the selected backend for this design.
- The flake exposes ten packages on each Linux architecture and seven on each Darwin architecture. `anytype-agent-runtime` and `anytype-mcp` are Linux-only; `anytype-heart` is marked broken on Darwin by its inherited metadata. The flake already filters unavailable and broken outputs. Evaluation alone does not prove a package builds.
- The VM test overrides Valkey to disable its checks and wrap the server with the `valkey-bloom` module; this is a distinct derivation from ordinary Valkey. The test also installs ordinary Valkey. `valkey-bloom` is independently exposed as a package and is useful in deployments, not just tests.
- Nixpkgs warns that its 26.05 release is the last with x86_64 Darwin support. This is a future constraint, not a reason to remove the current platform.

## Package publishing

Use GitHub-hosted native runners for `x86_64-linux`, `aarch64-linux`, `x86_64-darwin`, and `aarch64-darwin`, subject to runner availability for the repository. Build every package exposed by `packages.<system>` on the corresponding native system, not a hard-coded list that could drift. Do not manufacture outputs for packages the flake excludes. A failed build must be visible and must not be reported as a successful publication; do not silently skip failures. Actual platform support is established by builds, not metadata alone.

Trusted `main` CI runs publish built outputs and their required runtime closures to the AWS S3 cache using Nix's S3 store support. Nix store paths, rather than version strings, determine whether an object is new: changed source, patches, dependencies, or build settings can produce a new output even if the package version is unchanged. Existing cache paths should not be uploaded again. Do not use the final VM test output as a substitute for its build dependencies or publish it in a way that silently turns future intended test executions into cache hits.

All pull-request CI, including fork PRs, may read the public cache but must not receive AWS write credentials or the Nix signing secret. Only trusted default-branch code can publish or prune. A PR with new derivations may therefore build them before they are published after merge; this trade-off is intentional.

## VM dependency publishing

Identify explicit reusable roots for the x86_64 Linux VM test, including the customized Valkey output. Publish those roots and their runtime closures after a successful trusted test build. The flake's standalone `valkey-bloom` output is published independently on every platform on which it is exposed.

The test result's runtime closure is insufficient evidence that its build-time VM dependencies were published. Inspect the evaluated test and its derivation graph to select real VM dependency roots, avoiding an indiscriminate upload of every local store path. Verify on a fresh, empty store or equivalent clean runner that the customized Valkey output is substituted rather than rebuilt, and that the VM test actually runs. A failed test must not advance the retained VM stack roots.

## Access and trust

Serve cache objects publicly over HTTPS so users do not need AWS credentials. Publish the matching Nix public signing key and document how to add the substituter and trusted key to Nix configuration; do not rely on flake-provided settings being automatically accepted by every client. Preserve normal signature verification. Bucket policy grants public read only to the cache objects and denies public write.

Use one IAM user restricted to the cache bucket's required read, write, and delete operations. Store its access key ID and secret access key as GitHub Actions repository secrets, and expose them only to the trusted publication and cleanup workflows, not pull-request jobs. These are long-lived credentials; rotate them regularly. A compromised trusted workflow or leaked key can delete cache objects. Store the Nix signing private key in a separate GitHub Actions secret, materialize it only for the publication step with restrictive permissions, and remove it afterward. Never print credentials or keys. Bucket, region, public cache URL, and public key are deployment-specific configuration, not hard-coded assumptions.

## Retention and safe cleanup

Maintain durable publication manifests recording package name, version, platform, output roots, and successful publication identity, plus the roots of each successful VM stack publication. Update authoritative retention state only after the relevant build, upload, and closure verification succeed. A partially failed matrix or interrupted upload must not replace the last known-good manifest for an affected package or VM stack.

For every package and supported system, preserve the latest successfully published build for the current and previous distinct published version strings. If a package is rebuilt with the same version string, the latest successful build replaces that version's earlier retained root; the previous distinct version remains protected. Preserve the VM dependency roots for the current and previous successful stack publications. Track versions from successful publications, not from wall-clock object age.

A trusted cleanup job computes reachability from all retained roots via Nix store references and maps cache `.narinfo` records to their NAR objects. Shared references and NAR objects are retained if any protected root needs them. Coordinate publication, manifest changes, and cleanup so retirement and deletion cannot race an upload or a new root becoming authoritative. Missing or malformed metadata, incomplete traversal, uncertain manifest state, or loss of coordination must abort deletion. Provide a dry-run mode and inspect its output before enabling deletion.

Retirement has two stages. Before withdrawing an unretained `.narinfo`, durably record its complete signed contents and NAR mapping as a pending withdrawal. After confirmation, record the withdrawal time and extend a separate per-NAR deletion deadline to at least seven days after that time. Preserve this deadline independently of metadata records, including when metadata is republished with a different NAR, until the old NAR is safely deleted. If the withdrawal time is uncertain, restart the seven-day period conservatively. Never delete a NAR while any advertised `.narinfo` refers to it; after the last referring metadata is withdrawn, its deadline must be at least seven days in the future. Before deletion, reacquire publication coordination and recheck both retained roots and all currently advertised `.narinfo` records. If a retired path becomes retained, restore its signed metadata and verify its closure before making the root authoritative. Interrupted retirement must be recoverable without losing the mappings or deleting early.

The grace period protects readers that obtained metadata shortly before withdrawal and complete their download within seven days. It cannot guarantee safety for clients with stale metadata or downloads paused beyond that interval; document that bounded guarantee and avoid HTTP metadata caching longer than the grace period. Test withdrawal, a reader paused between metadata and NAR requests, cached metadata, shared NARs, and a path becoming retained again during retirement.

The collector may remove only recognized store-path `.narinfo` records and NAR objects in the cache's designated object namespaces. It must never sweep `nix-cache-info`, manifests, retirement records, coordination state, or unknown keys. Keep control records in a separately permissioned prefix outside the sweep and test that control and unrelated objects survive.

S3 lifecycle age rules alone are not Nix-aware and must not be used to expire cache NARs and metadata. Lifecycle can clean ancillary objects such as incomplete multipart uploads; if bucket versioning is enabled, document how noncurrent object versions affect actual storage reclamation. Cache misses for revisions older than the retained set are acceptable.

## Verification

- Evaluate all four package sets and run native builds for every exposed package. Record unsupported packages without attempting to bypass their metadata.
- Verify ordinary package deployment from a clean Nix store with the public cache and trusted public key; verify an untrusted or missing signature is rejected.
- From a fresh Linux runner, show that the customized Valkey output is fetched from the cache instead of built, and that the VM test is still executed. Confirm the standalone `valkey-bloom` package is independently substitutable.
- Test retention against multiple versions and platforms, same-version rebuilds, shared store references and NAR objects, partially failed builds, missing metadata, interrupted publication or retirement, and concurrent publish/prune attempts. Verify staged withdrawal, the seven-day grace from the last metadata withdrawal, a paused reader, stale cached metadata, renewed retention, and survival of control and unrelated objects. Verify that the current and previous roots remain substitutable after cleanup.
- Run the existing Python tests, flake evaluation, and NixOS VM test as applicable. Validate workflow syntax and permissions. Record runner, AWS credential, or KVM limitations honestly if full end-to-end verification is unavailable.

## Documentation and scope

Document cache client setup, supported platforms, trust and publication boundaries, AWS and GitHub setup, retention behavior, cleanup recovery and dry-run procedure, and the fact that retained cache versions are not a guarantee of indefinite historical availability. Update the existing README cache description and resolve the stale Yandex-only manual upload instructions consistently with the selected AWS backend.

No new package versions, changes to package platform metadata, public write access, PR-secret exposure, custom cache service, or unrelated module refactoring are part of this design.
