import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import auto_review_core
from auto_review_core import (
    clean_reviewer_summaries,
    deindex_conversation,
    run_reviewer_turn,
)


class TestDeindexAndCleanup(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="agy_deindex_test_")
        self.db1 = os.path.join(self.test_dir, "db1.db")
        self.db2 = os.path.join(self.test_dir, "db2.db")

        # Create mock conversation_summaries databases
        for db in (self.db1, self.db2):
            conn = sqlite3.connect(db)
            c = conn.cursor()
            c.execute("""
                CREATE TABLE conversation_summaries (
                    conversation_id text PRIMARY KEY,
                    title text NOT NULL DEFAULT "",
                    preview text NOT NULL DEFAULT "",
                    step_count integer NOT NULL DEFAULT 0,
                    app_data_dir text NOT NULL DEFAULT ""
                )
            """)
            try:
                c.execute("""
                    CREATE VIRTUAL TABLE conversations_fts USING fts5(
                        conversation_id UNINDEXED,
                        title
                    )
                """)
            except Exception:
                pass
            conn.commit()
            conn.close()

        self.orig_db_paths = auto_review_core.SUMMARY_DB_PATHS
        auto_review_core.SUMMARY_DB_PATHS = [self.db1, self.db2]

    def tearDown(self):
        auto_review_core.SUMMARY_DB_PATHS = self.orig_db_paths
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _insert_summary(self, db_path, cid, title, preview):
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute(
            "INSERT INTO conversation_summaries (conversation_id, title, preview) VALUES (?, ?, ?)",
            (cid, title, preview),
        )
        try:
            c.execute(
                "INSERT INTO conversations_fts (conversation_id, title) VALUES (?, ?)",
                (cid, title),
            )
        except Exception:
            pass
        conn.commit()
        conn.close()

    def test_deindex_conversation(self):
        # Insert target conversation and another legitimate user conversation
        self._insert_summary(self.db1, "conv-review-1", "", "You are the automated reviewer session...")
        self._insert_summary(self.db1, "conv-user-1", "My Feature Coding", "Can you build this?")
        self._insert_summary(self.db2, "conv-review-1", "", "You are the automated reviewer session...")

        deindex_conversation("conv-review-1")

        for db in (self.db1, self.db2):
            conn = sqlite3.connect(db)
            c = conn.cursor()
            c.execute("SELECT conversation_id FROM conversation_summaries WHERE conversation_id = 'conv-review-1'")
            self.assertEqual(c.fetchall(), [])
            conn.close()

        # Ensure legitimate user conversation is untouched
        conn = sqlite3.connect(self.db1)
        c = conn.cursor()
        c.execute("SELECT conversation_id FROM conversation_summaries WHERE conversation_id = 'conv-user-1'")
        self.assertEqual(len(c.fetchall()), 1)
        conn.close()

    def test_clean_reviewer_summaries(self):
        # Insert multiple reviewer entries across both databases
        self._insert_summary(self.db1, "rev-1", "", "You are the automated reviewer session for the uncommitted changes...")
        self._insert_summary(self.db1, "rev-2", "Code Review and Verification", "You are the automated reviewer session...")
        self._insert_summary(self.db1, "user-real-1", "Feature Auth Implementation", "Let's implement OAuth")
        self._insert_summary(self.db2, "rev-3", "", "You are the automated reviewer session for the uncommitted changes...")
        self._insert_summary(self.db2, "user-real-2", "Bug Fix in Engine", "Fixing segfault")

        removed = clean_reviewer_summaries()
        self.assertEqual(removed, 3)

        # Verify only user conversations remain
        conn = sqlite3.connect(self.db1)
        c = conn.cursor()
        c.execute("SELECT conversation_id, title FROM conversation_summaries")
        rows = c.fetchall()
        self.assertEqual(rows, [("user-real-1", "Feature Auth Implementation")])
        conn.close()

        conn = sqlite3.connect(self.db2)
        c = conn.cursor()
        c.execute("SELECT conversation_id, title FROM conversation_summaries")
        rows = c.fetchall()
        self.assertEqual(rows, [("user-real-2", "Bug Fix in Engine")])
        conn.close()

    def test_deindex_handles_missing_or_corrupt_db(self):
        auto_review_core.SUMMARY_DB_PATHS = ["/non/existent/path/db.sqlite"]
        # Must not raise exception
        try:
            deindex_conversation("some-id")
            removed = clean_reviewer_summaries()
            self.assertEqual(removed, 0)
        except Exception as e:
            self.fail(f"deindex raised unexpected exception on missing db: {e}")

    @patch("subprocess.run")
    def test_run_reviewer_turn_triggers_deindex(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"response": "VERDICT: APPROVED\\nNo findings.", "conversation_id": "conv-auto-deindex-test"}',
            stderr="",
        )

        self._insert_summary(self.db1, "conv-auto-deindex-test", "", "You are the automated reviewer session...")

        res = run_reviewer_turn(
            repo_root="/dummy",
            round_number=1,
            existing_convo_id=None,
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["verdict"], "APPROVED")
        self.assertEqual(res["conversationId"], "conv-auto-deindex-test")

        # Verify it was automatically de-indexed from conversation_summaries
        conn = sqlite3.connect(self.db1)
        c = conn.cursor()
        c.execute("SELECT conversation_id FROM conversation_summaries WHERE conversation_id = 'conv-auto-deindex-test'")
        self.assertEqual(c.fetchall(), [])
        conn.close()


if __name__ == "__main__":
    unittest.main()
