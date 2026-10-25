import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import auto_review_core
from auto_review_core import (
    load_state,
    save_state,
    rotate_cli_account,
    run_reviewer_turn,
    DEFAULT_MODEL,
    DEFAULT_EFFORT,
    DEFAULT_MAX_REVIEWS,
)


class TestRotationAndState(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="agy_state_test_")
        self.state_file = os.path.join(self.test_dir, "auto-review.json")
        self.orig_state_file = auto_review_core.STATE_FILE
        auto_review_core.STATE_FILE = self.state_file

    def tearDown(self):
        auto_review_core.STATE_FILE = self.orig_state_file
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_load_state_default(self):
        state = load_state()
        self.assertTrue(state.get("enabled"))
        self.assertEqual(state.get("mode"), "loop")
        self.assertEqual(state.get("maxReviews"), DEFAULT_MAX_REVIEWS)
        self.assertEqual(state.get("model"), DEFAULT_MODEL)
        self.assertEqual(state.get("effort"), DEFAULT_EFFORT)

    def test_save_and_load_state(self):
        state = load_state()
        state["reviewCount"] = 5
        state["lastVerdict"] = "APPROVED"
        save_state(state)

        reloaded = load_state()
        self.assertEqual(reloaded["reviewCount"], 5)
        self.assertEqual(reloaded["lastVerdict"], "APPROVED")

    @patch("subprocess.run")
    def test_rotate_cli_account_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "schema_version": 1,
                "command": "rotate",
                "data": {
                    "rotated": True,
                    "account": {"email": "alt-user@example.com"},
                    "reason": "forced"
                }
            }),
            stderr="",
        )

        success, msg = rotate_cli_account()
        self.assertTrue(success)
        self.assertIn("alt-user@example.com", msg)

        # Verify it called agy-auth with --target=cli --force --json
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn("rotate", args)
        self.assertIn("--target=cli", args)
        self.assertIn("--force", args)
        self.assertIn("--json", args)

    @patch("subprocess.run")
    def test_rotate_cli_account_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="no stored accounts have remaining quota",
        )

        success, msg = rotate_cli_account()
        self.assertFalse(success)
        self.assertIn("no stored accounts", msg)

    @patch("auto_review_core.send_desktop_notification")
    @patch("auto_review_core.rotate_cli_account")
    @patch("subprocess.run")
    def test_quota_exhaustion_triggers_rotation_and_retry(self, mock_subproc, mock_rotate, mock_notify):
        # 1. First run fails with quota exhaustion (code 3)
        fail_mock = MagicMock(
            returncode=3,
            stdout="",
            stderr="Antigravity reviewer exited: Your AI credits balance is too low to continue.",
        )
        # 2. Second run (retry on rotated account) succeeds
        success_mock = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "status": "SUCCESS",
                "response": "All good\nVERDICT: APPROVED",
                "conversation_id": "c-rotated"
            }),
            stderr="",
        )
        mock_subproc.side_effect = [fail_mock, success_mock]
        mock_rotate.return_value = (True, "Rotated CLI account to new-acct@example.com")

        result = run_reviewer_turn(
            repo_root=self.test_dir,
            round_number=1,
            existing_convo_id="c-old",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["verdict"], "APPROVED")
        self.assertEqual(result["conversationId"], "c-rotated")
        mock_rotate.assert_called_once()
        mock_notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
