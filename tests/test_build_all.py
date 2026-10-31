import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BuildAllTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.calls = self.root / "calls.jsonl"
        self.nix = self.bin / "nix"
        self.nix.write_text(f"""#!{sys.executable}
import json, os, sys
args = sys.argv[1:]
with open(os.environ['CALLS'], 'a') as calls:
    calls.write(json.dumps(args) + '\\n')
if args[:2] == ['eval', '--impure']:
    if os.environ.get('SYSTEM_FAIL') == '1':
        sys.exit(11)
    print(os.environ.get('SYSTEM', 'x86_64-linux'))
elif args[:2] == ['eval', '--json']:
    if os.environ.get('DISCOVERY_FAIL') == '1':
        print('discovery diagnostic from nix', file=sys.stderr)
        sys.exit(12)
    print(os.environ.get('PACKAGES', '["demo", "other"]'))
elif args[:1] == ['build']:
    print('build output from nix: ' + args[1])
    if args[1] == os.environ.get('BUILD_FAIL'):
        print('build diagnostic from nix', file=sys.stderr)
        sys.exit(13)
else:
    sys.exit(14)
""")
        self.nix.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def run_builder(self, **overrides):
        env = os.environ.copy()
        env.update({"PATH": f"{self.bin}:{env['PATH']}", "CALLS": str(self.calls)})
        env.update(overrides)
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/build-all.py")],
            cwd=ROOT, env=env, capture_output=True, text=True,
        )

    def calls_made(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def test_happy_path_discovers_and_builds_every_package(self):
        result = self.run_builder()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("build output from nix: .#demo", result.stdout)
        self.assertIn("build output from nix: .#other", result.stdout)
        calls = self.calls_made()
        self.assertEqual(calls[0], ["eval", "--impure", "--raw", "--expr", "builtins.currentSystem"])
        self.assertEqual(calls[1], ["eval", "--json", ".#packages.x86_64-linux", "--apply", "builtins.attrNames"])
        self.assertEqual(calls[2:], [["build", ".#demo"], ["build", ".#other"]])

    def test_current_system_failure_stops_discovery(self):
        result = self.run_builder(SYSTEM_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.calls_made()), 1)

    def test_package_discovery_failure_propagates(self):
        result = self.run_builder(DISCOVERY_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("discovery diagnostic from nix", result.stderr)
        self.assertEqual(len(self.calls_made()), 2)

    def test_invalid_json_fails_without_building(self):
        result = self.run_builder(PACKAGES="not json")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.calls_made()), 2)

    def test_empty_and_malformed_package_lists_fail_without_building(self):
        for packages in ("[]", "{}", '["good", ""]', '["same", "same"]'):
            with self.subTest(packages=packages):
                self.calls.unlink(missing_ok=True)
                result = self.run_builder(PACKAGES=packages)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(self.calls_made()), 2)

    def test_package_build_failure_propagates_and_stops_later_builds(self):
        result = self.run_builder(BUILD_FAIL=".#demo")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("build output from nix: .#demo", result.stdout)
        self.assertIn("build diagnostic from nix", result.stderr)
        self.assertEqual(self.calls_made()[-1], ["build", ".#demo"])
        self.assertEqual(len(self.calls_made()), 3)


if __name__ == "__main__":
    unittest.main()
