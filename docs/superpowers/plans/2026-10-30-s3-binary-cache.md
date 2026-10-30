# AWS S3 Binary Cache Implementation Plan

> **For agentic workers:** Execute task by task and verify each deliverable. Do not commit or push unless the user explicitly asks. Delegation requires separate user authorization.

**Goal:** Publish all available flake packages for four native systems and reusable Linux VM dependencies to a signed, public AWS S3 cache, while safely retaining the current and previous package versions and VM stacks.

**Architecture:** Trusted GitHub Actions builds publish signed Nix store closures and record successful roots in private S3 control state. A scheduled cleanup uses the same trusted AWS role to traverse retained and advertised Nix metadata, retire obsolete metadata, and delete unreferenced NARs only after a seven-day grace period. Public and PR consumers can read the cache but cannot write or prune it.

**Tech Stack:** Nix flakes and S3 binary cache store, GitHub Actions, AWS S3 and IAM/OIDC, Python 3 standard library and AWS CLI, existing `unittest` framework.

**Spec:** `docs/superpowers/specs/2026-10-30-s3-binary-cache-design.md`

## Global constraints

- Platforms: `x86_64-linux`, `aarch64-linux`, `x86_64-darwin`, `aarch64-darwin`; build each system's actual `packages` outputs natively. Do not claim evaluation proves a build.
- Publish the standalone `valkey-bloom` package and separately publish actual reusable x86_64 Linux test VM inputs, including the overridden Valkey output. Never publish the completed test result as a shortcut around executing the test.
- Pull requests are read-only; secrets and write credentials are available only to trusted default-branch jobs. Use GitHub OIDC, not long-lived AWS access keys. Sign the cache and do not bypass Nix signature verification.
- Keep the latest successful build of the two most recently published distinct version strings per package and system, plus the two most recent successful VM stack publications. Rebuilding the same version replaces its retained root, not the previous distinct version.
- Retire metadata first, preserve affected NARs for at least seven days after the last referring metadata withdrawal, and recheck under coordination before deleting. Recovery state must be durable before withdrawal. Cache misses for older versions are acceptable; a closure download is not guaranteed to complete if its metadata is retired during the download.
- Fail closed on missing metadata, partial closure traversal, uncertain coordination, or invalid control state. Never sweep `nix-cache-info`, control records, unknown keys, or unrelated S3 objects. Do not expire NARs using age-based S3 lifecycle rules.
- Manual AWS provisioning, secrets, and actual native runners are required to validate live publishing. Do not invent bucket names, keys, IAM roles, or claim live validation without them.

## File map

- Modify `.github/workflows/test-nixos.yml`: configure public cache for PR and main VM tests; preserve KVM and test execution.
- Create `.github/workflows/publish-cache.yml`: trusted main builds, native platform matrix, VM dependency publication, and successful publication recording.
- Create `.github/workflows/prune-cache.yml`: scheduled and manually dispatched trusted cleanup, dry-run by default until explicitly enabled.
- Create `scripts/cache-publish.py`: discover/build package roots, prepare signed uploads, verify cache, and update manifest under a lock.
- Create `scripts/cache-retention.py`: lock/control state, `.narinfo` parsing and graph traversal, retirement and deletion logic, and CLI entry points used by workflows.
- Create `tests/test_cache_retention.py` and `tests/test_cache_publish.py`: `unittest` coverage with local fake S3/AWS CLI adapters and temporary Nix-store-shaped fixtures.
- Modify `Makefile` to remove or replace the stale Yandex-only upload targets; update `README.md` and create `docs/binary-cache.md` with provisioning, consumer and operator instructions.

## Control-state and coordination contract

Use a dedicated cache bucket with root-level `<store-hash>.narinfo`, `nar/…` and `nix-cache-info`; private control keys use the separate `control/` prefix. Limit public reads to `nix-cache-info`, root-level `.narinfo` and `nar/`, not `control/`. Validate that bucket-policy pattern matching actually enforces these prefixes before exposing the bucket.

