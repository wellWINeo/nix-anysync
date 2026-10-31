import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cache_publish", ROOT / "scripts/cache-publish.py")
publish = importlib.util.module_from_spec(SPEC)

VALID = "/nix/store/0123456789abcdfghijklmnpqrsvwxyz-demo-1"


class CachePublishTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.fixture = self.root / "nix-fixture.json"
        self.fixture.write_text(json.dumps({
            "packages": {"demo": {"version": "1.2.3"}, "other": {"version": "4.5"}},
            "outputs": {"demo": [VALID, VALID.replace("demo-1", "demo-docs-1")],
                        "other": [VALID.replace("demo-1", "other-4")]},
            "fail_build": [], "fail_copy": False, "fail_verify": False,
        }))
        nix = self.bin / "nix"
        nix.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
f = pathlib.Path(os.environ["NIX_FIXTURE"])
data = json.loads(f.read_text())
a = sys.argv[1:]
if a[:2] == ["eval", "--impure"]:
    print(os.environ["NIX_SYSTEM"])
elif a[:2] == ["eval", "--json"] and a[2].startswith(".#packages.") and a[-2:] == ["--apply", "builtins.attrNames"]:
    print(json.dumps(list(data["packages"])))
elif a[:2] == ["eval", "--json"]:
    name = a[2].rsplit(".", 1)[0].rsplit(".", 1)[-1]
    if name not in data["packages"] or "version" not in data["packages"][name]:
        print("attribute 'version' missing", file=sys.stderr); sys.exit(1)
    print(json.dumps(data["packages"][name]["version"]))
elif a and a[0] == "build":
    name = a[-1].split(".")[-1]
    if name in data["fail_build"]: sys.exit(7)
    print("\\n".join(data["outputs"][name]))
elif a and a[0] == "copy":
    if data["fail_copy"]: sys.exit(8)
elif a and a[0] == "path-info":
    print(json.dumps([{"path": p} for p in data["outputs"]["demo"]]))
elif a and a[0] == "store" and a[1:2] == ["verify"]:
    if data["fail_verify"]: sys.exit(9)
