import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update-package.sh"


class UpdatePackageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.package = self.root / "pkgs/any-sync/any-sync-node.nix"
        self.package.parent.mkdir(parents=True)
        self.package.write_text('version = "1";\n')
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "add", str(self.package)], cwd=self.root, check=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.output = self.root / "output"
        self.env = os.environ | {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "GITHUB_OUTPUT": str(self.output),
        }

    def run_update(self, nix_body):
        nix = self.bin / "nix"
        nix.write_text("#!/bin/sh\nset -eu\n" + nix_body + "\n")
        nix.chmod(0o755)
        return subprocess.run(
            ["bash", str(SCRIPT), "any-sync-node"],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
        )

    def test_new_version_reports_change(self):
        result = self.run_update('printf \'version = "2";\\n\' > pkgs/any-sync/any-sync-node.nix')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_text(), "changed=true\n")
        self.assertEqual(self.package.read_text(), 'version = "2";\n')

    def test_unchanged_package_does_not_request_pull_request(self):
        result = self.run_update(":")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_text(), "changed=false\n")

    def test_updater_failure_is_not_reported_as_success(self):
        result = self.run_update('echo "upstream error" >&2; exit 1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("upstream error", result.stderr)
        self.assertFalse(self.output.exists())

    def test_unexpected_package_is_rejected(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "../../other"],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unsupported package", result.stderr)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