All writers and the collector acquire `control/lock.json` with S3 `PutObject` `If-None-Match: *`; the file contains a random token and GitHub run identity. Hold the lock across Nix uploads, cache verification, manifest changes, metadata withdrawal, and NAR deletion. Release with conditional delete against the acquired ETag. An occupied lock fails the operation without writing; CI must surface the failure and support rerunning it. There is no automatic lock expiry: an operator verifies the owning GitHub run has stopped, then conditionally releases a stale lock. Never delete a lock based only on its age. Verify the installed AWS CLI supports conditional put and delete before enabling writes. Restrict all writers to this protocol; out-of-band S3 modifications invalidate its guarantees.

`control/state.json` is one versioned JSON document, written with an atomic S3 PUT while holding the lock. Its structure is:

```json
{
  "schema": 1,
  "packages": {"x86_64-linux": {"example": [{"version": "2", "roots": ["/nix/store/0123456789abcdfghijklmnpqrsvwxyz-example-2"], "revision": "git-commit", "run_id": "123", "run_attempt": 1}]}},
  "vm_stacks": [{"revision": "git-commit", "run_id": "123", "run_attempt": 1, "roots": ["/nix/store/0123456789abcdfghijklmnpqrsvwxyz-vm-driver"]}],
  "retirements": {"0123456789abcdfghijklmnpqrsvwxyz.narinfo": {"nar": "nar/example.nar.xz", "withdrawn_at": "2026-10-30T12:00:00Z", "metadata": "complete original narinfo text"}},
  "nar_deadlines": {"nar/example.nar.xz": "2026-11-06T12:00:00Z"}
}
```

Package and stack arrays are newest first; at most two distinct versions or stack publications are protected. Record revision, GitHub run ID and attempt for each successful package and VM publication; treat reruns of the same revision and roots as idempotent, not a new previous version or VM stack. Record the signed original metadata and a pending retirement before withdrawing it. After confirmed withdrawal, atomically record the time at or after confirmation and extend that NAR's separate deadline to at least seven days later. An unresolved pending withdrawal blocks NAR deletion until recovered. If a run fails between these writes, resume conservatively: confirm or repeat withdrawal and start a fresh seven-day period; never infer an earlier time. When a root is reintroduced, re-publish/restore its signed metadata and entire closure, verify it is available, then update state; remove or supersede metadata retirement records only after this succeeds, but preserve the original NAR deadline independently until that NAR is safely deleted. Do not initialize missing state if the bucket is nonempty: distinguish explicitly provisioned empty state from missing/corrupt control data and abort on ambiguity.

All S3 listing must paginate. Parse Nix metadata strictly; recognize only root-level names matching the Nix store-hash `.narinfo` format and `nar/` objects actually referenced by valid records. Derive referenced store hashes from `.narinfo` `References` and require the expected store directory and valid safe relative NAR URL. Unknown compression, paths, duplicate required fields, absent records, unexpected references, or unsupported encodings stop the run without deletion. Never turn an unparseable or foreign object into a deletion candidate. Because a NAR may be shared, use its durable per-NAR deadline, extending it for every confirmed metadata withdrawal even when its former metadata record is later replaced; if any advertised record refers to it, do not delete it. For partially failed runs, use a later conservative timestamp.

## Task 1: Establish public cache configuration and native VM roots

**Files:** `.github/workflows/test-nixos.yml`, `tests/test_cache_publish.py`, `docs/binary-cache.md`.

**Consumes:** `vars.NIX_CACHE_URL`, `vars.NIX_CACHE_PUBLIC_KEY` configured by the operator. **Produces:** cache-enabled existing CI; documented evaluated paths for the VM driver and customized Valkey.

