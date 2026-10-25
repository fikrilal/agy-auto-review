import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from auto_review_core import find_review_skills


class TestSkills(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="agy_skills_test_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_find_review_skills_empty(self):
        skills = find_review_skills(self.test_dir)
        self.assertEqual(skills, [])

    def test_find_review_skills_directories(self):
        # Create .agents/skills/review-change/SKILL.md
        skill1_dir = os.path.join(self.test_dir, ".agents", "skills", "review-change")
        os.makedirs(skill1_dir, exist_ok=True)
        with open(os.path.join(skill1_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# Review Change\n")

        # Create .agents/skills/other-skill/SKILL.md
        skill2_dir = os.path.join(self.test_dir, ".agents", "skills", "other-skill")
        os.makedirs(skill2_dir, exist_ok=True)
        with open(os.path.join(skill2_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# Other Skill\n")

        skills = find_review_skills(self.test_dir)
        # Should prioritize skills with 'review' in the name
        self.assertEqual(len(skills), 1)
        self.assertIn(".agents/skills/review-change/SKILL.md", skills)

    def test_find_review_skills_standalone_md(self):
        # Create .commandcode/skills/review-test.md
        skills_dir = os.path.join(self.test_dir, ".commandcode", "skills")
        os.makedirs(skills_dir, exist_ok=True)
        with open(os.path.join(skills_dir, "review-test.md"), "w", encoding="utf-8") as f:
            f.write("# Review Test\n")

        skills = find_review_skills(self.test_dir)
        self.assertEqual(len(skills), 1)
        self.assertIn(".commandcode/skills/review-test.md", skills)


if __name__ == "__main__":
    unittest.main()
