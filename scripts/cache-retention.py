#!/usr/bin/env python3
"""S3 coordination and publication-manifest primitives for the Nix cache."""

import argparse
import contextlib
from datetime import datetime, timedelta, timezone
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from dataclasses import dataclass

STATE_KEY = "control/state.json"
LOCK_KEY = "control/lock.json"
STORE_PATH = re.compile(r"^/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+$")
STORE_HASH = re.compile(r"^[0-9a-df-np-sv-z]{32}\.narinfo$")
STORE_NAME = re.compile(r"^([0-9a-df-np-sv-z]{32})-([A-Za-z0-9+._?=-]+)$")
RETENTION = timedelta(days=7)


class CacheError(RuntimeError):
    """The cache control state or requested operation is unsafe."""


def aws(*args, input=None):
    """Run AWS CLI without a shell; credentials remain in the environment."""
    command = ["aws", *args]
    if input is None:
        return subprocess.run(command, check=True, capture_output=True, text=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as body:
        body.write(input)
        body.flush()
        command = [body.name if arg == "-" else arg for arg in command]
        return subprocess.run(command, check=True, capture_output=True, text=True)


def bucket():
    value = os.environ.get("CACHE_BUCKET")
    if not value:
        raise CacheError("CACHE_BUCKET must name the configured bucket")
    return value


def state_uri(key):
    return f"s3://{bucket()}/{key}"


def decode_json(raw, label):
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
        raise CacheError(f"{label} is not valid JSON") from error


def validate_state(state):
    if not isinstance(state, dict) or set(state) != {
        "schema", "packages", "vm_stacks", "retirements", "nar_deadlines"
    } or state["schema"] != 1 or isinstance(state["schema"], bool):
        raise CacheError("unsupported or invalid state schema")
    packages = state["packages"]
    if not isinstance(packages, dict):
        raise CacheError("packages must be an object")
    for platform, entries in packages.items():
        if not isinstance(platform, str) or not isinstance(entries, dict):
            raise CacheError("invalid platform package map")
        for name, versions in entries.items():
            if not isinstance(name, str) or not name or not isinstance(versions, list) or len(versions) > 2:
                raise CacheError("invalid package version list")
            seen = set()
            for version in versions:
                _validate_publication(version, package=True)
                if version["version"] in seen:
                    raise CacheError("duplicate package version")
                seen.add(version["version"])
    if not isinstance(state["vm_stacks"], list) or len(state["vm_stacks"]) > 2:
        raise CacheError("invalid VM stack list")
    for stack in state["vm_stacks"]:
        _validate_publication(stack, package=False)
    retirements, deadlines = state["retirements"], state["nar_deadlines"]
    if not isinstance(retirements, dict) or not isinstance(deadlines, dict):
        raise CacheError("invalid retirement control maps")
    for key, retirement in retirements.items():
        if not isinstance(key, str) or not STORE_HASH.fullmatch(key) or not isinstance(retirement, dict):
            raise CacheError("invalid retirement record")
        if set(retirement) != {"nar", "withdrawn_at", "metadata"}:
            raise CacheError("invalid retirement record fields")
        if not _valid_nar_key(retirement["nar"]) or not isinstance(retirement["metadata"], str) or not retirement["metadata"]:
            raise CacheError("invalid retirement mapping or metadata")
        try:
            original = _parse_narinfo(retirement["metadata"].encode("utf-8"), key)
        except (UnicodeEncodeError, CacheError) as error:
            raise CacheError(f"invalid original metadata for retirement {key}") from error
        if original["nar"] != retirement["nar"]:
            raise CacheError(f"retirement NAR mapping does not match original metadata for {key}")
        if retirement["withdrawn_at"] is not None and not _valid_timestamp(retirement["withdrawn_at"]):
            raise CacheError("invalid retirement timestamp")
    for key, deadline in deadlines.items():
        if not _valid_nar_key(key) or not _valid_timestamp(deadline):
            raise CacheError("invalid NAR deadline")
    return state


def _valid_nar_key(value):
    return (isinstance(value, str) and value.startswith("nar/") and len(value) > 4
            and all(part not in ("", ".", "..") for part in value.split("/")))


def _valid_timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0
    except (ValueError, OverflowError):
        return False


def _validate_publication(entry, package):
    if not isinstance(entry, dict):
        raise CacheError("publication must be an object")
    required = {"revision", "run_id", "run_attempt", "roots"}
    if package:
        required.add("version")
        if not isinstance(entry.get("version"), str) or not entry["version"]:
            raise CacheError("invalid package version")
    if set(entry) != required:
        raise CacheError("invalid publication fields")
    if not all(isinstance(entry[k], str) and entry[k] for k in ("revision", "run_id")):
        raise CacheError("invalid publication identity")
    if not isinstance(entry["run_attempt"], int) or isinstance(entry["run_attempt"], bool) or entry["run_attempt"] < 1:
        raise CacheError("invalid run attempt")
    roots = entry["roots"]
    if not isinstance(roots, list) or not roots or any(not isinstance(p, str) or not STORE_PATH.fullmatch(p) for p in roots):
        raise CacheError("invalid store path")
    if len(roots) != len(set(roots)):
        raise CacheError("duplicate store path")


def empty_state():
    return {"schema": 1, "packages": {}, "vm_stacks": [], "retirements": {}, "nar_deadlines": {}}


def read_state():
    with tempfile.NamedTemporaryFile() as destination:
        aws("s3api", "get-object", "--bucket", bucket(), "--key", STATE_KEY, destination.name)
        destination.seek(0)
        return validate_state(decode_json(destination.read(), "state"))


@dataclass(frozen=True)
class Lock:
    token: str
    etag: str


def acquire_lock(run_id=None, run_attempt=None):
    token = secrets.token_hex(32)
    body = json.dumps({"token": token, "run_id": run_id or os.environ.get("GITHUB_RUN_ID", "local"),
                       "run_attempt": int(run_attempt or os.environ.get("GITHUB_RUN_ATTEMPT", "1"))})
    result = aws("s3api", "put-object", "--bucket", bucket(), "--key", LOCK_KEY,
                 "--body", "-", "--if-none-match", "*", input=body)
    try:
        response = decode_json(result.stdout, "lock response")
        etag = response["ETag"]
    except (KeyError, TypeError) as error:
        raise CacheError("AWS did not return a lock ETag") from error
    if not isinstance(etag, str) or not re.fullmatch(r'"[0-9a-fA-F]{32}"', etag):
        raise CacheError("AWS returned an invalid lock ETag")
    return Lock(token, etag)


def release_lock(lock):
    aws("s3api", "delete-object", "--bucket", bucket(), "--key", LOCK_KEY, "--if-match", lock.etag)


@contextlib.contextmanager
def locked():
    lock = acquire_lock()
    try:
        yield lock
    finally:
        # Conditional release cannot remove a replacement owner's lock.
        release_lock(lock)


def _assert_lock_held(lock):
    if not isinstance(lock, Lock) or not lock.token or not lock.etag:
        raise CacheError("operation requires the acquired lock")
    with tempfile.NamedTemporaryFile() as current_lock:
        aws("s3api", "get-object", "--bucket", bucket(), "--key", LOCK_KEY, current_lock.name)
        current_lock.seek(0)
        record = decode_json(current_lock.read(), "lock")
    head = decode_json(aws("s3api", "head-object", "--bucket", bucket(), "--key", LOCK_KEY).stdout, "lock headers")
    if record.get("token") != lock.token or head.get("ETag") != lock.etag:
        raise CacheError("lock is no longer held by this owner")


def write_state(state, lock):
    _assert_lock_held(lock)
    validate_state(state)
    aws("s3api", "put-object", "--bucket", bucket(), "--key", STATE_KEY,
        "--body", "-", input=json.dumps(state, sort_keys=True, separators=(",", ":")))


def _metadata_keys():
    # Paginate and only use this for the explicit one-time empty-bucket check.
    token = None
    keys = []
    while True:
        args = ["s3api", "list-objects-v2", "--bucket", bucket()]
        if token:
            args += ["--continuation-token", token]
        response = decode_json(aws(*args).stdout, "S3 listing")
        keys.extend(obj["Key"] for obj in response.get("Contents", []))
        if not response.get("IsTruncated"):
            return keys
        token = response.get("NextContinuationToken")
        if not token:
            raise CacheError("truncated S3 listing has no continuation token")


def initialize_empty(enabled):
    if not enabled:
        raise CacheError("initialization requires --initialize-empty")
    with locked() as lock:
        _assert_lock_held(lock)
        keys = _metadata_keys()
        if any(key != LOCK_KEY for key in keys):
            raise CacheError("refusing initialization: bucket is not empty")
        write_state(empty_state(), lock)


def supersede_retirements(state, store_paths):
    """Forget retirement records only for paths freshly copied and verified as available."""
    hashes = set()
    for store_path in store_paths:
        if not isinstance(store_path, str) or not STORE_PATH.fullmatch(store_path):
            raise CacheError("verified closure contains an invalid store path")
        match = STORE_NAME.fullmatch(store_path.rsplit("/", 1)[-1])
        hashes.add(match.group(1) + ".narinfo")
    for key in hashes:
        state["retirements"].pop(key, None)
    # Deliberately retain nar_deadlines: old NARs may still be referenced by readers.
    return state


def record_package(state, platform, name, version, roots, revision, run_id, run_attempt, verified):
    if not verified:
        raise CacheError("publication verification failed")
    candidate = {"version": version, "roots": roots, "revision": revision,
                 "run_id": str(run_id), "run_attempt": int(run_attempt)}
    _validate_publication(candidate, package=True)
    versions = state["packages"].setdefault(platform, {}).setdefault(name, [])
    # An idempotent retry updates run identity but never changes retained ordering.
    for index, old in enumerate(versions):
        if old["version"] == version and old["revision"] == revision and old["roots"] == roots:
            versions[index] = candidate
            return state
    versions = [old for old in versions if old["version"] != version]
    state["packages"][platform][name] = ([candidate] + versions)[:2]
    return state


def record_vm_stack(state, roots, revision, run_id, run_attempt, verified):
    if not verified:
        raise CacheError("publication verification failed")
    candidate = {"roots": roots, "revision": revision, "run_id": str(run_id), "run_attempt": int(run_attempt)}
    _validate_publication(candidate, package=False)
    stacks = state["vm_stacks"]
    for index, old in enumerate(stacks):
        if old["revision"] == revision and old["roots"] == roots:
            stacks[index] = candidate
            return state
    state["vm_stacks"] = [candidate] + stacks
    state["vm_stacks"] = state["vm_stacks"][:2]
    return state


def _now_utc():
    return datetime.now(timezone.utc)


def _timestamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_narinfo(raw, key):
    """Parse signed Nix metadata strictly and derive safe graph edges."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CacheError(f"{key} is not UTF-8") from error
    fields, signatures = {}, []
    for line in text.splitlines():
        if not line or line.startswith((" ", "\\t")) or ": " not in line or "\\r" in line:
            raise CacheError(f"{key} contains a malformed field")
        name, value = line.split(": ", 1)
        if not name or (not value and name != "References"):
            raise CacheError(f"{key} contains an empty field")
        if name == "Sig":
            signatures.append(value)
        elif name not in {"StorePath", "URL", "Compression", "FileHash", "FileSize", "NarHash", "NarSize", "References", "Deriver", "System", "CA"}:
            raise CacheError(f"{key} contains unsupported field {name}")
        elif name in fields:
            raise CacheError(f"{key} contains duplicate {name}")
        else:
            fields[name] = value
    required = {"StorePath", "URL", "Compression", "FileHash", "FileSize", "NarHash", "NarSize", "References"}
    if not required.issubset(fields) or not signatures:
        raise CacheError(f"{key} is incomplete or unsigned")
    match = STORE_HASH.fullmatch(key)
    store = STORE_NAME.fullmatch(fields["StorePath"].rsplit("/", 1)[-1])
    if not match or not store or fields["StorePath"] != "/nix/store/" + fields["StorePath"].rsplit("/", 1)[-1] or store.group(1) != key[:-len(".narinfo")]:
        raise CacheError(f"{key} StorePath does not match its key")
    url = fields["URL"]
    compression = fields["Compression"]
    suffixes = {"xz": ".nar.xz", "zstd": ".nar.zst", "bzip2": ".nar.bz2",
                "gzip": ".nar.gz", "none": ".nar"}
    if (compression not in suffixes or not _valid_nar_key(url)
            or not re.fullmatch(r"nar/[A-Za-z0-9_-]+" + re.escape(suffixes[compression]), url)):
        raise CacheError(f"{key} has unsupported compression or unsafe NAR URL")
    if not re.fullmatch(r"[A-Za-z0-9]+[:-][A-Za-z0-9+/_=-]+", fields["FileHash"]) or not re.fullmatch(r"[A-Za-z0-9]+[:-][A-Za-z0-9+/_=-]+", fields["NarHash"]):
        raise CacheError(f"{key} has malformed NAR hash")
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]+:[A-Za-z0-9+/_=-]+", signature) for signature in signatures):
        raise CacheError(f"{key} has malformed signature")
    for field in ("FileSize", "NarSize"):
        if not fields[field].isdigit():
            raise CacheError(f"{key} has malformed {field}")
    references = []
    for ref in fields["References"].split():
        item = STORE_NAME.fullmatch(ref)
        if not item:
            raise CacheError(f"{key} has malformed reference")
        references.append(item.group(1) + ".narinfo")
    if len(references) != len(set(references)):
        raise CacheError(f"{key} has duplicate references")
    return {"store_path": fields["StorePath"], "nar": url, "references": references, "text": text}


def _list_objects():
    token, objects = None, {}
    while True:
        args = ["s3api", "list-objects-v2", "--bucket", bucket()]
        if token:
            args += ["--continuation-token", token]
        response = decode_json(aws(*args).stdout, "S3 listing")
        contents = response.get("Contents", [])
        if not isinstance(contents, list):
            raise CacheError("malformed S3 listing")
        for item in contents:
            key = item.get("Key") if isinstance(item, dict) else None
            if not isinstance(key, str) or key in objects:
                raise CacheError("malformed or duplicate S3 object key")
            objects[key] = item
        if not response.get("IsTruncated"):
            return objects
        token = response.get("NextContinuationToken")
        if not isinstance(token, str) or not token:
            raise CacheError("truncated S3 listing has no continuation token")


def _get_object(key):
    with tempfile.NamedTemporaryFile() as destination:
        aws("s3api", "get-object", "--bucket", bucket(), "--key", key, destination.name)
        destination.seek(0)
        return destination.read()


def _retained_roots(state):
    roots = []
    for platforms in state["packages"].values():
        for versions in platforms.values():
            for entry in versions:
                roots.extend(entry["roots"])
    for entry in state["vm_stacks"]:
        roots.extend(entry["roots"])
    return roots


def _metadata_graph(state=None):
    objects = _list_objects()
    records = {}
    for key in objects:
        if STORE_HASH.fullmatch(key):
            records[key] = _parse_narinfo(_get_object(key), key)
    # A persisted retirement record can explain a missing dependency after an
    # interrupted withdrawal. Marking still rejects it if any retained root needs it.
    retired = set(state["retirements"]) if state is not None else set()
    for key, record in records.items():
        for reference in record["references"]:
            if reference not in records and reference not in retired:
                raise CacheError(f"{key} references missing metadata {reference}")
    advertised = {}
    for key, record in records.items():
        advertised.setdefault(record["nar"], set()).add(key)
    return objects, records, advertised


def _marked_metadata(state, records):
    marked, pending = set(), []
    for root in _retained_roots(state):
        match = STORE_NAME.fullmatch(root.rsplit("/", 1)[-1])
        if not match:
            raise CacheError("invalid retained root")
        pending.append(match.group(1) + ".narinfo")
    while pending:
        key = pending.pop()
        if key in marked:
            continue
        record = records.get(key)
        if record is None:
            raise CacheError(f"retained root/reference metadata missing: {key}")
        marked.add(key)
        pending.extend(record["references"])
    return marked


def prune(dry_run=True, clock=None):
    """Plan or execute one lock-protected mark/retire/sweep pass."""
    clock = clock or _now_utc
    report = {"dry_run": dry_run, "withdraw": [], "delete": [], "blocked": []}
    with locked() as lock:
        state = read_state()
        objects, records, advertised = _metadata_graph(state)
        marked = _marked_metadata(state, records)
        if dry_run:
            report["withdraw"] = sorted(set(records) - marked)
            now = clock()
            for nar, deadline in sorted(state["nar_deadlines"].items()):
                unresolved = any(item["nar"] == nar and item["withdrawn_at"] is None
                                 for item in state["retirements"].values())
                eligible = datetime.fromisoformat(deadline.replace("Z", "+00:00")) <= now
                if eligible and not unresolved and not advertised.get(nar) and nar in objects:
                    report["delete"].append(nar)
        else:
            for key in sorted(set(records) - marked):
                record = records[key]
                state["retirements"][key] = {"nar": record["nar"], "withdrawn_at": None,
                                               "metadata": record["text"]}
                write_state(state, lock)
                aws("s3api", "delete-object", "--bucket", bucket(), "--key", key)
                withdrawn = _timestamp(clock())
                state["retirements"][key]["withdrawn_at"] = withdrawn
                deadline = _timestamp(clock() + RETENTION)
                old_deadline = state["nar_deadlines"].get(record["nar"])
                state["nar_deadlines"][record["nar"]] = max(old_deadline, deadline) if old_deadline else deadline
                write_state(state, lock)
                report["withdraw"].append(key)
                advertised.get(record["nar"], set()).discard(key)
            # Recompute reachability before recovery; never delete a newly marked key.
            marked = _marked_metadata(state, records)
            for key, retirement in list(state["retirements"].items()):
                if key in marked:
                    state["retirements"].pop(key)
                    write_state(state, lock)
                    continue
                if retirement["withdrawn_at"] is None:
                    withdrawn_now = key in records
                    if withdrawn_now:
                        aws("s3api", "delete-object", "--bucket", bucket(), "--key", key)
                    retirement["withdrawn_at"] = _timestamp(clock())
                    deadline = _timestamp(clock() + RETENTION)
                    old = state["nar_deadlines"].get(retirement["nar"])
                    state["nar_deadlines"][retirement["nar"]] = max(old, deadline) if old else deadline
                    write_state(state, lock)
                    if withdrawn_now:
                        report["withdraw"].append(key)
            objects, records, advertised = _metadata_graph(state)
            _marked_metadata(state, records)
            now = clock()
            candidates = set(state["nar_deadlines"])
            candidates.update(item["nar"] for item in state["retirements"].values())
            for nar in sorted(candidates):
                if advertised.get(nar) or any(item["nar"] == nar and item["withdrawn_at"] is None for item in state["retirements"].values()):
                    continue
                deadline = state["nar_deadlines"].get(nar)
                if deadline is None or now < datetime.fromisoformat(deadline.replace("Z", "+00:00")) or nar not in objects:
                    continue
                aws("s3api", "delete-object", "--bucket", bucket(), "--key", nar)
                state["nar_deadlines"].pop(nar, None)
                for key in [k for k, item in state["retirements"].items() if item["nar"] == nar]:
                    state["retirements"].pop(key)
                write_state(state, lock)
                report["delete"].append(nar)
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("lock")
    sub.add_parser("unlock").add_argument("--etag", required=True)
    prune_cmd = sub.add_parser("prune", help="dry-run unless --execute is explicitly supplied")
    prune_cmd.add_argument("--execute", action="store_true")
    init = sub.add_parser("initialize")
    init.add_argument("--initialize-empty", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "lock":
            lock = acquire_lock()
            print(json.dumps({"token": lock.token, "etag": lock.etag}))
        elif args.command == "unlock":
            release_lock(Lock("", args.etag))
        elif args.command == "prune":
            print(json.dumps(prune(dry_run=not args.execute), sort_keys=True))
        else:
            initialize_empty(args.initialize_empty)
    except (CacheError, subprocess.CalledProcessError) as error:
        print(f"cache-retention: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
