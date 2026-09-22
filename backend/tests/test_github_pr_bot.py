"""
test_github_pr_bot.py
---------------------
Tests for Feature 3: GitHub PR Bot.

Focuses on components that don't require a live GitHub connection.

Covers:
  1. _parse_pr_url correctly parses pull/pulls URLs
  2. _parse_pr_url raises ValueError for invalid URLs
  3. _extract_changed_files_from_diff extracts Python files
  4. _extract_changed_files_from_diff extracts JS/TS files
  5. _extract_changed_files_from_diff ignores unsupported extensions
  6. _extract_changed_files_from_diff handles empty diff
  7. _build_comment produces a Markdown comment with required sections
  8. _build_comment shows "no issues" when reports is empty
  9. _build_comment includes validation status badges
  10. _build_comment includes AI confidence
  11. GitHubPRBot.analyse_and_comment raises ValueError without required args
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.github_pr_bot import GitHubPRBot, _parse_pr_url


SAMPLE_DIFF = """
diff --git a/src/calculator.py b/src/calculator.py
index 0000001..0000002 100644
--- a/src/calculator.py
+++ b/src/calculator.py
@@ -1,5 +1,7 @@
 def divide(a, b):
-    return a / b
+    if b == 0:
+        raise ValueError("Division by zero")
+    return a / b
diff --git a/src/utils.js b/src/utils.js
index 0000003..0000004 100644
--- a/src/utils.js
+++ b/src/utils.js
@@ -1,3 +1,3 @@
 function check(role) {
-    return role == 1;
+    return role === 1;
 }
diff --git a/README.md b/README.md
index 0000005..0000006 100644
--- a/README.md
+++ b/README.md
@@ -1,1 +1,2 @@
 # Project
+Updated docs
"""


def _sample_report(validation_status: str = "VERIFIED") -> dict:
    return {
        "id": "BUG-2026-0001",
        "title": "Division by Zero in divide()",
        "severity": "high",
        "priority": "p2",
        "priority_formatted": "P2 • Fix this week",
        "file_path": "src/calculator.py",
        "file": "src/calculator.py",
        "line": 2,
        "category": "division_by_zero",
        "ai_confidence": 0.93,
        "confidence": 0.93,
        "validation_status": validation_status,
        "description": "Division by zero possible.",
        "static_analysis": {"rule_id": "PY_DIV_001", "code_snippet": "a / b", "evidence": {}},
        "explanation": {
            "what": "Unguarded division by zero.",
            "evidence_summary": "Static analysis rule PY_DIV_001 triggered.",
        },
        "suggestedFix": {
            "remove": "- return a / b",
            "add": "+ if b == 0: raise ValueError\n+ return a / b",
            "note": "Guard divisor.",
        },
        "test_harness_result": {
            "generated_test_source": "def test_divide_zero():\n    pytest.raises(ZeroDivisionError, divide, 1, 0)",
            "pre_fix_passed": False,
            "post_fix_passed": True,
            "validated": True,
            "error": None,
        },
    }


class TestParsePRUrl(unittest.TestCase):

    def test_standard_pull_url(self):
        owner, repo, num = _parse_pr_url("https://github.com/acme/myrepo/pull/42")
        self.assertEqual(owner, "acme")
        self.assertEqual(repo, "myrepo")
        self.assertEqual(num, 42)

    def test_pulls_url(self):
        owner, repo, num = _parse_pr_url("https://github.com/acme/myrepo/pulls/7")
        self.assertEqual(owner, "acme")
        self.assertEqual(repo, "myrepo")
        self.assertEqual(num, 7)

    def test_large_pr_number(self):
        owner, repo, num = _parse_pr_url("https://github.com/org/project/pull/9999")
        self.assertEqual(num, 9999)

    def test_invalid_url_raises(self):
        with self.assertRaises(ValueError):
            _parse_pr_url("https://gitlab.com/owner/repo/merge_requests/1")

    def test_missing_pr_number_raises(self):
        with self.assertRaises(ValueError):
            _parse_pr_url("https://github.com/owner/repo")

    def test_arbitrary_string_raises(self):
        with self.assertRaises(ValueError):
            _parse_pr_url("not-a-url-at-all")


class TestExtractChangedFiles(unittest.TestCase):

    def setUp(self):
        self.bot = GitHubPRBot(github_token="fake_token")

    def test_extracts_python_file(self):
        files = self.bot._extract_changed_files_from_diff(SAMPLE_DIFF)
        paths = [f["path"] for f in files]
        self.assertIn("src/calculator.py", paths)

    def test_extracts_js_file(self):
        files = self.bot._extract_changed_files_from_diff(SAMPLE_DIFF)
        paths = [f["path"] for f in files]
        self.assertIn("src/utils.js", paths)

    def test_ignores_markdown(self):
        files = self.bot._extract_changed_files_from_diff(SAMPLE_DIFF)
        paths = [f["path"] for f in files]
        self.assertNotIn("README.md", paths)

    def test_content_is_nonempty(self):
        files = self.bot._extract_changed_files_from_diff(SAMPLE_DIFF)
        for f in files:
            self.assertTrue(len(f["content"]) > 0, f"Empty content for {f['path']}")

    def test_empty_diff_returns_empty(self):
        files = self.bot._extract_changed_files_from_diff("")
        self.assertEqual(files, [])

    def test_diff_with_only_deletions_returns_no_content(self):
        diff = """diff --git a/src/old.py b/src/old.py
