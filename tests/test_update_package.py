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


class GroupedUpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.packages = [
            "any-sync-consensus", "any-sync-coordinator", "any-sync-filenode",
            "any-sync-node", "any-sync-tools",
        ]
        package_dir = self.root / "pkgs/any-sync"
        package_dir.mkdir(parents=True)
        for name in self.packages:
            (package_dir / f"{name}.nix").write_text('version = "1";\n')
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "add", "pkgs/any-sync"], cwd=self.root, check=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        nix = self.bin / "nix"
        nix.write_text('''#!/bin/sh
set -eu
for arg do package="$arg"; done
printf '%s\\n' "$package" >> "$CALLS"
if [ "$package" = "${FAIL_PACKAGE:-}" ]; then
  echo "update failed for $package" >&2
  exit 1
fi
case ",${CHANGED_PACKAGES:-}," in
  *",$package,"*) printf 'version = "2";\\n' > "pkgs/any-sync/$package.nix" ;;
esac
''')
        nix.chmod(0o755)
        self.output = self.root / "output"
        self.calls = self.root / "calls"
        self.env = os.environ | {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "GITHUB_OUTPUT": str(self.output),
            "CALLS": str(self.calls),
        }

    def run_update(self):
        return subprocess.run(
            ["bash", str(SCRIPT.parent / "update-packages.sh")],
            cwd=self.root, env=self.env, capture_output=True, text=True,
        )

    def test_changes_to_multiple_packages_are_reported_as_one_update(self):
        self.env["CHANGED_PACKAGES"] = "any-sync-consensus,any-sync-tools"
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_text(), "changed=true\n")
        self.assertEqual(self.calls.read_text().splitlines(), self.packages)
        self.assertEqual((self.root / "pkgs/any-sync/any-sync-tools.nix").read_text(), 'version = "2";\n')

    def test_unchanged_stack_does_not_request_pull_request(self):
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_text(), "changed=false\n")
        self.assertEqual(self.calls.read_text().splitlines(), self.packages)

    def test_failure_after_an_update_does_not_report_partial_success(self):
        self.env["CHANGED_PACKAGES"] = "any-sync-consensus"
        self.env["FAIL_PACKAGE"] = "any-sync-node"
        result = self.run_update()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("update failed for any-sync-node", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.calls.read_text().splitlines(), self.packages[:4])


class FindUpdateBranchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text('''#!/bin/sh
set -eu
[ "$1" = pr ] && [ "$2" = list ]
if [ "${FAIL_GH:-}" = true ]; then echo "API failed" >&2; exit 1; fi
printf '%s' "${BRANCHES:-}"
''')
        gh.chmod(0o755)
        self.output = self.root / "output"
        self.github_env = self.root / "github-env"
        self.env = os.environ | {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "GITHUB_REPOSITORY": "test/repo",
            "BASE_BRANCH": "main",
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "2",
            "GITHUB_OUTPUT": str(self.output),
            "GITHUB_ENV": str(self.github_env),
        }

    def find(self):
        return subprocess.run(
            ["bash", str(SCRIPT.parent / "find-update-branch.sh")],
            cwd=self.root, env=self.env, capture_output=True, text=True,
        )

    def test_new_update_uses_unique_branch(self):
        result = self.find()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_text(), "open=false\n")
        self.assertEqual(self.github_env.read_text(), "UPDATE_BRANCH=automation/update-any-sync-stack-123-2\n")

    def test_existing_pr_reuses_its_branch(self):
        self.env["BRANCHES"] = "automation/update-any-sync-stack-50-1\n"
        result = self.find()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_text(), "open=true\n")
        self.assertEqual(self.github_env.read_text(), "UPDATE_BRANCH=automation/update-any-sync-stack-50-1\n")

    def test_multiple_prs_fail_instead_of_selecting_one(self):
        self.env["BRANCHES"] = "automation/update-any-sync-stack-50-1\nautomation/update-any-sync-stack-51-1\n"
        result = self.find()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Multiple open", result.stderr)
        self.assertFalse(self.output.exists())

    def test_invalid_branch_is_rejected(self):
        self.env["BRANCHES"] = "automation/update-any-sync-stack-not-a-run\n"
        result = self.find()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid stack update branch", result.stderr)
        self.assertFalse(self.output.exists())

    def test_api_failure_does_not_act_as_no_pr(self):
        self.env["FAIL_GH"] = "true"
        result = self.find()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("API failed", result.stderr)
        self.assertFalse(self.output.exists())


class PrepareUpdateBranchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.remote = self.root / "remote.git"
        self.source = self.root / "source"
        self.runner = self.root / "runner"
        self.branch = "automation/update-any-sync-stack"
        self.env = os.environ | {
            "GIT_AUTHOR_NAME": "Test Maintainer",
            "GIT_AUTHOR_EMAIL": "maintainer@example.invalid",
            "GIT_COMMITTER_NAME": "Test Maintainer",
            "GIT_COMMITTER_EMAIL": "maintainer@example.invalid",
        }
        self.git(self.root, "init", "--bare", "-q", str(self.remote))
        self.git(self.root, "init", "-q", "-b", "main", str(self.source))
        (self.source / "package.nix").write_text("base\n")
        self.git(self.source, "add", "package.nix")
        self.git(self.source, "commit", "-qm", "base")
        self.git(self.source, "remote", "add", "origin", str(self.remote))
        self.git(self.source, "push", "-q", "origin", "main")
        self.git(self.root, "--git-dir", str(self.remote), "symbolic-ref", "HEAD", "refs/heads/main")

    def git(self, cwd, *args):
        return subprocess.run(
            ["git", *args], cwd=cwd, env=self.env, check=True,
            capture_output=True, text=True,
        ).stdout.strip()

    def create_remote_branch(self):
        self.git(self.source, "switch", "-qc", self.branch)
        (self.source / "package.nix").write_text("manual fix\n")
        self.git(self.source, "add", "package.nix")
        self.git(self.source, "commit", "-qm", "manual fix")
        commit = self.git(self.source, "rev-parse", "HEAD")
        self.git(self.source, "push", "-q", "origin", self.branch)
        self.git(self.source, "switch", "-q", "main")
        return commit

    def clone(self):
        self.git(self.root, "clone", "-q", str(self.remote), str(self.runner))

    def prepare(self, pr_open):
        return subprocess.run(
            ["bash", str(SCRIPT.parent / "prepare-update-branch.sh"), "main", self.branch, pr_open],
            cwd=self.runner, env=self.env, capture_output=True, text=True,
        )

    def test_new_branch_starts_at_main(self):
        self.clone()
        result = self.prepare("false")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git(self.runner, "branch", "--show-current"), self.branch)
        self.assertEqual(self.git(self.runner, "rev-parse", "HEAD"), self.git(self.runner, "rev-parse", "origin/main"))

    def test_existing_pr_preserves_manual_commit_and_merges_main(self):
        manual_commit = self.create_remote_branch()
        (self.source / "other.nix").write_text("main change\n")
        self.git(self.source, "add", "other.nix")
        self.git(self.source, "commit", "-qm", "main change")
        self.git(self.source, "push", "-q", "origin", "main")
        self.clone()
        result = self.prepare("true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.runner / "package.nix").read_text(), "manual fix\n")
        self.assertEqual((self.runner / "other.nix").read_text(), "main change\n")
        self.git(self.runner, "merge-base", "--is-ancestor", manual_commit, "HEAD")
        self.git(self.runner, "merge-base", "--is-ancestor", "origin/main", "HEAD")

    def test_existing_branch_without_open_pr_is_not_replaced(self):
        commit = self.create_remote_branch()
        self.clone()
        result = self.prepare("false")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already exists", result.stderr)
        self.assertEqual(self.git(self.runner, "rev-parse", f"origin/{self.branch}"), commit)

    def test_conflicting_main_does_not_update_remote_branch(self):
        commit = self.create_remote_branch()
        (self.source / "package.nix").write_text("conflicting main change\n")
        self.git(self.source, "add", "package.nix")
        self.git(self.source, "commit", "-qm", "conflicting main change")
        self.git(self.source, "push", "-q", "origin", "main")
        self.clone()
        result = self.prepare("true")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git(self.runner, "rev-parse", f"origin/{self.branch}"), commit)

    def push_update(self):
        env = self.env | {
            "UPDATE_BRANCH": self.branch,
            "BASE_BRANCH": "main",
            "PR_OPEN": "true",
            "GITHUB_REPOSITORY": "test/repo",
        }
        return subprocess.run(
            ["bash", str(SCRIPT.parent / "push-update-branch.sh")],
            cwd=self.runner, env=env, capture_output=True, text=True,
        )

    def test_push_appends_to_existing_manual_commit(self):
        manual_commit = self.create_remote_branch()
        self.clone()
        self.assertEqual(self.prepare("true").returncode, 0)
        (self.runner / "new.nix").write_text("new update\n")
        self.git(self.runner, "add", "new.nix")
        self.git(self.runner, "commit", "-qm", "new update")
        result = self.push_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.git(self.runner, "merge-base", "--is-ancestor", manual_commit, "HEAD")
        self.assertEqual(self.git(self.root, "--git-dir", str(self.remote), "rev-parse", self.branch), self.git(self.runner, "rev-parse", "HEAD"))

    def test_concurrent_push_is_rejected_without_losing_manual_commit(self):
        self.create_remote_branch()
        self.clone()
        self.assertEqual(self.prepare("true").returncode, 0)
        self.git(self.source, "switch", "-q", self.branch)
        (self.source / "manual.nix").write_text("concurrent fix\n")
        self.git(self.source, "add", "manual.nix")
        self.git(self.source, "commit", "-qm", "concurrent fix")
        self.git(self.source, "push", "-q", "origin", self.branch)
        concurrent_commit = self.git(self.source, "rev-parse", "HEAD")
        (self.runner / "new.nix").write_text("new update\n")
        self.git(self.runner, "add", "new.nix")
        self.git(self.runner, "commit", "-qm", "new update")
        result = self.push_update()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git(self.root, "--git-dir", str(self.remote), "rev-parse", self.branch), concurrent_commit)

    def test_new_branch_is_pushed_before_creating_pr(self):
        self.clone()
        self.assertEqual(self.prepare("false").returncode, 0)
        (self.runner / "new.nix").write_text("new update\n")
        self.git(self.runner, "add", "new.nix")
        self.git(self.runner, "commit", "-qm", "new update")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text('#!/bin/sh\ngit --git-dir "$REMOTE" show-ref --verify --quiet "refs/heads/$UPDATE_BRANCH" || exit 1\nprintf "%s\\n" "$@" > "$GH_CALL"\n')
        gh.chmod(0o755)
        call = self.root / "gh-call"
        env = self.env | {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "UPDATE_BRANCH": self.branch,
            "BASE_BRANCH": "main",
            "PR_OPEN": "false",
            "GITHUB_REPOSITORY": "test/repo",
            "GH_CALL": str(call),
            "REMOTE": str(self.remote),
        }
        result = subprocess.run(
            ["bash", str(SCRIPT.parent / "push-update-branch.sh")],
            cwd=self.runner, env=env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git(self.root, "--git-dir", str(self.remote), "rev-parse", self.branch), self.git(self.runner, "rev-parse", "HEAD"))
        args = call.read_text().splitlines()
        self.assertEqual(args[:2], ["pr", "create"])
        self.assertIn(self.branch, args)
        self.assertIn("main", args)


if __name__ == "__main__":
    unittest.main()
