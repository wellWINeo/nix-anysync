# AWS S3 binary cache

The cache is an optional public Nix substituter. The repository does not provision AWS resources or contain a bucket name, account, URL, or key. Trusted GitHub Actions on `main` publish signed package closures for the four native systems (`x86_64-linux`, `aarch64-linux`, `x86_64-darwin`, `aarch64-darwin`) and reusable x86_64 Linux VM inputs after the real test succeeds. Available packages are discovered from the flake. A weekly retention workflow defaults to dry-run. Evaluation is not evidence of a successful native build; x86_64 Darwin support is expected to end with nixpkgs 26.05.

## AWS provisioning and trust

Create a dedicated bucket and HTTPS public cache endpoint. Keep S3 Block Public Access enabled except for the specific setting needed to honor the deliberate public-read policy; review account- and bucket-level controls before changing either. Intended anonymous reads are only `nix-cache-info`, root-level `.narinfo` records, and `nar/*`; do not grant public `ListBucket`, writes, or reads of `control/*`. Keep the control prefix private to the workflow role.

Do not assume an S3 resource pattern such as `arn:aws:s3:::BUCKET/*.narinfo` is root-only: IAM `*` can match `/`, so that pattern can also match nested `.narinfo` keys. Enforce root-only metadata reads with an actual mechanism, such as an HTTPS edge that filters paths while the origin bucket remains private, or an explicit anonymous `GetObject` deny for nested `.narinfo` keys that does not deny the authorized writer/collector role. This repository does not provide or validate such a policy. Before exposing the cache, test unauthenticated requests: `nix-cache-info` and a known root-level `.narinfo`/NAR must succeed, while `control/` and a nested `.narinfo` must be denied; also confirm no public listing or write access, and confirm the authorized role still accesses required cache and control objects. Do not treat an untested wildcard policy as enforcing the boundary. Clients use HTTPS, not AWS credentials.

Configure one IAM role for both trusted publisher and pruner. Limit its S3 actions to the cache bucket and required object operations, including reads, writes, listing, and deletes; restrict object access to cache objects and `control/*` as required by the scripts. It must not grant access to other buckets. The same role can delete cache artifacts: a compromised trusted workflow or role can destroy cache data. This accepted risk is why untrusted jobs must never receive its credentials. Use GitHub OIDC, not static AWS keys. The role trust policy must require audience `sts.amazonaws.com` and allow only these two exact repository subjects (replace placeholders):

- Publisher: `repo:OWNER/REPO:ref:refs/heads/main`
- Pruner: `repo:OWNER/REPO:environment:cache-prune`

The trust policy must not allow a `pull_request` subject or wildcard repository subjects. The environment subject does **not** include the branch: configure the `cache-prune` GitHub environment with required reviewers and deployment branch restrictions allowing only `main`. Retain the workflows' explicit main-ref and destructive-mode checks. Verify trust conditions in IAM and test that a PR identity cannot assume the role before enabling publication; do not infer this from workflow syntax alone.

Set repository Actions **variables** (all public/non-secret): `NIX_CACHE_BUCKET`, `NIX_CACHE_REGION`, `NIX_CACHE_URL`, `NIX_CACHE_PUBLIC_KEY`, and `CACHE_WRITER_ROLE_ARN`. Set secret `NIX_CACHE_PRIVATE_KEY` only after key generation below. For pruning, configure `CACHE_PRUNE_ENABLED=true` only after reviewing dry runs and environment protections; otherwise pruning remains dry-run. The publisher consumes public URL/key and region/bucket. The workflows consume the role ARN and use OIDC. Never put AWS access keys in GitHub secrets.

Enable S3 bucket versioning and configure lifecycle expiration for **noncurrent versions** after an operator-selected retention period, plus abort incomplete multipart uploads. Versioning can preserve deleted current objects as noncurrent versions and continue incurring storage charges; expiration policy and actual reclamation should be checked explicitly. Do not use age-based lifecycle expiry on current `.narinfo` or NAR objects: it is not Nix-reference-aware and bypasses the seven-day protocol. Costs include stored current/noncurrent objects, requests, public data transfer, and any serving/CDN layer; estimate and monitor them for the selected workload and region.

