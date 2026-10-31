import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cache_retention", ROOT / "scripts/cache-retention.py")
cache = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cache)

VALID = "/nix/store/0123456789abcdfghijklmnpqrsvwxyz-package-1"


class CacheRetentionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bucket = Path(self.temp.name) / "bucket"
        self.bucket.mkdir()
        cli = Path(self.temp.name) / "aws"
        cli.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ["FAKE_BUCKET"])
a = sys.argv[1:]
def path(key): return root / key
def fail(): print("PreconditionFailed", file=sys.stderr); sys.exit(255)
if a[:2] == ["s3api", "put-object"]:
    key = a[a.index("--key") + 1]; body = pathlib.Path(a[a.index("--body") + 1]).read_bytes()
    if "--if-none-match" in a and path(key).exists(): fail()
    path(key).parent.mkdir(parents=True, exist_ok=True); path(key).write_bytes(body)
    print(json.dumps({"ETag": "\\\"" + "a" * 32 + "\\\""}))
elif a[:2] == ["s3api", "delete-object"]:
    key = a[a.index("--key") + 1]
    if not path(key).exists(): fail()
    if "--if-match" in a and a[a.index("--if-match") + 1] != '\\"' + "a" * 32 + '\\"': fail()
    path(key).unlink()
elif a[:2] == ["s3api", "get-object"]:
    key = a[a.index("--key") + 1]; pathlib.Path(a[-1]).write_bytes(path(key).read_bytes())
    print(json.dumps({"Key": key, "ETag": '\\"' + "a" * 32 + '\\"'}))
elif a[:2] == ["s3api", "list-objects-v2"]:
    contents = sorted([{"Key": str(p.relative_to(root))} for p in root.rglob("*") if p.is_file()], key=lambda x: x["Key"])
    start = int(a[a.index("--continuation-token") + 1]) if "--continuation-token" in a else 0
    page = contents[start:start + 2]
    truncated = start + 2 < len(contents)
    print(json.dumps({"Contents": page, "IsTruncated": truncated, "NextContinuationToken": str(start + 2) if truncated else None}))
