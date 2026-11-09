import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from auto_review_core import capture_workspace, save_state, load_state, STATE_FILE


class TestHookGating(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="agy_hook_test_")
        self.state_dir = tempfile.mkdtemp(prefix="agy_state_test_")
        self.state_file = os.path.join(self.state_dir, "auto-review.json")
        os.environ["AGY_REVIEW_STATE_FILE"] = self.state_file

        # Init git repo
        subprocess.run(["git", "init"], cwd=self.test_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.test_dir, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.test_dir, check=True)

        self.readme = os.path.join(self.test_dir, "README.md")
        with open(self.readme, "w", encoding="utf-8") as f:
            f.write("# Hello\n")
        subprocess.run(["git", "add", "README.md"], cwd=self.test_dir, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=self.test_dir, check=True)

    def tearDown(self):
        os.environ.pop("AGY_REVIEW_STATE_FILE", None)
        shutil.rmtree(self.test_dir, ignore_errors=True)
        shutil.rmtree(self.state_dir, ignore_errors=True)

    def run_hook(self, payload: dict) -> dict:
        hook_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "review_hook.py"))
        env = dict(os.environ)
        env["AGY_REVIEW_STATE_FILE"] = self.state_file
        proc = subprocess.run(
            [sys.executable, hook_path],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=self.test_dir,
            env=env,
        )
        try:
            return json.loads(proc.stdout.strip())
        except Exception:
            return {"raw": proc.stdout, "err": proc.stderr, "code": proc.returncode}

    def test_clean_tree_allows_stop(self):
        state = {
            "enabled": True,
            "mode": "loop",
            "projects": {}
        }
        with open(self.state_file, "w") as f:
            json.dump(state, f)

        payload = {
            "terminationReason": "NO_TOOL_CALL",
            "workspacePaths": [self.test_dir],
        }
        res = self.run_hook(payload)
        self.assertEqual(res.get("decision"), "allow")

    def test_approved_fingerprint_allows_stop(self):
        # Make dirty change
        with open(self.readme, "a") as f:
            f.write("change\n")
        snapshot = capture_workspace(self.test_dir)
        fp = snapshot["fingerprint"]

        # Store approvedFingerprint
        state = {
            "enabled": True,
            "mode": "loop",
            "projects": {
                self.test_dir: {
                    "approvedFingerprint": fp,
                    "lastVerdict": "APPROVED",
                }
            }
        }
        with open(self.state_file, "w") as f:
            json.dump(state, f)

        payload = {
            "terminationReason": "NO_TOOL_CALL",
            "workspacePaths": [self.test_dir],
        }
        res = self.run_hook(payload)
        self.assertEqual(res.get("decision"), "allow")

    def test_unchanged_working_tree_fingerprint_allows_stop(self):
        # Make dirty change
        with open(self.readme, "a") as f:
            f.write("change 2\n")
        snapshot = capture_workspace(self.test_dir)
        fp = snapshot["fingerprint"]

        # Store lastObservedFingerprint
        state = {
            "enabled": True,
            "mode": "loop",
            "projects": {
                self.test_dir: {
                    "lastObservedFingerprint": fp,
                    "lastReviewedFingerprint": fp,
                }
            }
        }
        with open(self.state_file, "w") as f:
            json.dump(state, f)

        payload = {
            "terminationReason": "NO_TOOL_CALL",
            "workspacePaths": [self.test_dir],
        }
        res = self.run_hook(payload)
        self.assertEqual(res.get("decision"), "allow")


if __name__ == "__main__":
    unittest.main()
