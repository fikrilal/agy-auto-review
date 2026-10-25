import json
import os
import sys
import tempfile
import unittest

# Ensure scripts directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from auto_review_core import (
    clip_text,
    get_project_state,
    parse_envelope,
    parse_verdict,
    turn_has_code_modifications,
)


class TestParsers(unittest.TestCase):
    def test_parse_envelope_valid(self):
        raw = '{"status": "SUCCESS", "response": "VERDICT: APPROVED", "conversation_id": "test-123"}'
        parsed = parse_envelope(raw)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.get("status"), "SUCCESS")
        self.assertEqual(parsed.get("response"), "VERDICT: APPROVED")
        self.assertEqual(parsed.get("conversation_id"), "test-123")

    def test_parse_envelope_noisy_stdout(self):
        raw = """
        Logging system starting...
        Some debug lines
        {"status": "SUCCESS", "response": "Found issues\\nVERDICT: CHANGES_REQUIRED", "conversation_id": "c-456"}
        Extra trailing log line
        """
        parsed = parse_envelope(raw)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.get("conversation_id"), "c-456")
        self.assertIn("CHANGES_REQUIRED", parsed.get("response", ""))

    def test_parse_envelope_invalid(self):
        self.assertIsNone(parse_envelope(""))
        self.assertIsNone(parse_envelope("just plain text without json"))
        self.assertIsNone(parse_envelope("{broken json"))

    def test_parse_verdict_approved(self):
        text = "All verification passed cleanly.\nVERDICT: APPROVED\nEverything looks good."
        verdict = parse_verdict(text)
        self.assertEqual(verdict, "APPROVED")

    def test_parse_verdict_changes_required(self):
        text = "1. test failure in api.go:12\n\nVERDICT: CHANGES_REQUIRED\nFix before commit."
        verdict = parse_verdict(text)
        self.assertEqual(verdict, "CHANGES_REQUIRED")

    def test_parse_verdict_case_insensitive(self):
        text = "verdict: approved"
        self.assertEqual(parse_verdict(text), "APPROVED")

        text = "Verdict: Changes_Required"
        self.assertEqual(parse_verdict(text), "CHANGES_REQUIRED")

    def test_parse_verdict_multiple_uses_last(self):
        text = "Initial thought: VERDICT: CHANGES_REQUIRED\nAfter recheck: VERDICT: APPROVED"
        self.assertEqual(parse_verdict(text), "APPROVED")

    def test_parse_verdict_none(self):
        text = "No verdict found here, just general explanation."
        self.assertIsNone(parse_verdict(text))

    def test_clip_text(self):
        text = "Short text"
        self.assertEqual(clip_text(text, 50), text)

        long_text = "A" * 100
        clipped = clip_text(long_text, 10)
        self.assertTrue(clipped.startswith("A" * 10))
        self.assertIn("…[truncated]", clipped)

    def test_turn_has_code_modifications_pure_chat(self):
        # A turn with user input and only conversational text (zero tools)
        with tempfile.NamedTemporaryFile("w", delete=False) as tf:
            tf.write(json.dumps({"type": "USER_INPUT", "content": "How does this work?"}) + "\n")
            tf.write(json.dumps({"type": "PLANNER_RESPONSE", "content": "Here is an explanation.", "tool_calls": []}) + "\n")
            temp_path = tf.name

        try:
            self.assertFalse(turn_has_code_modifications(temp_path))
        finally:
            os.remove(temp_path)

    def test_turn_has_code_modifications_readonly_tools(self):
        # A turn where agent only calls read_file
        with tempfile.NamedTemporaryFile("w", delete=False) as tf:
            tf.write(json.dumps({"type": "USER_INPUT", "content": "Can you check line 10?"}) + "\n")
            tf.write(json.dumps({"type": "PLANNER_RESPONSE", "tool_calls": [{"name": "read_file"}]}) + "\n")
            tf.write(json.dumps({"type": "PLANNER_RESPONSE", "content": "Line 10 contains foo."}) + "\n")
            temp_path = tf.name

        try:
            self.assertFalse(turn_has_code_modifications(temp_path))
        finally:
            os.remove(temp_path)

    def test_turn_has_code_modifications_active_coding(self):
        # A turn where agent calls edit_file
        with tempfile.NamedTemporaryFile("w", delete=False) as tf:
            tf.write(json.dumps({"type": "USER_INPUT", "content": "Fix the bug"}) + "\n")
            tf.write(json.dumps({"type": "PLANNER_RESPONSE", "tool_calls": [{"name": "edit_file"}]}) + "\n")
            temp_path = tf.name

        try:
            self.assertTrue(turn_has_code_modifications(temp_path))
        finally:
            os.remove(temp_path)

    def test_get_project_state_isolation(self):
        state = {}
        proj1 = get_project_state(state, "/repo/awwabi")
        proj2 = get_project_state(state, "/repo/kevly")

        proj1["lastReviewedFingerprint"] = "hash-awwabi"
        proj2["lastReviewedFingerprint"] = "hash-kevly"

        self.assertNotEqual(proj1["lastReviewedFingerprint"], proj2["lastReviewedFingerprint"])
        self.assertEqual(state["projects"]["/repo/awwabi"]["lastReviewedFingerprint"], "hash-awwabi")
        self.assertEqual(state["projects"]["/repo/kevly"]["lastReviewedFingerprint"], "hash-kevly")


if __name__ == "__main__":
    unittest.main()