- [ ] Add a workflow configuration test that reads `.github/workflows/test-nixos.yml` and fails if the VM build is removed, the cache URL/public key are missing, or `trusted = true`/`require-sigs = false` appears. Add a negative fixture that changes the test build command to a no-op and assert the check rejects it.
- [ ] Configure Nix with the public URL and public key using the existing install action's documented `extra_nix_config`, retaining the default `https://cache.nixos.org` substituter and its trusted key. Do not add AWS or signing secrets to this PR-capable workflow. Keep the existing KVM checks and actual `nix build` command.
- [ ] Evaluate the derivations rather than assuming the test output closure contains its inputs:

```sh
nix eval --raw .#checks.x86_64-linux.any-sync-test.driver.drvPath
nix eval --raw .#checks.x86_64-linux.any-sync-test.nodes.server.services.redis.package.drvPath
nix eval --raw .#checks.x86_64-linux.any-sync-test.nodes.server.services.redis.package.outPath
```

- [ ] On x86_64 Linux, build `.#checks.x86_64-linux.any-sync-test.driver` and inspect its runtime closure with `nix path-info -r`. Check for the exact evaluated customized Valkey output, not a substring such as `valkey`. If absent, include the explicit overridden Valkey output as a second VM root; include other actual VM outputs required to avoid rebuilding them. Verify the chosen roots by testing a clean store later, rather than assuming the driver includes everything.
- [ ] Run `python3 -m unittest discover -s tests -v` and `nix flake check --no-build --all-systems --show-trace`. On a Linux KVM host also run `nix build --show-trace --print-build-logs .#checks.x86_64-linux.any-sync-test`.

## Task 2: Build and verify the lock and manifest primitives

**Files:** `scripts/cache-retention.py`, `tests/test_cache_retention.py`.

**Consumes:** AWS CLI credentials and bucket supplied through environment. **Produces:** `lock`, `unlock`, state parsing and update primitives used by both publishing and pruning.

- [ ] Write failing `unittest` cases for conditional lock creation: the first owner succeeds, a second owner fails without touching state, and release with the wrong ETag does not remove the first owner's lock. Test missing state, malformed JSON, unsupported schema, duplicate versions and invalid store paths all fail closed.
- [ ] Implement `aws` calls using argument arrays with `subprocess.run(..., check=True)`; do not invoke a shell or interpolate credentials. Use `aws s3api put-object --if-none-match '*'` and `aws s3api delete-object --if-match "$etag"`; verify the AWS CLI's actual return status and ETag format with disposable S3 before live use. Implement signal-safe `finally` release when possible; document manual recovery for killed runners.
- [ ] Implement strict state validation and atomic PUT only while holding the acquired lock. Define a one-time initialization command that requires an explicit `--initialize-empty` flag and confirms no cache metadata, NARs or control state exist. It must refuse a nonempty bucket.
- [ ] Write tests for successive versions `1 → 2 → 3`, same-version rebuild `3a → 3b`, independent platforms, failed verification, two VM stack revisions, and an idempotent retry of the same revision and roots. Verify `3b` and `2` remain protected, run identity is persisted, retry does not displace the prior VM stack, and a failed publication never changes state. Make tests pass and run the complete Python suite.

## Task 3: Implement native package publishing

**Files:** `scripts/cache-publish.py`, `tests/test_cache_publish.py`, `.github/workflows/publish-cache.yml`.

**Consumes:** public cache URL/key, private signing key, bucket, region, OIDC writer role. **Produces:** signed package closures and manifest entries per successful package/system.

