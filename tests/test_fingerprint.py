import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from auto_review_core import capture_workspace, ensure_git_exclude, save_review_report


class TestFingerprint(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="agy_review_test_")
        # Initialize a real git repo
        subprocess.run(["git", "init"], cwd=self.test_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.test_dir, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.test_dir, check=True)

        # Initial commit
        self.readme = os.path.join(self.test_dir, "README.md")
        with open(self.readme, "w", encoding="utf-8") as f:
            f.write("# Test Repo\n")
        subprocess.run(["git", "add", "README.md"], cwd=self.test_dir, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=self.test_dir, check=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_clean_working_tree(self):
        snapshot = capture_workspace(self.test_dir)
        self.assertFalse(snapshot["dirty"])
        self.assertIsNotNone(snapshot["fingerprint"])

    def test_tracked_modification_changes_fingerprint(self):
        initial = capture_workspace(self.test_dir)

        # Modify tracked file
        with open(self.readme, "a", encoding="utf-8") as f:
            f.write("A new line\n")

        modified = capture_workspace(self.test_dir)
        self.assertTrue(modified["dirty"])
        self.assertNotEqual(initial["fingerprint"], modified["fingerprint"])

    def test_untracked_file_changes_fingerprint(self):
        initial = capture_workspace(self.test_dir)

        # Create new untracked file
        new_file = os.path.join(self.test_dir, "feature.py")
        with open(new_file, "w", encoding="utf-8") as f:
            f.write("print('hello')\n")

        dirty_snapshot = capture_workspace(self.test_dir)
        self.assertTrue(dirty_snapshot["dirty"])
        self.assertNotEqual(initial["fingerprint"], dirty_snapshot["fingerprint"])

    def test_review_report_excluded_from_fingerprint(self):
        # Create a modified file to make it dirty
        with open(self.readme, "a", encoding="utf-8") as f:
            f.write("feature code\n")

        dirty_snapshot = capture_workspace(self.test_dir)
        self.assertTrue(dirty_snapshot["dirty"])

        # Save review report (which automatically calls ensure_git_exclude)
        report_path = save_review_report(
            repo_root=self.test_dir,
            artifact_dir=None,
            round_number=1,
            verdict="APPROVED",
            text="Clean test run",
            model="test-model",
            effort="high",
            tree_hash=dirty_snapshot["fingerprint"],
        )
        self.assertTrue(os.path.exists(report_path))

        # Re-capture workspace: writing review-latest.md must NOT alter the fingerprint!
        after_report_snapshot = capture_workspace(self.test_dir)
        self.assertEqual(dirty_snapshot["fingerprint"], after_report_snapshot["fingerprint"])

    def test_custom_fingerprint_script(self):
        # Create a mock review-fingerprint.sh
        mods_dir = os.path.join(self.test_dir, ".commandcode", "mods")
        os.makedirs(mods_dir, exist_ok=True)
        script_path = os.path.join(mods_dir, "review-fingerprint.sh")

        custom_hash = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(f"#!/usr/bin/env bash\necho '{custom_hash}'\nexit 0\n")
        os.chmod(script_path, 0o755)

        snapshot = capture_workspace(self.test_dir)
        self.assertTrue(snapshot["dirty"])
        self.assertEqual(snapshot["fingerprint"], custom_hash)
        self.assertEqual(snapshot["fingerprint_script"], ".commandcode/mods/review-fingerprint.sh")


if __name__ == "__main__":
    unittest.main()