Before first publication, initialize control state once from a genuinely empty bucket using the trusted role and the explicit command `CACHE_BUCKET=... python3 scripts/cache-retention.py initialize --initialize-empty`. It refuses a nonempty bucket. Do not reinitialize a live cache. The publisher and collector share `control/lock.json`; contention fails safely and should be investigated/rerun, never bypassed. Locks do not expire automatically. For recovery, inspect the lock record and its GitHub run ID/attempt, confirm the owning run has stopped, then release with its recorded ETag via `CACHE_BUCKET=... python3 scripts/cache-retention.py unlock --etag '"ETAG"'`. Conditional deletion prevents removing a replacement lock. Never clear a lock based only on age. The installed AWS CLI must support the conditional S3 operations used by these commands; verify this against a disposable bucket before production use.

## Signing key and consumer setup

On a trusted machine with Nix installed, generate the cache key pair and keep the private key offline/secret:

```sh
nix key generate-secret --key-name nix-anysync-cache-1 > cache-private-key
chmod 600 cache-private-key
nix key convert-secret-to-public < cache-private-key
```

Configure the resulting public key as `NIX_CACHE_PUBLIC_KEY`, and store the private-key contents as GitHub Actions secret `NIX_CACHE_PRIVATE_KEY`. Never commit, print in CI logs, or distribute the private key. For rotation, publish/trust the new public key on clients before signing new entries with it; keep old public trust during the overlap while old signed cache metadata remains advertised, then remove it only when no longer needed.

A client can use ordinary Nix configuration (substitute the provisioned HTTPS URL and matching public key):

```ini
extra-substituters = https://CACHE-ENDPOINT
extra-trusted-public-keys = nix-anysync-cache-1:PUBLIC-KEY-MATERIAL
```

For one-off testing use equivalent `nix --option extra-substituters ... --option extra-trusted-public-keys ...` options. Preserve the standard `https://cache.nixos.org` substituter and its trusted key; do not disable signature checking or mark arbitrary keys trusted. NixOS users should add these settings through their normal NixOS Nix configuration and preserve the distribution's standard substituters/keys. Merely accepting a flake's configuration or `nixConfig` does not mean a client automatically trusts its substituter/key: review and explicitly authorize the settings through the client's normal trust mechanism.

## Retention and limitations

The private control manifest retains two distinct successfully published version strings per package and system, replacing same-version rebuilds, and two latest successful VM stacks. Cleanup marks retained roots and references, records retirement before withdrawing metadata, then waits at least seven days after the last relevant metadata withdrawal before a NAR may be deleted. Shared NARs remain while advertised metadata refers to them. Missing/malformed metadata or uncertain state fails closed. Dry-run is the default; inspect its report before an approved manual destructive run with `CACHE_PRUNE_ENABLED=true`.

The seven-day period is a per-NAR grace for readers that already obtained metadata before withdrawal. Configure the public HTTP serving layer to send an explicit `.narinfo` `Cache-Control` maximum lifetime of no more than seven days, and verify it on the real endpoint with `curl -I 'https://CACHE-ENDPOINT/STORE-HASH.narinfo'` before relying on it. This repository has no serving-layer or bucket configuration, so it cannot set or verify these headers; do not enable destructive pruning until the actual endpoint is configured and checked. Independent caches/clients may ignore HTTP cache headers. A client with stale metadata or a download paused beyond the grace can still fail. The cache is not an archive: older revisions can miss after the two-version/stack window, and retention does not promise that an entire historical deployment closure remains available forever.

## Local build and checks

`make build-all` builds the packages exposed on the current native system without AWS credentials. Publishing is performed by the trusted GitHub Actions workflow; no local Yandex upload target remains. Review workflow permissions and AWS trust before enabling the workflows.