- [ ] Add tests that stub the `nix` executable and demonstrate dynamic discovery, one build per exposed package, actual version/root recording, skip of unavailable attributes, and nonzero exit on build or verification failure. Assert state does not advance if copying or closure verification fails, and that an unchanged store path is not recorded as a new version.
- [ ] Discover package names with `nix eval --json .#packages.<system> --apply builtins.attrNames`; obtain each package's evaluated `version` and build each selected flake attribute with `nix build --no-link --print-out-paths`. Reject empty outputs or ambiguous version metadata. Record every output path emitted by Nix, not only the default `result` symlink.
- [ ] Under the lock, use `nix copy --to "s3://<bucket>?region=<region>&secret-key=<temporary-file>" <roots...>`; create the destination URI using URL encoding, not shell interpolation. For each root, validate the destination closure using Nix path information and signed `.narinfo`, and check the NAR objects exist. Force fresh metadata reads for verification. Only then update state. Nix's destination path-existence checks should avoid uploading paths already present; verify with repeated uploads against a disposable bucket rather than assuming it.
- [ ] Add a trusted push-to-`main` workflow with native runners: `ubuntu-24.04`, `ubuntu-24.04-arm`, `macos-15-intel`, `macos-15`. Verify each runner's reported `nix eval --impure --raw --expr builtins.currentSystem` matches its matrix system. Pin actions consistently with repository conventions. Set `id-token: write` only for the writer job and use `aws-actions/configure-aws-credentials` with the operator's writer role. Explicitly handle unavailable runners as failed validation, never silently skip them.
- [ ] Use `strategy.max-parallel: 1` for the publishing matrix so its jobs do not contend for the lock. Other trusted workflows may still contend: fail visibly and rerun rather than bypassing the lock or pretending publication succeeded. Write the signing key from a secret to a mode-0600 temporary file without logging it; remove it using a shell trap. Set read-only permissions on all other jobs.
- [ ] Run the test suite and all-system evaluation. On each native runner validate every exposed package builds and publishes; record any build or platform failures instead of changing package metadata to hide them.

## Task 4: Publish reusable VM roots without skipping the test

**Files:** `.github/workflows/publish-cache.yml`, `scripts/cache-publish.py`, `tests/test_cache_publish.py`.

**Consumes:** VM root discovery from Task 1 and successful actual VM test; **produces:** signed VM roots and successful stack retention entry.

- [ ] Add failing tests covering explicit VM roots, rejection of the test result as a root, no state change after a failed test or upload, and retention of the two latest successful stack revisions.
- [ ] On x86_64 Linux, run the existing KVM verification and actual VM test, then build the VM driver and any explicitly identified additional roots. Use `nix path-info -r` to verify the exact custom Valkey path is included in the union of published roots. Copy those roots under the same lock and verify the closure. Advance the VM stack entry only after all checks pass. Do not copy `.#checks.x86_64-linux.any-sync-test` itself.
- [ ] Verify on a fresh Linux store or independent clean runner: enable only the public cache plus the normal NixOS cache, confirm the custom Valkey path substitutes from the project cache rather than builds, and confirm the VM test actually executes. Separately verify `valkey-bloom` substitutes as a package. Test a failed VM test does not advance the stack record.

## Task 5: Implement safe staged retention and scheduled dry run

**Files:** `scripts/cache-retention.py`, `tests/test_cache_retention.py`, `.github/workflows/prune-cache.yml`.

**Consumes:** Task 2 state and lock; **produces:** a dry-run report and, when explicitly enabled, staged metadata withdrawal and later NAR deletion.