else: sys.exit(2)
''')
        nix.chmod(0o755)
        self.env = os.environ | {
            "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
            "NIX_FIXTURE": str(self.fixture), "NIX_SYSTEM": "x86_64-linux",
            "CACHE_BUCKET": "test-bucket", "CACHE_REGION": "us-test-1",
            "CACHE_SIGNING_KEY_FILE": str(self.root / "secret key"),
            "GITHUB_SHA": "revision", "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
        }
        (self.root / "secret key").write_text("never logged")
        self.patch_env = mock.patch.dict(os.environ, self.env)
        self.patch_env.start()
        self.addCleanup(self.patch_env.stop)
        self.nix_calls = []
        real_run = subprocess.run
        def track_run(command, *args, **kwargs):
            if command and command[0] == "nix":
                self.nix_calls.append(command)
            return real_run(command, *args, **kwargs)
        self.track = mock.patch.object(subprocess, "run", side_effect=track_run)
        self.track.start()
        self.addCleanup(self.track.stop)
        SPEC.loader.exec_module(publish)
        self.state = publish.retention.empty_state()
        self.writes = []
        self.mock_lock = mock.patch.object(publish.retention, "locked")
        manager = self.mock_lock.start()
        manager.return_value.__enter__.return_value = object()
        self.addCleanup(self.mock_lock.stop)
        self.mock_read = mock.patch.object(publish.retention, "read_state", side_effect=lambda: self.state)
        self.mock_read.start()
        self.addCleanup(self.mock_read.stop)
        def write(state, lock):
            self.writes.append(json.loads(json.dumps(state)))
        self.mock_write = mock.patch.object(publish.retention, "write_state", side_effect=write)
        self.mock_write.start()
        self.addCleanup(self.mock_write.stop)
        self.mock_verify = mock.patch.object(publish, "verify_roots", side_effect=lambda uri, roots: set(roots))
        self.mock_verify.start()
        self.addCleanup(self.mock_verify.stop)

    def run_publish(self):
        return publish.main(["x86_64-linux"])

    def _add_pending_retirement(self, path, nar):
        store_name = path.rsplit("/", 1)[-1]
        store_hash, name = store_name.split("-", 1)
        key = store_hash + ".narinfo"
        text = (f"StorePath: {path}\nURL: {nar}\nCompression: xz\nFileHash: sha256-abc=\n"
                "FileSize: 10\nNarHash: sha256-def=\nNarSize: 20\nReferences: \n"
                "Sig: cache-1:signature\n")
        self.state["retirements"][key] = {"nar": nar, "withdrawn_at": None, "metadata": text}
        return key

    def test_verified_package_republication_supersedes_pending_retirement_only_after_copy(self):
        key = self._add_pending_retirement(VALID, "nar/old.nar.xz")
        self.state["nar_deadlines"]["nar/old.nar.xz"] = "2026-11-10T12:00:00Z"
        self.assertEqual(self.run_publish(), 0)
        self.assertNotIn(key, self.state["retirements"])
        self.assertEqual(self.state["nar_deadlines"]["nar/old.nar.xz"], "2026-11-10T12:00:00Z")
        self.assertTrue(self.writes)

    def test_unverified_package_copy_does_not_supersede_pending_retirement(self):
        key = self._add_pending_retirement(VALID, "nar/old.nar.xz")
        self.state["nar_deadlines"]["nar/old.nar.xz"] = "2026-11-10T12:00:00Z"
        with mock.patch.object(publish, "verify_roots", side_effect=publish.PublishError("verification failed")):
            self.assertNotEqual(self.run_publish(), 0)
        self.assertIn(key, self.state["retirements"])
        self.assertEqual(self.state["nar_deadlines"]["nar/old.nar.xz"], "2026-11-10T12:00:00Z")
        self.assertEqual(self.writes, [])

    def test_verified_vm_republication_supersedes_pending_retirement(self):
        driver = VALID.replace("demo-1", "nixos-test-driver")
        valkey = VALID.replace("demo-1", "valkey-custom")
        key = self._add_pending_retirement(driver, "nar/old-vm.nar.xz")
        self.state["nar_deadlines"]["nar/old-vm.nar.xz"] = "2026-11-10T12:00:00Z"
        def fake_nix(*args):
            if args[:2] == ("eval", "--impure"):
                return mock.Mock(stdout="x86_64-linux")
            if args[0] == "build":
                return mock.Mock(stdout=driver + "\n")
            if args[:2] == ("eval", "--raw"):
                return mock.Mock(stdout=valkey)
            if args[0] == "path-info":
                return mock.Mock(stdout=json.dumps([{"path": driver}, {"path": valkey}]))
            if args[0] == "copy":
                return mock.Mock(stdout="")
            raise AssertionError(args)
        with (mock.patch.object(publish, "_run_nix", side_effect=fake_nix),
              mock.patch.object(publish, "verify_roots", return_value={driver, valkey})):
            self.assertEqual(publish.publish_vm_stack(), 0)
        self.assertNotIn(key, self.state["retirements"])
        self.assertEqual(self.state["nar_deadlines"]["nar/old-vm.nar.xz"], "2026-11-10T12:00:00Z")

    def test_public_test_workflow_keeps_vm_build_and_safe_cache_wiring(self):
        workflow = (ROOT / ".github/workflows/test-nixos.yml").read_text()

        def check(text):
            self.assertIn("nix build --show-trace --print-build-logs .#checks.x86_64-linux.any-sync-test", text)
            self.assertIn("NIX_CACHE_URL", text)
            self.assertIn("NIX_CACHE_PUBLIC_KEY", text)
            self.assertIn("extra_nix_config", text)
            self.assertIn("steps.cache-config.outputs.extra_nix_config", text)
            self.assertNotRegex(text, r"trusted\s*=\s*true")
            self.assertNotRegex(text, r"require-sigs\s*=\s*false")

        check(workflow)
        mutated = workflow.replace(
            "nix build --show-trace --print-build-logs .#checks.x86_64-linux.any-sync-test",
            "true", 1)
        with self.assertRaises(AssertionError):
            check(mutated)

    def test_failure_diagnostics_surface_stderr_and_redact_secret_key(self):
        error = publish.PublishError("nix command failed")
        error.stderr = "failed secret-key=/tmp/private%20file details\\n"
        output = __import__("io").StringIO()
        with (mock.patch("sys.stderr", output),
              mock.patch.object(publish, "publish_system", side_effect=error)):
            self.assertEqual(publish.main(["x86_64-linux"]), 1)
        self.assertIn("failed", output.getvalue())
        self.assertIn("secret-key=<redacted>", output.getvalue())
        self.assertNotIn("/tmp/private", output.getvalue())

    def test_dynamic_discovery_one_build_per_package_and_actual_roots(self):
        self.assertEqual(self.run_publish(), 0)
        builds = [command for command in self.nix_calls if command[1] == "build"]
        self.assertEqual(len(builds), 2)
        packages = self.state["packages"]["x86_64-linux"]
        self.assertEqual(packages["demo"][0]["version"], "1.2.3")
        self.assertEqual(packages["demo"][0]["roots"], json.loads(self.fixture.read_text())["outputs"]["demo"])
        self.assertEqual(set(packages), {"demo", "other"})

    def test_build_failure_is_nonzero_and_does_not_advance_that_package(self):
        data = json.loads(self.fixture.read_text()); data["fail_build"] = ["demo"]
        self.fixture.write_text(json.dumps(data))
        self.assertNotEqual(self.run_publish(), 0)
        self.assertNotIn("demo", self.state["packages"].get("x86_64-linux", {}))

    def test_copy_failure_does_not_advance_manifest(self):
        data = json.loads(self.fixture.read_text()); data["fail_copy"] = True
        self.fixture.write_text(json.dumps(data))
        with mock.patch.object(publish, "verify_roots", side_effect=AssertionError("must not verify")):
            self.assertNotEqual(self.run_publish(), 0)
        self.assertEqual(self.writes, [])

    def test_closure_verification_failure_does_not_advance_manifest(self):
        with mock.patch.object(publish, "verify_roots", side_effect=publish.PublishError("verification failed")):
            self.assertNotEqual(self.run_publish(), 0)
        self.assertEqual(self.writes, [])

    def test_same_roots_with_distinct_versions_are_both_retained(self):
        roots = json.loads(self.fixture.read_text())["outputs"]["demo"]
        self.state["packages"] = {"x86_64-linux": {"demo": [{
            "version": "old-version", "roots": roots,
            "revision": "old", "run_id": "1", "run_attempt": 1,
        }]}}
        self.assertEqual(self.run_publish(), 0)
        versions = self.state["packages"]["x86_64-linux"]["demo"]
        self.assertEqual([v["version"] for v in versions], ["1.2.3", "old-version"])
        self.assertEqual(versions[0]["roots"], versions[1]["roots"])

    def test_unchanged_roots_and_version_do_not_create_new_retention_entry(self):
        data = json.loads(self.fixture.read_text())
        data["packages"].pop("other")
        data["outputs"].pop("other")
        self.fixture.write_text(json.dumps(data))
        roots = data["outputs"]["demo"]
        self.state["packages"] = {"x86_64-linux": {"demo": [{
            "version": "1.2.3", "roots": roots,
            "revision": "revision", "run_id": "123", "run_attempt": 1,
        }]}}
        before = json.dumps(self.state, sort_keys=True)
        self.assertEqual(self.run_publish(), 0)
        self.assertEqual(json.dumps(self.state, sort_keys=True), before)

    def test_discovered_package_missing_version_fails_instead_of_skipping(self):
        data = json.loads(self.fixture.read_text())
        data["packages"]["missing-version"] = {}
        data["outputs"]["missing-version"] = [VALID.replace("demo-1", "missing-version")]
        self.fixture.write_text(json.dumps(data))
        self.assertNotEqual(self.run_publish(), 0)
        self.assertEqual(self.writes, [])
        self.assertFalse(any(command[-1].endswith("missing-version") and command[1] == "build"
                             for command in self.nix_calls))

    def test_destination_uri_encodes_bucket_region_and_secret_filename(self):
        uri = publish.destination_uri("bucket.name", "us-west-2", "/tmp/key file")
        self.assertEqual(uri, "s3://bucket.name?region=us-west-2&secret-key=%2Ftmp%2Fkey%20file")

    def test_destination_verification_accepts_real_keyed_json_and_checks_complete_closure(self):
        reference = "/nix/store/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-dependency-1"
        closure = {
            VALID: {"references": [reference], "narHash": "sha256-root"},
            reference: {"references": [], "narHash": "sha256-dependency"},
        }
        self.assert_destination_closure_verifies(closure, [VALID], [VALID, reference])

    def test_destination_verification_accepts_list_json_format(self):
        self.assert_destination_closure_verifies(
            [{"path": VALID, "references": [], "narHash": "sha256-root"}], [VALID], [VALID])

    def assert_destination_closure_verifies(self, info_value, roots, closure_paths):
        metadata_by_path = {}
        for path in closure_paths:
            hash_part = path.rsplit("/", 1)[1].split("-", 1)[0]
            metadata_by_path[hash_part] = ("\n".join([
                f"StorePath: {path}", f"URL: nar/{hash_part}.nar.xz", "Compression: xz",
                "FileHash: sha256-abc=", "FileSize: 10", "NarHash: sha256-def=", "NarSize: 20",
                "References: ", "Sig: cache-1:signature", "",
            ])).encode()
        info = mock.Mock(stdout=json.dumps(info_value))
        calls = []
        def fake_aws(*args):
            calls.append(args)
            if args[0] == "s3api" and args[1] == "get-object":
                key_index = args.index("--key") + 1
                Path(args[-1]).write_bytes(metadata_by_path[args[key_index].removesuffix(".narinfo")])
            return mock.Mock(stdout="{}")
        self.mock_verify.stop()
        with (mock.patch.object(publish, "_run_nix", return_value=info) as nix,
              mock.patch.object(publish, "_aws", side_effect=fake_aws)):
            publish.verify_roots("s3://test-bucket?region=us-test-1", roots)
        for path in closure_paths:
            hash_part = path.rsplit("/", 1)[1].split("-", 1)[0]
            self.assertIn(("s3api", "head-object", "--bucket", "test-bucket",
                           "--key", f"nar/{hash_part}.nar.xz"), calls)
        self.assertEqual(nix.call_count, len(closure_paths) + 1)
        self.assertIn("--refresh", nix.call_args_list[0].args)
        self.assertTrue(all("--sigs-needed" in call.args for call in nix.call_args_list[1:]))

    def test_incomplete_destination_closure_is_rejected(self):
        info = mock.Mock(stdout=json.dumps({VALID: {"references": ["/nix/store/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-missing"]}}))
        self.mock_verify.stop()
        with (mock.patch.object(publish, "_run_nix", return_value=info),
              mock.patch.object(publish, "_aws") as aws):
            with self.assertRaises(publish.PublishError):
                publish.verify_roots("s3://test-bucket?region=us-test-1", [VALID])
        aws.assert_not_called()

    def test_vm_stack_publishes_explicit_driver_and_custom_valkey_not_test_result(self):
        driver = VALID.replace("demo-1", "nixos-test-driver")
        valkey = VALID.replace("demo-1", "valkey-custom")
        calls = []
        def fake_nix(*args):
            calls.append(args)
            if args[:2] == ("eval", "--impure"):
                return mock.Mock(stdout="x86_64-linux")
            if args[0] == "build":
                return mock.Mock(stdout=driver + "\n")
            if args[:2] == ("eval", "--raw"):
                return mock.Mock(stdout=valkey)
            if args[0] == "path-info":
                return mock.Mock(stdout=json.dumps([{"path": driver}, {"path": valkey}]))
            if args[0] == "copy":
                return mock.Mock(stdout="")
            raise AssertionError(args)
        with (mock.patch.object(publish, "_run_nix", side_effect=fake_nix),
              mock.patch.object(publish, "verify_roots", return_value={driver, valkey}) as verify):
            self.assertEqual(publish.publish_vm_stack(), 0)
        roots = self.state["vm_stacks"][0]["roots"]
        self.assertEqual(roots, [driver, valkey])
        verify.assert_called_once()
        copy = next(call for call in calls if call[0] == "copy")
        self.assertNotIn(".#checks.x86_64-linux.any-sync-test", copy)
        self.assertNotIn("any-sync-test", roots)

    def test_vm_upload_failure_does_not_advance_stack_state(self):
        driver = VALID.replace("demo-1", "nixos-test-driver")
        valkey = VALID.replace("demo-1", "valkey-custom")
        def fake_nix(*args):
            if args[:2] == ("eval", "--impure"):
                return mock.Mock(stdout="x86_64-linux")
            if args[0] == "build":
                return mock.Mock(stdout=driver + "\n")
            if args[:2] == ("eval", "--raw"):
                return mock.Mock(stdout=valkey)
            if args[0] == "path-info":
                return mock.Mock(stdout=json.dumps([{"path": driver}, {"path": valkey}]))
            if args[0] == "copy":
                raise publish.PublishError("copy failed")
            raise AssertionError(args)
        with (mock.patch.object(publish, "_run_nix", side_effect=fake_nix),
              mock.patch.object(publish, "verify_roots", return_value={driver, valkey}) as verify):
            self.assertEqual(publish.publish_vm_stack(), 1)
        self.assertEqual(self.writes, [])
        self.assertEqual(self.state["vm_stacks"], [])
        verify.assert_not_called()

    def workflow_run_script(self, step_name):
        lines = (ROOT / ".github/workflows/publish-cache.yml").read_text().splitlines()
        step_start = lines.index(f"      - name: {step_name}")
        run_start = lines.index("        run: |", step_start)
        body = []
        for line in lines[run_start + 1:]:
            if line and not line.startswith("          "):
                break
            body.append(line[10:] if line.startswith("          ") else "")
        return "\n".join(body)

    def test_vm_workflow_runs_real_test_before_root_publication(self):
        workflow = (ROOT / ".github/workflows/publish-cache.yml").read_text()
        test_step = workflow.index("- name: Run actual x86_64 Linux VM test")
        actual_test = workflow.index("nix build --show-trace --print-build-logs .#checks.x86_64-linux.any-sync-test", test_step)
        publish_step = workflow.index("- name: Build, publish, and verify package closures")
        self.assertIn("bash scripts/verify-kvm.sh", workflow[test_step:actual_test])
        self.assertLess(actual_test, publish_step)
        self.assertIn('if [[ "${{ matrix.system }}" == "x86_64-linux" ]]', workflow[publish_step:])
        self.assertIn("if: matrix.system == 'x86_64-linux'", workflow[test_step:actual_test])

    def _run_kvm_permission_fixture(self, *, fail_chmod=False, inaccessible_after_chmod=False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        bindir = root / "bin"
        bindir.mkdir()
        log = root / "sudo.log"
        (bindir / "sudo").write_text(f"""#!/bin/bash
printf '%s\\n' "$*" >> "$SUDO_LOG"
if [[ "$1" == chmod ]]; then {'exit 8' if fail_chmod else 'exit 0'}; fi
if [[ "$2" == runner ]]; then exit 0; fi
{'exit 1' if inaccessible_after_chmod else 'count=$(grep -c \'^-u nixbld1\' "$SUDO_LOG" || true); [[ "$count" -gt 1 ]]'}
""")
        (bindir / "getent").write_text("#!/bin/sh\necho nixbld1:x:1001:1001::/var/empty:/sbin/nologin\n")
        (bindir / "id").write_text("#!/bin/sh\necho runner\n")
        for tool in bindir.iterdir():
            tool.chmod(0o755)
        env = os.environ | {"PATH": str(bindir) + os.pathsep + os.environ["PATH"], "SUDO_LOG": str(log)}
        result = subprocess.run(["bash", "scripts/verify-kvm.sh", "/dev/null"], cwd=ROOT,
                                env=env, capture_output=True, text=True)
        return result, log.read_text() if log.exists() else ""

    def test_kvm_permission_script_requires_character_device(self):
        with tempfile.TemporaryDirectory() as temp:
            regular_file = Path(temp) / "not-kvm"
            regular_file.write_text("")
            result = subprocess.run(["bash", "scripts/verify-kvm.sh", str(regular_file)],
                                    cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not provide", result.stderr)

    def test_kvm_permission_script_rechecks_all_users_after_permission_change(self):
        result, calls = self._run_kvm_permission_fixture()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("chmod a+rw /dev/null", calls)
        self.assertEqual(calls.count("-u nixbld1"), 2)
        self.assertIn("-u runner", calls)

    def test_kvm_permission_script_fails_when_chmod_fails(self):
        result, calls = self._run_kvm_permission_fixture(fail_chmod=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("chmod a+rw /dev/null", calls)

    def test_kvm_permission_script_fails_if_user_remains_inaccessible(self):
        result, calls = self._run_kvm_permission_fixture(inaccessible_after_chmod=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertGreaterEqual(calls.count("-u nixbld1"), 2)

    def test_failed_vm_test_stops_workflow_before_stack_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bindir = root / "bin"
            bindir.mkdir()
            (bindir / "nix").write_text("""#!/bin/sh
echo "$*" >> "$NIX_LOG"
exit "$NIX_EXIT"
""")
            (bindir / "sudo").write_text("#!/bin/sh\nexit 0\n")
            (bindir / "getent").write_text("#!/bin/sh\nexit 0\n")
            (bindir / "id").write_text("#!/bin/sh\necho runner\n")
            (bindir / "python3").write_text("""#!/bin/bash
echo "$*" >> "$PYTHON_LOG"
if [[ "$*" == *vm-stack* ]]; then echo advanced >> "$STATE_LOG"; fi
""")
            for tool in bindir.iterdir():
                tool.chmod(0o755)
            kvm = Path("/dev/null")
            env = os.environ | {"PATH": str(bindir) + os.pathsep + os.environ["PATH"],
                "NIX_LOG": str(root / "nix.log"), "PYTHON_LOG": str(root / "python.log"),
                "STATE_LOG": str(root / "state"), "NIX_EXIT": "23"}
            # Run the actual workflow shell steps in order; GitHub's default is to stop after failure.
            test_script = self.workflow_run_script("Run actual x86_64 Linux VM test").replace(
                "bash scripts/verify-kvm.sh", f"bash scripts/verify-kvm.sh '{kvm}'")
            publish_script = self.workflow_run_script("Build, publish, and verify package closures").replace(
                "${{ matrix.system }}", "x86_64-linux")
            results = []
            for step_script in (test_script, publish_script):
                step = subprocess.run(["bash", "-euo", "pipefail", "-c", step_script], cwd=ROOT,
                                      env=env, capture_output=True, text=True)
                results.append(step)
                if step.returncode:
                    break
            self.assertEqual(results[0].returncode, 23, results[0].stderr)
            self.assertEqual(len(results), 1, "workflow must not start publication after VM test failure")
            self.assertFalse((root / "python.log").exists())
            self.assertFalse((root / "state").exists())
            self.assertIn("checks.x86_64-linux.any-sync-test", (root / "nix.log").read_text())

    def test_two_latest_successful_vm_revisions_are_retained(self):
        roots_a = [VALID]
        roots_b = [VALID.replace("demo-1", "other-2")]
        roots_c = [VALID.replace("demo-1", "other-3")]
        state = publish.retention.empty_state()
        for revision, roots in (("a", roots_a), ("b", roots_b), ("c", roots_c)):
            publish.retention.record_vm_stack(state, roots, revision, revision, 1, verified=True)
        self.assertEqual([stack["revision"] for stack in state["vm_stacks"]], ["c", "b"])

    def test_publish_workflow_is_trusted_native_serial_matrix_without_pr_trigger(self):
        workflow = (ROOT / ".github/workflows/publish-cache.yml").read_text()
        for runner, system in (("ubuntu-24.04", "x86_64-linux"),
                               ("ubuntu-24.04-arm", "aarch64-linux"),
                               ("macos-15-intel", "x86_64-darwin"),
                               ("macos-15", "aarch64-darwin")):
            self.assertIn(f"runner: {runner}", workflow)
            self.assertIn(f"system: {system}", workflow)
        self.assertIn("max-parallel: 1", workflow)
        self.assertIn("aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}", workflow)
        self.assertIn("aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}", workflow)
        self.assertNotIn("id-token: write", workflow)
        self.assertNotIn("role-to-assume:", workflow)
        self.assertIn("secrets.NIX_CACHE_PRIVATE_KEY", workflow)
        self.assertIn("chmod 0600", workflow)
        self.assertIn("trap 'rm -f", workflow)
        self.assertNotIn("pull_request", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("\non:\n  push:", workflow)
        self.assertIn("concurrency:\n  group: publish-cache", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)

    def test_actual_workflow_shell_step_passes_private_key_file_and_removes_it(self):
        lines = (ROOT / ".github/workflows/publish-cache.yml").read_text().splitlines()
        step_start = lines.index("      - name: Build, publish, and verify package closures")
        run_start = lines.index("        run: |", step_start)
        body = []
        for line in lines[run_start + 1:]:
            if line and not line.startswith("          "):
                break
            body.append(line[10:] if line.startswith("          ") else "")
        script = "\n".join(body).replace("${{ matrix.system }}", "x86_64-linux")
        self.assertEqual(script.count("mktemp"), 1)
        self.assertIn('if [[ "x86_64-linux" == "x86_64-linux" ]]', script)
        for exit_code in (0, 9):
            with self.subTest(exit_code=exit_code), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                fake_python = root / "python3"
                fake_python.write_text("\n".join([
                    "#!/bin/bash", "set -euo pipefail",
                    '[[ -f "$CACHE_SIGNING_KEY_FILE" ]] || exit 80',
                    'mode="$(ls -ld "$CACHE_SIGNING_KEY_FILE" | cut -c2-10)"',
                    '[[ "$mode" == rw------- ]] || exit 81',
                    '[[ "$(cat "$CACHE_SIGNING_KEY_FILE")" == "$FAKE_EXPECTED_KEY" ]] || exit 82',
                    'printf \'%s|%s|%s\\n\' "$CACHE_SIGNING_KEY_FILE" "$mode" "$(cat "$CACHE_SIGNING_KEY_FILE")" > "$FAKE_PYTHON_REPORT"',
                    'exit "$FAKE_PYTHON_EXIT"',
                ]) + "\n")
                fake_python.chmod(0o755)
                report = root / "observed"
                env = os.environ | {
                    "PATH": str(root) + os.pathsep + os.environ["PATH"],
                    "NIX_CACHE_PRIVATE_KEY": "test private signing material",
                    "FAKE_EXPECTED_KEY": "test private signing material",
                    "FAKE_PYTHON_REPORT": str(report),
                    "FAKE_PYTHON_EXIT": str(exit_code),
                }
                result = subprocess.run(["bash", "-euo", "pipefail", "-c", script],
                                        cwd=ROOT, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, exit_code, result.stderr)
                observed_path, observed_mode, observed_content = report.read_text().rstrip("\n").split("|", 2)
                self.assertEqual(observed_mode, "rw-------")
                self.assertEqual(observed_content, "test private signing material")
                self.assertFalse(Path(observed_path).exists())


if __name__ == "__main__":
    unittest.main()
