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
    get_installed_version,
    fetch_latest_remote_version,
    check_for_update,
    perform_update,
)


class TestUpdate(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="agy_update_test_")
        self.version_file = os.path.join(self.test_dir, ".version")
        self.state_file = os.path.join(self.test_dir, "auto-review.json")

        self.orig_version_file = auto_review_core.VERSION_FILE
        self.orig_state_file = auto_review_core.STATE_FILE

        auto_review_core.VERSION_FILE = self.version_file
        auto_review_core.STATE_FILE = self.state_file

    def tearDown(self):
        auto_review_core.VERSION_FILE = self.orig_version_file
        auto_review_core.STATE_FILE = self.orig_state_file
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_get_installed_version_missing(self):
        self.assertEqual(get_installed_version(), "unknown")

    def test_get_installed_version_exists(self):
        with open(self.version_file, "w", encoding="utf-8") as f:
            f.write("abcdef1234567890\n")
        self.assertEqual(get_installed_version(), "abcdef1234567890")

    @patch("urllib.request.urlopen")
    def test_fetch_latest_remote_version_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"sha": "1234567890abcdef"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        sha = fetch_latest_remote_version()
        self.assertEqual(sha, "1234567890abcdef")

    @patch("urllib.request.urlopen")
    def test_fetch_latest_remote_version_network_error(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Connection refused")
        sha = fetch_latest_remote_version()
        self.assertIsNone(sha)

    @patch("auto_review_core.fetch_latest_remote_version")
    def test_check_for_update_available(self, mock_fetch):
        with open(self.version_file, "w", encoding="utf-8") as f:
            f.write("old_sha_111\n")
        mock_fetch.return_value = "new_sha_222"

        avail, local_v, remote_v = check_for_update(force=True)
        self.assertTrue(avail)
        self.assertEqual(local_v, "old_sha_111")
        self.assertEqual(remote_v, "new_sha_222")

    @patch("auto_review_core.fetch_latest_remote_version")
    def test_check_for_update_already_latest(self, mock_fetch):
        with open(self.version_file, "w", encoding="utf-8") as f:
            f.write("same_sha\n")
        mock_fetch.return_value = "same_sha"

        avail, local_v, remote_v = check_for_update(force=True)
        self.assertFalse(avail)
        self.assertEqual(local_v, "same_sha")
        self.assertEqual(remote_v, "same_sha")

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_perform_update_success(self, mock_run, mock_popen):
        # Mock curl and tar Popen
        p1 = MagicMock()
        p1.stdout = MagicMock()
        p2 = MagicMock()
        p2.communicate.return_value = (b"", b"")
        p2.returncode = 0
        mock_popen.side_effect = [p1, p2]

        # Mock install.sh run
        mock_run.return_value = MagicMock(returncode=0, stdout="Installed ok", stderr="")

        # Create dummy install.sh in temp dir mock
        with patch("tempfile.TemporaryDirectory") as mock_tmp:
            dummy_dir = os.path.join(self.test_dir, "fake_extract")
            os.makedirs(dummy_dir, exist_ok=True)
            with open(os.path.join(dummy_dir, "install.sh"), "w") as f:
                f.write("#!/bin/bash\nexit 0\n")
            mock_tmp.return_value.__enter__.return_value = dummy_dir

            with open(self.version_file, "w", encoding="utf-8") as f:
                f.write("updated_commit_sha\n")

            ok, msg = perform_update()
            self.assertTrue(ok)
            self.assertIn("Successfully updated", msg)


if __name__ == "__main__":
    unittest.main()