else: sys.exit(2)
''')
        cli.chmod(0o755)
        self.env = os.environ | {"PATH": str(Path(self.temp.name)) + os.pathsep + os.environ["PATH"],
                                 "FAKE_BUCKET": str(self.bucket), "CACHE_BUCKET": "test-bucket"}
        self.patch = mock.patch.dict(os.environ, self.env)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_lock_is_conditional_and_wrong_etag_does_not_release(self):
        lock = cache.acquire_lock("first", 1)
        self.assertTrue((self.bucket / cache.LOCK_KEY).exists())
        with self.assertRaises(subprocess.CalledProcessError):
            cache.acquire_lock("second", 1)
        self.assertIn(lock.token, (self.bucket / cache.LOCK_KEY).read_text())
        with self.assertRaises(subprocess.CalledProcessError):
            cache.release_lock(cache.Lock("wrong", '"' + "b" * 32 + '"'))
        self.assertTrue((self.bucket / cache.LOCK_KEY).exists())
        cache.release_lock(lock)
        self.assertFalse((self.bucket / cache.LOCK_KEY).exists())

    def test_state_put_requires_current_lock_owner(self):
        lock = cache.acquire_lock("writer", 1)
        state = cache.empty_state()
        cache.write_state(state, lock)
        self.assertEqual(cache.read_state(), state)
        with self.assertRaises(cache.CacheError):
            cache.write_state(state, cache.Lock("not-owner", lock.etag))

    def test_missing_malformed_and_unsupported_state_fail_closed(self):
        with self.assertRaises(subprocess.CalledProcessError):
            cache.read_state()
        target = self.bucket / cache.STATE_KEY
        target.parent.mkdir()
        for raw in (b"{", json.dumps(cache.empty_state() | {"schema": 2}).encode()):
            target.write_bytes(raw)
            with self.assertRaises(cache.CacheError):
                cache.read_state()

    def test_duplicate_versions_and_invalid_store_paths_fail_closed(self):
        state = cache.empty_state()
        pub = {"version": "1", "roots": [VALID], "revision": "a", "run_id": "1", "run_attempt": 1}
        state["packages"] = {"x86_64-linux": {"demo": [pub, pub.copy()]}}
        with self.assertRaisesRegex(cache.CacheError, "duplicate"):
            cache.validate_state(state)
        state["packages"]["x86_64-linux"]["demo"] = [pub | {"roots": ["/tmp/no"]}]
        with self.assertRaisesRegex(cache.CacheError, "store path"):
            cache.validate_state(state)

    def test_publication_retains_distinct_versions_and_rebuilds_idempotently(self):
        state = cache.empty_state()
        for version, rev, root in [("1", "a", VALID), ("2", "b", VALID.replace("package-1", "package-2")),
                                   ("3", "c", VALID.replace("package-1", "package-3a")),
                                   ("3", "d", VALID.replace("package-1", "package-3b"))]:
            cache.record_package(state, "x86_64-linux", "demo", version, [root], rev, "run-" + rev, 1, True)
        entries = state["packages"]["x86_64-linux"]["demo"]
        self.assertEqual([entry["version"] for entry in entries], ["3", "2"])
        self.assertEqual(entries[0]["roots"], [VALID.replace("package-1", "package-3b")])
        self.assertEqual(entries[0]["run_id"], "run-d")
        cache.record_package(state, "aarch64-linux", "demo", "1", [VALID], "e", "run-e", 1, True)
        self.assertIn("aarch64-linux", state["packages"])
        before = json.dumps(state, sort_keys=True)
        with self.assertRaises(cache.CacheError):
            cache.record_package(state, "x86_64-linux", "demo", "4", [VALID], "f", "run-f", 1, False)
        self.assertEqual(json.dumps(state, sort_keys=True), before)

    def test_vm_stack_retry_keeps_prior_revision(self):
        state = cache.empty_state()
        cache.record_vm_stack(state, [VALID], "rev1", "run1", 1, True)
        cache.record_vm_stack(state, [VALID.replace("package-1", "vm-driver")], "rev2", "run2", 1, True)
        prior = state["vm_stacks"][1].copy()
        cache.record_vm_stack(state, [VALID.replace("package-1", "vm-driver")], "rev2", "retry", 2, True)
        self.assertEqual(state["vm_stacks"][1], prior)
        self.assertEqual(state["vm_stacks"][0]["run_id"], "retry")

    def test_initialization_requires_flag_and_empty_bucket(self):
        with self.assertRaises(cache.CacheError):
            cache.initialize_empty(False)
        (self.bucket / "nix-cache-info").write_text("StoreDir: /nix/store")
        with self.assertRaisesRegex(cache.CacheError, "not empty"):
            cache.initialize_empty(True)
        self.assertFalse((self.bucket / cache.STATE_KEY).exists())

    def test_initialization_accepts_only_its_owned_lock_as_existing_object(self):
        cache.initialize_empty(True)
        self.assertEqual(cache.read_state(), cache.empty_state())
        self.assertFalse((self.bucket / cache.LOCK_KEY).exists())

    def test_old_package_retry_does_not_displace_newest_or_evict_roots(self):
        state = cache.empty_state()
        for version, revision, root in (("1", "r1", "package-1"), ("2", "r2", "package-2")):
            cache.record_package(state, "x86_64-linux", "demo", version, [VALID.replace("package-1", root)], revision, revision, 1, True)
        cache.record_package(state, "x86_64-linux", "demo", "1", [VALID], "r1", "retry", 2, True)
        cache.record_package(state, "x86_64-linux", "demo", "3", [VALID.replace("package-1", "package-3")], "r3", "r3", 1, True)
        versions = state["packages"]["x86_64-linux"]["demo"]
        self.assertEqual([entry["version"] for entry in versions], ["3", "2"])

    def test_old_vm_retry_does_not_displace_newest_or_evict_stack(self):
        state = cache.empty_state()
        cache.record_vm_stack(state, [VALID], "r1", "r1", 1, True)
        cache.record_vm_stack(state, [VALID.replace("package-1", "vm-2")], "r2", "r2", 1, True)
        cache.record_vm_stack(state, [VALID], "r1", "retry", 2, True)
        cache.record_vm_stack(state, [VALID.replace("package-1", "vm-3")], "r3", "r3", 1, True)
        self.assertEqual([entry["revision"] for entry in state["vm_stacks"]], ["r3", "r2"])

    def _narinfo(self, store_hash, name, url, references=""):
        return (f"StorePath: /nix/store/{store_hash}-{name}\nURL: {url}\nCompression: xz\n"
                "FileHash: sha256-abc=\nFileSize: 10\nNarHash: sha256-def=\nNarSize: 20\n"
                f"References: {references}\nSig: cache-1:signature\n").encode()

    def _put(self, key, data):
        path = self.bucket / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def _retention_fixture(self):
        hashes = ["0" * 32, "1" * 32, "2" * 32, "3" * 32, "4" * 32]
        roots = [f"/nix/store/{h}-root-v{i}" for i, h in enumerate(hashes[:3], 1)]
        # v3 and v2 share a NAR; v1 is obsolete. Two independent metadata records share it.
        self._put(hashes[0] + ".narinfo", self._narinfo(hashes[0], "root-v1", "nar/obsolete.nar.xz"))
        self._put(hashes[1] + ".narinfo", self._narinfo(hashes[1], "root-v2", "nar/shared.nar.xz"))
        self._put(hashes[2] + ".narinfo", self._narinfo(hashes[2], "root-v3", "nar/shared.nar.xz"))
        for key in ("nar/obsolete.nar.xz", "nar/shared.nar.xz"):
            self._put(key, b"nar bytes")
        state = cache.empty_state()
        state["packages"] = {"x86_64-linux": {"demo": [
            {"version": "3", "roots": [roots[2]], "revision": "r3", "run_id": "3", "run_attempt": 1},
            {"version": "2", "roots": [roots[1]], "revision": "r2", "run_id": "2", "run_attempt": 1}]}}
        self._put(cache.STATE_KEY, json.dumps(state).encode())
        return hashes, roots

    def test_shared_nar_traversal_protects_retained_roots_and_dry_run_is_read_only(self):
        self._retention_fixture()
        report = cache.prune(dry_run=True)
        self.assertEqual(report["withdraw"], ["0" * 32 + ".narinfo"])
        self.assertTrue((self.bucket / ("1" * 32 + ".narinfo")).exists())
        self.assertTrue((self.bucket / "nar/shared.nar.xz").exists())
        state = json.loads((self.bucket / "control/state.json").read_text())
        self.assertEqual(state["retirements"], {})
        self.assertEqual(state["nar_deadlines"], {})

    def test_pending_child_withdrawal_recovers_missing_metadata_needed_by_unretained_parent(self):
        hashes, _ = self._retention_fixture()
        child_hash = "4" * 32
        parent = self._narinfo(hashes[0], "root-v1", "nar/obsolete.nar.xz", f"{child_hash}-dependency")
        child = self._narinfo(child_hash, "dependency", "nar/child.nar.xz")
        self._put(hashes[0] + ".narinfo", parent)
        self._put(child_hash + ".narinfo", child)
        self._put("nar/child.nar.xz", b"child")
        state = json.loads((self.bucket / cache.STATE_KEY).read_text())
        state["retirements"][child_hash + ".narinfo"] = {
            "nar": "nar/child.nar.xz", "withdrawn_at": None, "metadata": child.decode()}
        (self.bucket / cache.STATE_KEY).write_text(json.dumps(state))
        (self.bucket / (child_hash + ".narinfo")).unlink()  # crash after delete, before confirmation write
        when = cache.datetime(2026, 10, 30, 12, tzinfo=cache.timezone.utc)
        cache.prune(dry_run=False, clock=lambda: when)
        after = json.loads((self.bucket / cache.STATE_KEY).read_text())
        self.assertFalse((self.bucket / (hashes[0] + ".narinfo")).exists())
        self.assertEqual(after["retirements"][child_hash + ".narinfo"]["withdrawn_at"], "2026-10-30T12:00:00Z")
        self.assertTrue((self.bucket / "nar/child.nar.xz").exists())

    def test_missing_unexplained_reference_fails_closed(self):
        hashes, _ = self._retention_fixture()
        self._put(hashes[0] + ".narinfo", self._narinfo(hashes[0], "root-v1", "nar/obsolete.nar.xz", f"{'4' * 32}-dependency"))
        with self.assertRaisesRegex(cache.CacheError, "missing metadata"):
            cache.prune(dry_run=False)
        self.assertTrue((self.bucket / (hashes[0] + ".narinfo")).exists())

    def test_pending_retirement_for_newly_marked_metadata_is_never_withdrawn(self):
        hashes, _ = self._retention_fixture()
        key = hashes[0] + ".narinfo"
        state = json.loads((self.bucket / cache.STATE_KEY).read_text())
        state["packages"]["x86_64-linux"]["demo"][1] = {
            "version": "1", "roots": [f"/nix/store/{hashes[0]}-root-v1"],
            "revision": "r1", "run_id": "1", "run_attempt": 1}
        state["retirements"][key] = {"nar": "nar/obsolete.nar.xz", "withdrawn_at": None,
                                     "metadata": self._narinfo(hashes[0], "root-v1", "nar/obsolete.nar.xz").decode()}
        state["nar_deadlines"]["nar/obsolete.nar.xz"] = "2026-11-10T12:00:00Z"
        (self.bucket / cache.STATE_KEY).write_text(json.dumps(state))
        self._put(key, self._narinfo(hashes[0], "root-v1", "nar/new.nar.xz"))
        self._put("nar/new.nar.xz", b"republished NAR")
        cache.prune(dry_run=False, clock=lambda: cache.datetime(2026, 10, 30, 12, tzinfo=cache.timezone.utc))
        self.assertTrue((self.bucket / key).exists())
        self.assertTrue((self.bucket / "nar/new.nar.xz").exists())
        after = json.loads((self.bucket / cache.STATE_KEY).read_text())
        self.assertNotIn(key, after["retirements"])
        self.assertEqual(after["nar_deadlines"]["nar/obsolete.nar.xz"], "2026-11-10T12:00:00Z")

    def test_missing_retained_metadata_fails_before_changes(self):
        hashes, _ = self._retention_fixture()
        (self.bucket / (hashes[2] + ".narinfo")).unlink()
        with self.assertRaisesRegex(cache.CacheError, "missing"):
            cache.prune(dry_run=False)
        self.assertTrue((self.bucket / "nar/obsolete.nar.xz").exists())

    def test_executed_prune_reports_successful_metadata_and_eligible_nar_deletions(self):
        hashes, _ = self._retention_fixture()
        when = cache.datetime(2026, 10, 30, 12, tzinfo=cache.timezone.utc)

        withdrawal_report = cache.prune(dry_run=False, clock=lambda: when)
        self.assertEqual(withdrawal_report["withdraw"], [hashes[0] + ".narinfo"])
        self.assertEqual(withdrawal_report["delete"], [])
        state = json.loads((self.bucket / cache.STATE_KEY).read_text())
        state["nar_deadlines"]["nar/obsolete.nar.xz"] = "2026-10-30T12:00:00Z"
        (self.bucket / cache.STATE_KEY).write_text(json.dumps(state))
        deletion_report = cache.prune(dry_run=False, clock=lambda: when)

        self.assertEqual(deletion_report["withdraw"], [])
        self.assertEqual(deletion_report["delete"], ["nar/obsolete.nar.xz"])
        self.assertFalse((self.bucket / (hashes[0] + ".narinfo")).exists())
        self.assertFalse((self.bucket / "nar/obsolete.nar.xz").exists())
        after = cache.read_state()
        self.assertNotIn("nar/obsolete.nar.xz", after["nar_deadlines"])
        self.assertNotIn(hashes[0] + ".narinfo", after["retirements"])

    def test_recovered_pending_withdrawal_does_not_report_already_absent_metadata(self):
        hashes, _ = self._retention_fixture()
        key = hashes[0] + ".narinfo"
        metadata = (self.bucket / key).read_text()
        state = json.loads((self.bucket / cache.STATE_KEY).read_text())
        state["retirements"][key] = {"nar": "nar/obsolete.nar.xz", "withdrawn_at": None,
                                      "metadata": metadata}
        (self.bucket / cache.STATE_KEY).write_text(json.dumps(state))
        (self.bucket / key).unlink()
        when = cache.datetime(2026, 10, 30, 12, tzinfo=cache.timezone.utc)

        report = cache.prune(dry_run=False, clock=lambda: when)

        self.assertEqual(report["withdraw"], [])
        self.assertEqual(report["delete"], [])
        after = cache.read_state()
        self.assertEqual(after["retirements"][key]["withdrawn_at"], "2026-10-30T12:00:00Z")

    def test_retirement_uses_seven_day_boundary_and_preserves_other_objects(self):
        self._retention_fixture()
        start = cache.datetime(2026, 10, 30, 12, tzinfo=cache.timezone.utc)
        clock = mock.Mock(return_value=start)
        cache.prune(dry_run=False, clock=clock)
        self.assertFalse((self.bucket / ("0" * 32 + ".narinfo")).exists())
        self.assertTrue((self.bucket / "nar/obsolete.nar.xz").exists())
        state = json.loads((self.bucket / "control/state.json").read_text())
        self.assertEqual(state["nar_deadlines"]["nar/obsolete.nar.xz"], "2026-11-06T12:00:00Z")
        self._put("foreign/object", b"leave")
        self._put("nix-cache-info", b"StoreDir: /nix/store")
        clock.return_value = start + cache.RETENTION - cache.timedelta(seconds=1)
        cache.prune(dry_run=False, clock=clock)
        self.assertTrue((self.bucket / "nar/obsolete.nar.xz").exists())
        clock.return_value = start + cache.RETENTION
        cache.prune(dry_run=False, clock=clock)
        self.assertFalse((self.bucket / "nar/obsolete.nar.xz").exists())
        self.assertTrue((self.bucket / "nar/shared.nar.xz").exists())
        self.assertTrue((self.bucket / "nix-cache-info").exists())
        self.assertTrue((self.bucket / "foreign/object").exists())
        self.assertTrue((self.bucket / "control/state.json").exists())

    def test_interrupted_pending_withdrawal_retries_with_fresh_grace(self):
        hashes, _ = self._retention_fixture()
        start = cache.datetime(2026, 10, 30, 12, tzinfo=cache.timezone.utc)
        original_aws = cache.aws
        failed = {"once": True}
        def fail_metadata_withdrawal(*args, **kwargs):
            if args[:2] == ("s3api", "delete-object") and args[args.index("--key") + 1] == hashes[0] + ".narinfo" and failed["once"]:
                failed["once"] = False
                raise subprocess.CalledProcessError(255, ["aws"])
            return original_aws(*args, **kwargs)
        with mock.patch.object(cache, "aws", side_effect=fail_metadata_withdrawal):
            with self.assertRaises(subprocess.CalledProcessError):
                cache.prune(dry_run=False, clock=lambda: start)
        state = json.loads((self.bucket / cache.STATE_KEY).read_text())
        self.assertIsNone(state["retirements"][hashes[0] + ".narinfo"]["withdrawn_at"])
        self.assertTrue((self.bucket / (hashes[0] + ".narinfo")).exists())
        cache.prune(dry_run=False, clock=lambda: start + cache.timedelta(hours=1))
        state = json.loads((self.bucket / cache.STATE_KEY).read_text())
        self.assertEqual(state["nar_deadlines"]["nar/obsolete.nar.xz"], "2026-11-06T13:00:00Z")

    def test_final_shared_metadata_withdrawal_resets_nar_grace(self):
        hashes, roots = self._retention_fixture()
        state = json.loads((self.bucket / cache.STATE_KEY).read_text())
        first = cache.datetime(2026, 10, 30, 12, tzinfo=cache.timezone.utc)
        cache.prune(dry_run=False, clock=lambda: first)
        state = json.loads((self.bucket / cache.STATE_KEY).read_text())
        state["packages"]["x86_64-linux"]["demo"] = [state["packages"]["x86_64-linux"]["demo"][0]]
        (self.bucket / cache.STATE_KEY).write_text(json.dumps(state))
        middle = first + cache.timedelta(days=1)
        cache.prune(dry_run=False, clock=lambda: middle)
        self.assertTrue((self.bucket / (hashes[2] + ".narinfo")).exists())
        self.assertEqual(json.loads((self.bucket / cache.STATE_KEY).read_text())["nar_deadlines"]["nar/shared.nar.xz"],
                         "2026-11-07T12:00:00Z")
        state = json.loads((self.bucket / cache.STATE_KEY).read_text())
        state["packages"] = {}
        (self.bucket / cache.STATE_KEY).write_text(json.dumps(state))
        last = first + cache.timedelta(days=2)
        cache.prune(dry_run=False, clock=lambda: last)
        final = json.loads((self.bucket / cache.STATE_KEY).read_text())
        self.assertEqual(final["nar_deadlines"]["nar/shared.nar.xz"], "2026-11-08T12:00:00Z")
        self.assertTrue((self.bucket / "nar/shared.nar.xz").exists())

    def test_stale_metadata_reader_can_fetch_nar_during_grace(self):
        self._retention_fixture()
        metadata = (self.bucket / ("0" * 32 + ".narinfo")).read_bytes()
        start = cache.datetime(2026, 10, 30, 12, tzinfo=cache.timezone.utc)
        cache.prune(dry_run=False, clock=lambda: start)
        self.assertIn(b"nar/obsolete.nar.xz", metadata)
        self.assertEqual((self.bucket / "nar/obsolete.nar.xz").read_bytes(), b"nar bytes")

    def test_republication_to_new_nar_keeps_old_independent_deadline(self):
        hashes, _ = self._retention_fixture()
        state = json.loads((self.bucket / cache.STATE_KEY).read_text())
        key = hashes[0] + ".narinfo"
        state["retirements"][key] = {"nar": "nar/new.nar.xz", "withdrawn_at": "2026-10-30T12:00:00Z",
                                      "metadata": self._narinfo(hashes[0], "root-v1", "nar/new.nar.xz").decode()}
        state["nar_deadlines"]["nar/obsolete.nar.xz"] = "2026-11-10T12:00:00Z"
        (self.bucket / cache.STATE_KEY).write_text(json.dumps(state))
        self._put(hashes[0] + ".narinfo", self._narinfo(hashes[0], "root-v1", "nar/new.nar.xz"))
        self._put("nar/new.nar.xz", b"new")
        when = cache.datetime(2026, 11, 5, 12, tzinfo=cache.timezone.utc)
        cache.prune(dry_run=False, clock=lambda: when)
        next_state = json.loads((self.bucket / cache.STATE_KEY).read_text())
        self.assertEqual(next_state["nar_deadlines"]["nar/obsolete.nar.xz"], "2026-11-10T12:00:00Z")
        self.assertTrue((self.bucket / "nar/obsolete.nar.xz").exists())

    def test_narinfo_without_references_line_parses_as_no_references(self):
        # Nix omits the References line entirely for zero-reference paths.
        key = "0123456789abcdfghijklmnpqrsvwxyz.narinfo"
        text = (f"StorePath: {VALID}\nURL: nar/0123456789abcdfghijklmnpqrsvwxyz.nar.xz\nCompression: xz\n"
                "FileHash: sha256-abc=\nFileSize: 10\nNarHash: sha256-def=\nNarSize: 20\n"
                "Sig: cache-1:signature\n").encode()
        record = cache._parse_narinfo(text, key)
        self.assertEqual(record["references"], [])
        self.assertEqual(record["store_path"], VALID)

    def test_iam_user_documentation_covers_credentials_and_environment_branch_gate(self):
        docs = (ROOT / "docs/binary-cache.md").read_text()
        for required in (
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "NIX_CACHE_PRIVATE_KEY",
            "allowing only `main`",
        ):
            self.assertIn(required, docs)
        self.assertNotIn("CACHE_WRITER_ROLE_ARN", docs)

    def test_prune_workflow_schedules_automatic_cleanup_on_main(self):
        workflow = (ROOT / ".github/workflows/prune-cache.yml").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("schedule:", workflow)
        self.assertIn("aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}", workflow)
        self.assertIn("aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}", workflow)
        self.assertNotIn("role-to-assume:", workflow)
        self.assertNotIn("id-token: write", workflow)
        dry, destructive = workflow.split("\n  destructive:\n", 1)
        self.assertIn("github.ref == 'refs/heads/main'", dry)
        self.assertIn("github.ref == 'refs/heads/main'", destructive)
        self.assertNotIn("github.event_name == 'schedule'", dry)
        self.assertIn("github.event_name == 'schedule'", destructive)
        self.assertIn("inputs.destructive != true", dry)
        self.assertIn("inputs.destructive == true", destructive)
        self.assertNotIn("CACHE_PRUNE_ENABLED", destructive)
        self.assertNotIn("environment:", destructive)

    def test_destructive_workflow_step_executes_prune_and_propagates_failure(self):
        workflow = (ROOT / ".github/workflows/prune-cache.yml").read_text()
        step = workflow.split("      - name: Run destructive cache retention\n", 1)[1]
        command = step.splitlines()[0].strip().removeprefix("run: ")
        bin_dir = Path(self.temp.name) / "bin"
        bin_dir.mkdir()
        python = bin_dir / "python3"
        python.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$ARGS_LOG"\nexit "$FAKE_EXIT"\n')
        python.chmod(0o755)
        log = Path(self.temp.name) / "args"
        for exit_code in (0, 17):
            with self.subTest(exit_code=exit_code):
                result = subprocess.run(
                    ["sh", "-c", command], capture_output=True, text=True,
                    env=os.environ | {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
                                      "ARGS_LOG": str(log), "FAKE_EXIT": str(exit_code)},
                )
                self.assertEqual(result.returncode, exit_code)
                self.assertEqual(log.read_text().splitlines(),
                                 ["scripts/cache-retention.py", "prune", "--execute"])

    def test_cli_prints_redacted_aws_stderr(self):
        error = subprocess.CalledProcessError(1, ["aws"], stderr="secret-key=private-value failed\\n")
        output = __import__("io").StringIO()
        with (mock.patch("sys.stderr", output),
              mock.patch.object(cache, "prune", side_effect=error)):
            self.assertEqual(cache.main(["prune"]), 1)
        self.assertIn("secret-key=<redacted>", output.getvalue())
        self.assertNotIn("private-value", output.getvalue())

    def test_state_rejects_malformed_publication_shapes_and_retirement_records(self):
        state = cache.empty_state()
        missing_version = {"roots": [VALID], "revision": "r", "run_id": "1", "run_attempt": 1}
        state["packages"] = {"x86_64-linux": {"demo": [missing_version]}}
        with self.assertRaises(cache.CacheError):
            cache.validate_state(state)
        state = cache.empty_state()
        pub = {"version": "1", "roots": [VALID], "revision": "r", "run_id": "1", "run_attempt": 1}
        state["packages"] = {"x86_64-linux": {"demo": [pub, pub | {"version": "2"}, pub | {"version": "3"}]}}
        with self.assertRaises(cache.CacheError):
            cache.validate_state(state)
        state = cache.empty_state()
        state["vm_stacks"] = [{**pub}]
        with self.assertRaises(cache.CacheError):
            cache.validate_state(state)
        state = cache.empty_state()
        hash_key = "0123456789abcdfghijklmnpqrsvwxyz.narinfo"
        state["retirements"] = {hash_key: {"nar": "../escape", "withdrawn_at": "2026-10-30T12:00:00Z", "metadata": "signed"}}
        with self.assertRaises(cache.CacheError):
            cache.validate_state(state)
        valid_metadata = self._narinfo(hash_key.removesuffix(".narinfo"), "retired", "nar/example.nar.xz").decode()
        state["retirements"] = {hash_key: {"nar": "nar/example.nar.xz", "withdrawn_at": "not-time", "metadata": valid_metadata}}
        with self.assertRaises(cache.CacheError):
            cache.validate_state(state)
        state["retirements"] = {hash_key: {"nar": "nar/other.nar.xz", "withdrawn_at": None, "metadata": valid_metadata}}
        with self.assertRaisesRegex(cache.CacheError, "mapping"):
            cache.validate_state(state)
        state["retirements"] = {hash_key: {"nar": "nar/example.nar.xz", "withdrawn_at": None, "metadata": "not signed metadata"}}
        with self.assertRaisesRegex(cache.CacheError, "original metadata"):
            cache.validate_state(state)
        state = cache.empty_state()
        state["nar_deadlines"] = {"nar/a.nar.xz": "not-time"}
        with self.assertRaises(cache.CacheError):
            cache.validate_state(state)


if __name__ == "__main__":
    unittest.main()
