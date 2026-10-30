#!/usr/bin/env python3
"""Build and publish the packages exposed by one native flake system."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import quote

import importlib.util

_RETENTION_PATH = Path(__file__).with_name("cache-retention.py")
_SPEC = importlib.util.spec_from_file_location("cache_retention", _RETENTION_PATH)
retention = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(retention)

SYSTEMS = {"x86_64-linux", "aarch64-linux", "x86_64-darwin", "aarch64-darwin"}
BUCKET_NAME = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
REGION_NAME = re.compile(r"^[a-z0-9-]+$")


class PublishError(RuntimeError):
    """A build or cache publication could not be safely completed."""


def destination_uri(bucket, region, secret_key_file):
    if not isinstance(bucket, str) or not BUCKET_NAME.fullmatch(bucket):
        raise PublishError("CACHE_BUCKET is missing or invalid")
    if not isinstance(region, str) or not REGION_NAME.fullmatch(region):
        raise PublishError("CACHE_REGION is missing or invalid")
    if not isinstance(secret_key_file, str) or not secret_key_file:
        raise PublishError("CACHE_SIGNING_KEY_FILE is required")
    query = f"region={quote(region, safe='')}&secret-key={quote(secret_key_file, safe='')}"
    return f"s3://{bucket}?{query}"


def _run(command, *, capture=True):
    try:
        return subprocess.run(command, check=True, capture_output=capture, text=True)
    except subprocess.CalledProcessError as error:
        # Nix/AWS diagnostics can echo the destination URI, including the secret-key path.
        failure = PublishError(f"{command[0]} command failed (exit {error.returncode})")
        failure.stderr = error.stderr
        raise failure from None
    except OSError as error:
        raise PublishError(f"cannot execute {command[0]}: {error.strerror}") from None


def _run_nix(*args):
    return _run(["nix", *args])


def _json_result(result, label):
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        raise PublishError(f"Nix returned invalid {label} JSON") from None


def discover_packages(system):
    names = _json_result(_run_nix("eval", "--json", f".#packages.{system}",
                                  "--apply", "builtins.attrNames"), "package list")
    if not isinstance(names, list) or any(not isinstance(name, str) or not name for name in names):
        raise PublishError("Nix returned an invalid package-name list")
    if len(names) != len(set(names)):
        raise PublishError("Nix returned duplicate package names")
    return names


def package_version(system, name):
    attribute = f".#packages.{system}.{name}.version"
    result = _run_nix("eval", "--json", attribute)
    version = _json_result(result, f"version for {name}")
    if not isinstance(version, str) or not version.strip():
        raise PublishError(f"package {name} has ambiguous version metadata")
    return version


def build_package(system, name):
    attribute = f".#packages.{system}.{name}"
    result = _run_nix("build", "--no-link", "--print-out-paths", attribute)
    roots = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not roots:
        raise PublishError(f"package {name} build returned no output paths")
    if any(not retention.STORE_PATH.fullmatch(root) for root in roots):
        raise PublishError(f"package {name} build returned an invalid store path")
    if len(roots) != len(set(roots)):
        raise PublishError(f"package {name} build returned duplicate output paths")
    return roots


def _aws(*args):
    try:
        return subprocess.run(["aws", *args], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        raise PublishError(f"AWS {args[0]} command failed (exit {error.returncode})") from None
    except OSError as error:
        raise PublishError(f"cannot execute aws: {error.strerror}") from None


def _parse_narinfo(raw, store_path):
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise PublishError("destination narinfo is not UTF-8") from None
    fields = {}
    signatures = []
    for line in text.splitlines():
        if not line or line.startswith(" ") or ": " not in line:
            raise PublishError("destination narinfo has malformed fields")
        key, value = line.split(": ", 1)
        if key == "Sig":
            signatures.append(value)
        elif key in fields:
            raise PublishError("destination narinfo has duplicate fields")
        else:
            fields[key] = value
    required = {"StorePath", "URL", "NarHash", "References"}
    if not required.issubset(fields) or fields["StorePath"] != store_path or not signatures:
        raise PublishError("destination narinfo is incomplete or unsigned")
    url = fields["URL"]
    if not url.startswith("nar/") or any(part in ("", ".", "..") for part in url.split("/")):
        raise PublishError("destination narinfo has an unsafe NAR URL")
    return url


def _closure_entries(info):
    if isinstance(info, dict):
        entries = []
        for path, item in info.items():
            if not isinstance(path, str) or not isinstance(item, dict):
                raise PublishError("destination returned malformed keyed closure information")
            entry = dict(item)
            if "path" in entry and entry["path"] != path:
                raise PublishError("destination closure key and path field disagree")
            entry["path"] = path
            entries.append(entry)
    elif isinstance(info, list):
        entries = info
    else:
        raise PublishError("destination returned no closure path information")
    if not entries:
        raise PublishError("destination returned no closure path information")
    return entries


def verify_roots(uri, roots):
    """Force fresh S3 metadata reads, validate signatures and verify every NAR object."""
    result = _run_nix("path-info", "--refresh", "--store", uri, "--recursive", "--json", *roots)
    info = _json_result(result, "destination path information")
    paths = {}
    for item in _closure_entries(info):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise PublishError("destination returned malformed closure path information")
        path = item["path"]
        if not retention.STORE_PATH.fullmatch(path) or path in paths:
            raise PublishError("destination returned an invalid or duplicate closure path")
        references = item.get("references")
        if not isinstance(references, list) or any(
            not isinstance(reference, str) or not retention.STORE_PATH.fullmatch(reference)
            for reference in references
        ):
            raise PublishError("destination returned incomplete closure references")
        paths[path] = item
    if any(root not in paths for root in roots):
        raise PublishError("destination closure is missing a requested root")
    if any(reference not in paths for item in paths.values() for reference in item["references"]):
        raise PublishError("destination returned an incomplete recursive closure")

    for store_path in paths:
        name = store_path.rsplit("/", 1)[-1]
        store_hash = name.split("-", 1)[0]
        if not re.fullmatch(r"[0-9a-df-np-sv-z]{32}", store_hash):
            raise PublishError("destination returned a malformed store hash")
        with tempfile.NamedTemporaryFile() as metadata:
            _aws("s3api", "get-object", "--bucket", os.environ["CACHE_BUCKET"],
                 "--key", f"{store_hash}.narinfo", metadata.name)
            metadata.seek(0)
            nar_key = _parse_narinfo(metadata.read(), store_path)
        _aws("s3api", "head-object", "--bucket", os.environ["CACHE_BUCKET"], "--key", nar_key)
        # Nix performs its normal trusted-key signature validation against the destination store.
        _run_nix("store", "verify", "--refresh", "--store", uri, "--sigs-needed", "1", store_path)
    return set(paths)


def vm_roots():
    """Build and select reusable VM inputs, never the completed test result."""
    driver = _run_nix("build", "--no-link", "--print-out-paths",
                      ".#checks.x86_64-linux.any-sync-test.driver").stdout.splitlines()
    valkey = _run_nix("eval", "--raw",
                      ".#checks.x86_64-linux.any-sync-test.nodes.server.services.redis.package.outPath").stdout.strip()
    if len(driver) != 1 or not retention.STORE_PATH.fullmatch(driver[0].strip()):
        raise PublishError("VM driver build returned an invalid or ambiguous root")
    driver = driver[0].strip()
    if not retention.STORE_PATH.fullmatch(valkey):
        raise PublishError("customized Valkey evaluation returned an invalid root")
    return list(dict.fromkeys([driver, valkey]))


def publish_vm_stack():
    """Publish verified reusable roots after workflow has executed the real VM test."""
    if _run_nix("eval", "--impure", "--raw", "--expr", "builtins.currentSystem").stdout.strip() != "x86_64-linux":
        raise PublishError("VM stack publication requires an x86_64-linux runner")
    key_file = os.environ.get("CACHE_SIGNING_KEY_FILE", "")
    uri = destination_uri(os.environ.get("CACHE_BUCKET", ""), os.environ.get("CACHE_REGION", ""), key_file)
    if not Path(key_file).is_file():
        raise PublishError("signing key file is unavailable")
    revision, run_id, attempt = _publication_revision()
    roots = vm_roots()
    # The custom output is always an explicit candidate so membership is exact, not name-based.
    closure = _json_result(_run_nix("path-info", "--recursive", "--json", *roots), "VM root closure")
    paths = set(closure if isinstance(closure, list) else closure.keys() if isinstance(closure, dict) else [])
    if not set(roots).issubset(paths):
        raise PublishError("VM root closure omitted a requested root")
    valkey = _run_nix("eval", "--raw", ".#checks.x86_64-linux.any-sync-test.nodes.server.services.redis.package.outPath").stdout.strip()
    if valkey not in paths:
        raise PublishError("customized Valkey is not in the published VM root closure")
    with retention.locked() as lock:
        state = retention.read_state()
        try:
            _run_nix("copy", "--to", uri, *roots)
            verified_paths = verify_roots(uri, roots)
            retention.supersede_retirements(state, verified_paths)
            retention.record_vm_stack(state, roots, revision, run_id, attempt, verified=True)
            retention.write_state(state, lock)
        except (PublishError, subprocess.CalledProcessError, retention.CacheError) as error:
            print(f"VM stack publication failed: {error}", file=sys.stderr)
            return 1
    return 0


def _publication_revision():
    revision = os.environ.get("GITHUB_SHA")
    run_id = os.environ.get("GITHUB_RUN_ID")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT")
    if not revision or not run_id or not attempt or not attempt.isdigit():
        raise PublishError("GitHub revision and run identity are required")
    return revision, run_id, int(attempt)


def publish_system(system):
    if system not in SYSTEMS:
        raise PublishError(f"unsupported publishing system: {system}")
    current = _run_nix("eval", "--impure", "--raw", "--expr", "builtins.currentSystem").stdout.strip()
    if current != system:
        raise PublishError(f"native runner reports {current!r}, expected {system!r}")
    bucket = os.environ.get("CACHE_BUCKET", "")
    region = os.environ.get("CACHE_REGION", "")
    key_file = os.environ.get("CACHE_SIGNING_KEY_FILE", "")
    uri = destination_uri(bucket, region, key_file)
    if not Path(key_file).is_file():
        raise PublishError("signing key file is unavailable")
    revision, run_id, attempt = _publication_revision()

    # Build before acquiring the shared lock; no remote writes happen until all builds finish.
    prepared = []
    for name in discover_packages(system):
        version = package_version(system, name)
        prepared.append((name, version, build_package(system, name)))

    with retention.locked() as lock:
        state = retention.read_state()
        for name, version, roots in prepared:
            try:
                _run_nix("copy", "--to", uri, *roots)
                verified_paths = verify_roots(uri, roots)
                retention.supersede_retirements(state, verified_paths)
                # The state primitive replaces this version's roots/id in place. Distinct
                # versions remain distinct retention entries even if Nix deduplicates their paths.
                retention.record_package(state, system, name, version, roots, revision,
                                         run_id, attempt, verified=True)
                retention.write_state(state, lock)
            except (PublishError, subprocess.CalledProcessError, retention.CacheError) as error:
                print(f"Publication failed for {system}/{name}: {error}", file=sys.stderr)
                return 1
    return 0


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv == ["vm-stack"]:
        try:
            return publish_vm_stack()
        except (PublishError, subprocess.CalledProcessError, retention.CacheError) as error:
            print(f"cache-publish: {error}", file=sys.stderr)
            return 1
    if len(argv) != 1:
        print("usage: cache-publish.py SYSTEM|vm-stack", file=sys.stderr)
        return 2
    try:
        return publish_system(argv[0])
    except (PublishError, subprocess.CalledProcessError, retention.CacheError) as error:
        print(f"cache-publish: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