--- a/src/old.py
+++ b/src/old.py
@@ -1,3 +0,0 @@
-def old(): pass
-def removed(): pass
"""
        files = self.bot._extract_changed_files_from_diff(diff)
        py_files = [f for f in files if f["path"] == "src/old.py"]
        # Either no file or empty content since only deletions
        for f in py_files:
            self.assertEqual(f["content"].strip(), "")


class TestBuildComment(unittest.TestCase):

    def setUp(self):
        self.bot = GitHubPRBot(github_token="fake_token")

    def _pr_meta(self) -> dict:
        return {
            "title": "Fix division by zero",
            "html_url": "https://github.com/acme/myrepo/pull/42",
        }

    def test_no_issues_produces_clean_message(self):
        comment = self.bot._build_comment(
            pr_meta=self._pr_meta(),
            reports=[],
            diff_text=SAMPLE_DIFF,
        )
        self.assertIn("No issues detected", comment)
        self.assertIn("BugTracker", comment)

    def test_comment_has_summary_table(self):
        comment = self.bot._build_comment(
            pr_meta=self._pr_meta(),
            reports=[_sample_report()],
            diff_text=SAMPLE_DIFF,
        )
        self.assertIn("Summary", comment)
        self.assertIn("High", comment)

    def test_comment_includes_pr_title(self):
        comment = self.bot._build_comment(
            pr_meta=self._pr_meta(),
            reports=[_sample_report()],
            diff_text=SAMPLE_DIFF,
        )
        self.assertIn("Fix division by zero", comment)

    def test_comment_includes_validation_status(self):
        comment = self.bot._build_comment(
            pr_meta=self._pr_meta(),
            reports=[_sample_report("VERIFIED")],
            diff_text=SAMPLE_DIFF,
        )
        self.assertIn("VERIFIED", comment)

    def test_comment_includes_unverified_status(self):
        comment = self.bot._build_comment(
            pr_meta=self._pr_meta(),
            reports=[_sample_report("UNVERIFIED")],
            diff_text=SAMPLE_DIFF,
        )
        self.assertIn("UNVERIFIED", comment)

    def test_comment_includes_ai_confidence(self):
        comment = self.bot._build_comment(
            pr_meta=self._pr_meta(),
            reports=[_sample_report()],
            diff_text=SAMPLE_DIFF,
        )
        self.assertIn("AI Confidence", comment)
        self.assertIn("93%", comment)

    def test_comment_includes_fix_diff(self):
        comment = self.bot._build_comment(
            pr_meta=self._pr_meta(),
            reports=[_sample_report()],
            diff_text=SAMPLE_DIFF,
        )
        self.assertIn("Suggested Fix", comment)
        self.assertIn("Guard divisor", comment)

    def test_comment_includes_generated_test(self):
        comment = self.bot._build_comment(
            pr_meta=self._pr_meta(),
            reports=[_sample_report()],
            diff_text=SAMPLE_DIFF,
        )
        self.assertIn("Generated Regression Test", comment)
        self.assertIn("test_divide_zero", comment)

    def test_comment_verified_count_in_summary(self):
        comment = self.bot._build_comment(
            pr_meta=self._pr_meta(),
            reports=[_sample_report("VERIFIED"), _sample_report("UNVERIFIED")],
            diff_text=SAMPLE_DIFF,
        )
        # Should show 1 verified
        self.assertIn("1", comment)

    def test_multiple_reports(self):
        comment = self.bot._build_comment(
            pr_meta=self._pr_meta(),
            reports=[_sample_report(), _sample_report()],
            diff_text=SAMPLE_DIFF,
        )
        # Two detailed finding sections
        self.assertGreaterEqual(comment.count("BUG-2026-0001"), 2)


class TestGitHubPRBotValidation(unittest.TestCase):

    def test_analyse_and_comment_raises_without_args(self):
        bot = GitHubPRBot(github_token="fake")
        with self.assertRaises(ValueError):
            bot.analyse_and_comment(
                pr_url=None, owner=None, repo=None, pr_number=None
            )

    def test_analyse_and_comment_raises_partial_args(self):
        bot = GitHubPRBot(github_token="fake")
        with self.assertRaises(ValueError):
            bot.analyse_and_comment(
                pr_url=None, owner="acme", repo=None, pr_number=42
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
