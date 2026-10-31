# AWS S3 binary cache

The cache is an optional public Nix substituter. The repository does not provision AWS resources or contain a bucket name, account, URL, or key. After live disposable-bucket validation succeeds (publish, idempotent re-publish, dry-run prune, and fresh-store substitution), an operator re-adds the `push: branches: [main]` trigger. Until then, publishing is manually dispatched. Trusted GitHub Actions publish signed package closures for the four native systems (`x86_64-linux`, `aarch64-linux`, `x86_64-darwin`, `aarch64-darwin`) and reusable x86_64 Linux VM inputs after the real test succeeds. Available packages are discovered from the flake. A weekly retention workflow automatically removes obsolete cache entries. Evaluation is not evidence of a successful native build; x86_64 Darwin support is expected to end with nixpkgs 26.05.

## AWS provisioning and trust

Create a dedicated bucket and HTTPS public cache endpoint. Keep S3 Block Public Access enabled except for the specific setting needed to honor the deliberate public-read policy; review account- and bucket-level controls before changing either. Intended anonymous reads are only `nix-cache-info`, root-level `.narinfo` records, and `nar/*`; do not grant public `ListBucket`, writes, or reads of `control/*`. Keep the control prefix private to the workflow IAM user.

Do not assume an S3 resource pattern such as `arn:aws:s3:::BUCKET/*.narinfo` is root-only: IAM `*` can match `/`, so that pattern can also match nested `.narinfo` keys. Enforce root-only metadata reads with an actual mechanism, such as an HTTPS edge that filters paths while the origin bucket remains private, or an explicit anonymous `GetObject` deny for nested `.narinfo` keys that does not deny the authorized writer/collector IAM user. This repository does not provide or validate such a policy. Before exposing the cache, test unauthenticated requests: `nix-cache-info` and a known root-level `.narinfo`/NAR must succeed, while `control/` and a nested `.narinfo` must be denied; also confirm no public listing or write access, and confirm the authorized IAM user still accesses required cache and control objects. Do not treat an untested wildcard policy as enforcing the boundary. Clients use HTTPS, not AWS credentials.

Configure one IAM user for both trusted publisher and pruner. Limit its S3 actions to the cache bucket and required object operations, including reads, writes, listing, and deletes; it must not have access to other buckets. Its access keys are long-lived and can delete cache artifacts if compromised. Store them as repository Actions secrets, rotate them regularly, and never expose them to pull-request jobs or logs. Restrict changes to the default branch and trusted workflows.

The retention workflow runs automatically without manual approval, allowing only `main` to execute cleanup. Both publication and pruning use the same IAM-user credentials; the public PR test workflow uses neither credential. A manual workflow dispatch can run either a dry-run or cleanup.

Set repository Actions **variables** (public/non-secret): `NIX_CACHE_BUCKET`, `NIX_CACHE_REGION`, `NIX_CACHE_URL`, and `NIX_CACHE_PUBLIC_KEY`. Set repository Actions **secrets**: `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from the IAM user, plus `NIX_CACHE_PRIVATE_KEY` from key generation below.

S3 bucket versioning is optional. If enabled, configure lifecycle expiration for **noncurrent versions** after an operator-selected retention period; deleted objects otherwise continue incurring storage charges. If disabled, deletion is permanent. Configure lifecycle cleanup for incomplete multipart uploads. Do not use age-based lifecycle expiry on current `.narinfo` or NAR objects: it is not Nix-reference-aware and bypasses the seven-day protocol. Costs include stored current/noncurrent objects, requests, public data transfer, and any serving/CDN layer; estimate and monitor them for the selected workload and region.

Before first publication, initialize control state once from a genuinely empty bucket using an AWS identity with access to the bucket and the explicit command `CACHE_BUCKET=... python3 scripts/cache-retention.py initialize --initialize-empty`. It refuses a nonempty bucket. Do not reinitialize a live cache. The publisher and collector share `control/lock.json`; contention fails safely and should be investigated/rerun, never bypassed. Locks do not expire automatically. For recovery, inspect the lock record and its GitHub run ID/attempt, confirm the owning run has stopped, then release with its recorded ETag via `CACHE_BUCKET=... python3 scripts/cache-retention.py unlock --etag '"ETAG"'`. Conditional deletion prevents removing a replacement lock. Never clear a lock based only on age. The installed AWS CLI must support the conditional S3 operations used by these commands; verify this against a disposable bucket before production use. The lock ETag check assumes the standard quoted MD5-style ETag returned for single-part PUTs; buckets or encryption defaults producing other ETag shapes are unsupported and must be validated against a disposable bucket.

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

The private control manifest retains two distinct successfully published version strings per package and system, replacing same-version rebuilds, and two latest successful VM stacks. Cleanup marks retained roots and references, records retirement before withdrawing metadata, then waits at least seven days after the last relevant metadata withdrawal before a NAR may be deleted. Shared NARs remain while advertised metadata refers to them. Missing/malformed metadata or uncertain state fails closed. The weekly scheduled workflow executes cleanup without manual approval. A manually dispatched workflow defaults to dry-run; select its destructive option to execute cleanup.

The seven-day period is a per-NAR grace for readers that already obtained metadata before withdrawal. Configure the public HTTP serving layer to send an explicit `.narinfo` `Cache-Control` maximum lifetime of no more than seven days, and verify it on the real endpoint with `curl -I 'https://CACHE-ENDPOINT/STORE-HASH.narinfo'` before relying on it. This repository has no serving-layer or bucket configuration, so it cannot set or verify these headers; the bare S3 endpoint serves metadata without `Cache-Control`, and a client behind a caching intermediary may hold withdrawn metadata past the grace period and fall back to a source build. That is an accepted trade-off. Adding an HTTP edge that sets the header is recommended if the cache gains a wide audience. Independent caches/clients may ignore HTTP cache headers. A client with stale metadata or a download paused beyond the grace can still fail. The cache is not an archive: older revisions can miss after the two-version/stack window, and retention does not promise that an entire historical deployment closure remains available forever.

## Local build and checks

`make build-all` builds the packages exposed on the current native system without AWS credentials. Publishing is performed by the trusted GitHub Actions workflow; no local Yandex upload target remains. Review workflow permissions and AWS trust before enabling the workflows.
