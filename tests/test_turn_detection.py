import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from auto_review_core import (
    is_readonly_shell_command,
    turn_has_code_modifications,
    capture_workspace,
    get_project_state,
)


class TestTurnDetection(unittest.TestCase):
    def test_readonly_shell_commands(self):
        valid_readonly = [
            "git status",
            "git log -n 5 --oneline",
            "git diff HEAD",
            "git -C /home/user/project status --porcelain=v1 -uall",
            "git --no-pager branch -a",
            "git rev-parse HEAD",
            "git show 1e74944",
            "git ls-files",
            "ls -la scripts/",
            "pwd",
            "cat /etc/hosts",
            "head -n 20 main.py",
            "tail -f log.txt",
            "grep -rn 'foo' src/",
            "find . -maxdepth 4 -name 'barberlog-backend' 2>/dev/null",
            "echo 'diagnostic note'",
            "node -v",
            "go version",
            "python3 --version",
            "cargo --version",
            "cat file.json | jq .name",
            "git status 2>/dev/null",
            "git status >/dev/null 2>&1",
            "env",
            "env -i",
            "env FOO=bar BAZ=1",
            "env FOO=1 git status",
            "find . -name '*.py'",
            "find src/ -type f",
        ]
        for cmd in valid_readonly:
            with self.subTest(cmd=cmd):
                self.assertTrue(is_readonly_shell_command(cmd), f"Expected readonly: {cmd}")

    def test_modifying_shell_commands(self):
        modifying_commands = [
            "git commit -m 'feat'",
            "git checkout -b new-branch",
            "git switch main",
            "git add .",
            "git reset --hard HEAD~1",
            "git pull origin main",
            "git push origin main",
            "rm -rf /tmp/foo",
            "mkdir -p src/components",
            "touch newfile.txt",
            "echo 'data' > output.txt",
            "echo 'data' >> output.txt",
            "ls | tee listing.txt",
            "npm test",
            "go test ./...",
            "make build",
            "mvn clean install",
            "cargo test",
            "python3 script.py",
            "env python3 modify.py",
            "env npm test",
            "find . -name '*.tmp' -delete",
            "find . -name '*.tmp' -exec rm {} +",
            "find . -execdir rm {} \\;",
        ]
        for cmd in modifying_commands:
            with self.subTest(cmd=cmd):
                self.assertFalse(is_readonly_shell_command(cmd), f"Expected modifying: {cmd}")

    def test_turn_has_code_modifications_with_chat_only(self):
        # A turn where the user asked a question and the model answered with pure text
        steps = [
            {"type": "USER_INPUT", "content": "How does the backup system work?"},
            {"type": "PLANNER_RESPONSE", "content": "The backup system works by taking a SQLite snapshot..."},
        ]
        temp_dir = tempfile.mkdtemp(prefix="agy_trans_")
        try:
            trans_file = os.path.join(temp_dir, "transcript.jsonl")
            with open(trans_file, "w", encoding="utf-8") as f:
                for s in steps:
                    f.write(json.dumps(s) + "\n")

            self.assertFalse(turn_has_code_modifications(trans_file))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_turn_has_code_modifications_with_readonly_tools(self):
        # Turn where model used read_file and run_command with git status
        steps = [
            {"type": "USER_INPUT", "content": "Are there any uncommitted changes?"},
            {
                "type": "PLANNER_RESPONSE",
                "tool_calls": [
                    {"name": "read_file", "args": {"Path": "/repo/README.md"}},
                    {"name": "run_command", "args": {"CommandLine": "git status --porcelain"}},
                ],
            },
            {"type": "PLANNER_RESPONSE", "content": "No, everything is clean."},
        ]
        temp_dir = tempfile.mkdtemp(prefix="agy_trans_")
        try:
            trans_file = os.path.join(temp_dir, "transcript.jsonl")
            with open(trans_file, "w", encoding="utf-8") as f:
                for s in steps:
                    f.write(json.dumps(s) + "\n")

            self.assertFalse(turn_has_code_modifications(trans_file))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_turn_has_code_modifications_with_modifying_tool(self):
        # Turn where model edited a file
        steps = [
            {"type": "USER_INPUT", "content": "Fix the bug in main.py"},
            {
                "type": "PLANNER_RESPONSE",
                "tool_calls": [
                    {"name": "edit_file", "args": {"Path": "/repo/main.py", "Replacement": "pass"}},
                ],
            },
            {"type": "PLANNER_RESPONSE", "content": "I fixed the bug."},
        ]
        temp_dir = tempfile.mkdtemp(prefix="agy_trans_")
        try:
            trans_file = os.path.join(temp_dir, "transcript.jsonl")
            with open(trans_file, "w", encoding="utf-8") as f:
                for s in steps:
                    f.write(json.dumps(s) + "\n")

            self.assertTrue(turn_has_code_modifications(trans_file))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_turn_has_code_modifications_with_modifying_command(self):
        # Turn where model ran a build command that could modify artifacts
        steps = [
            {"type": "USER_INPUT", "content": "Run tests"},
            {
                "type": "PLANNER_RESPONSE",
                "tool_calls": [
                    {"name": "run_command", "args": {"CommandLine": "npm test"}},
                ],
            },
        ]
        temp_dir = tempfile.mkdtemp(prefix="agy_trans_")
        try:
            trans_file = os.path.join(temp_dir, "transcript.jsonl")
            with open(trans_file, "w", encoding="utf-8") as f:
                for s in steps:
                    f.write(json.dumps(s) + "\n")

            self.assertTrue(turn_has_code_modifications(trans_file))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