- [ ] Write failing graph tests with explicit fake metadata: `root-v3 → shared`, `root-v2 → shared`, and `root-v1 → obsolete`; make two `.narinfo` records point to the same `nar/shared.nar.xz`. Assert the retained traversal protects `shared` and that malformed/missing metadata aborts before any deletion.
- [ ] Add tests for: a paused reader that already fetched old metadata; a reader using cached metadata; metadata withdrawn at time `T` with NAR present at `T + 7 days - 1 second` and eligible at `T + 7 days`; the final referring metadata withdrawal resetting the grace; a newly advertised or retained reference preventing NAR deletion; interrupted state write/withdrawal; a missing timestamp; paginated S3 listings; unrelated `control/`, `nix-cache-info` and foreign objects surviving. For two metadata records sharing NAR A withdrawn on different dates, republish the later record pointing to NAR B and assert A's later deadline survives. Use an injected UTC clock and fake S3 operations, not real sleeps.
- [ ] Implement mark: under the lock, parse state; enumerate and validate recognized public metadata; traverse all retained roots and references; construct a mapping of each advertised NAR to all referencing metadata. If any required record is missing, malformed, or cannot be read, abort without deletion.
- [ ] Implement retire: for each unmarked advertised metadata entry, persist a pending record containing its complete original signed contents and NAR mapping before withdrawal; withdraw its `.narinfo`; atomically record the confirmed withdrawal time and extend the independent per-NAR deadline to at least seven days later. Repeating after interruption must be safe and restart the seven-day clock conservatively. Never withdraw marked metadata.
- [ ] Implement sweep: only after the durable per-NAR deadline, if no withdrawal remains unresolved and no advertised record references the NAR, recompute retained reachability and advertised references while holding the lock and delete the recognized NAR. Remove its deadline only after confirmed NAR deletion. Unknown or incomplete retirement history must leave the NAR in place. A dry run may create and release its coordination lock, but must not mutate cache objects, manifests, or retirement state; test this boundary.
- [ ] Schedule a trusted cleanup workflow weekly and expose `workflow_dispatch`. Use the same bucket-scoped OIDC role as publication, including its read, write, and delete permissions. Default to dry-run; require an explicitly configured GitHub environment approval or repository variable before destructive mode. The job uses the same lock as publishers and fails visibly on contention. Validate action conditions cannot execute destructive cleanup from PRs or untrusted refs.
- [ ] Run the unit suite. Against a disposable, nonproduction S3 bucket with controlled credentials, test two cleanup runs separated by an injected test clock, verify the cache's current/previous roots are substitutable and control objects survive, and confirm real deletion reclaims unversioned objects. Do not advance production's seven-day clock artificially.

## Task 6: Provisioning, consumer documentation, and final verification

**Files:** `README.md`, `docs/binary-cache.md`, `Makefile`.

- [ ] Document public bucket read policy limited to `nix-cache-info`, root-level `.narinfo`, and `nar/`; private `control/` permissions; S3 public-access-block implications; the single trusted role's bucket-scoped read/write/delete permissions and the accepted risk that a compromised trusted workflow can delete artifacts; OIDC repository/default-branch trust and audience; GitHub variables/secrets and environment approval. Test that PR identities cannot assume the role. Include AWS bucket versioning, noncurrent-version expiration, multipart cleanup, costs, and operational lock recovery. Do not grant public `ListBucket` or public read of `control/` merely for convenience.
- [ ] Configure the public HTTP serving layer to return explicit `.narinfo` cache-control with a maximum lifetime no longer than seven days; verify actual response headers with `curl`. Exercise a cached-metadata reader through withdrawal and confirm its NAR remains available through the bounded grace period. Document that independent caches may ignore these headers.
- [ ] Document generating a cache signing key on a trusted machine, storing only the private key as a secret, client `substituters` and `trusted-public-keys` setup, standard NixOS cache preservation, key rotation, and the fact that accepting flake-provided configuration is not automatic. Document the seven-day per-NAR grace and older-revision/whole-closure limitations.
- [ ] Replace the Yandex-specific README and Makefile instructions with the selected AWS publication workflow; do not remove useful local build targets without replacing their documented purpose. Avoid embedding actual bucket names, AWS account IDs, or secrets.
- [ ] Run:

```sh
python3 -m unittest discover -s tests -v
nix flake check --no-build --all-systems --show-trace
nix build --show-trace --print-build-logs .#checks.x86_64-linux.any-sync-test
git diff --check
```

- [ ] In an isolated clean Nix store with signature verification required and only the disposable cache configured, prove a normally signed input-addressed output substitutes with the configured public key, while an unsigned output and an output signed by a different key are rejected. Avoid content-addressed paths and existing local copies that could bypass the signature check.
- [ ] Review GitHub workflow syntax and security, then run the live native matrix, fresh-store substitution, failed-publication, re-publication, dry-run, and disposable-bucket pruning checks listed above. Confirm `x86_64-darwin`'s future Nixpkgs support limitation in docs. Record exact blocked commands and reasons if AWS, native runners, or Linux KVM are unavailable; do not report them as passing.
