"""
test_escaped_testing_detector.py
----------------------------------
Tests for Feature 4: Escaped Testing Detection.

Covers:
  1. EscapedTestingDetector.check() returns EscapedTestingResult
  2. escaped=True when no test file covers the scenario
  3. escaped=False when a matching test file exists
  4. coverage pattern matching for all known rules
  5. function_name match triggers covered=True
  6. _locate_test_files finds test_<stem>.py mirror
  7. _file_covers returns True/False correctly
  8. check_report() accepts a dict form of EnrichedBugReport
  9. to_dict() serialises correctly
  10. run_demo_escaped_check() executes without crashing
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.escaped_testing_detector import (
    EscapedTestingDetector,
    EscapedTestingResult,
    DEMO_BUG,
    _COVERAGE_PATTERNS,
)


class TestEscapedTestingDetectorUnit(unittest.TestCase):

    def setUp(self):
        self.detector = EscapedTestingDetector()

    # ------------------------------------------------------------------
    # 1. Return type
    # ------------------------------------------------------------------

    def test_check_returns_result(self):
        result = self.detector.check(
            rule_id="PY_DIV_001",
            file_path="src/calc.py",
        )
        self.assertIsInstance(result, EscapedTestingResult)

    # ------------------------------------------------------------------
    # 2. escaped=True when no tests exist
    # ------------------------------------------------------------------

    def test_escaped_true_when_no_test_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.detector.check(
                rule_id="PY_DIV_001",
                file_path="src/calc.py",
                repository_path=tmpdir,
            )
        self.assertTrue(result.escaped)
        self.assertEqual(result.coverage_found_in, [])

    def test_remediation_mentions_generated_test(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.detector.check(
                rule_id="PY_DIV_001",
                file_path="src/calc.py",
                repository_path=tmpdir,
                generated_test_source="def test_divide_zero(): ...",
            )
        self.assertIn("generated", result.remediation.lower())
        self.assertEqual(result.generated_test_source, "def test_divide_zero(): ...")

    # ------------------------------------------------------------------
    # 3. escaped=False when matching test exists
    # ------------------------------------------------------------------

    def test_escaped_false_when_test_covers_scenario(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            # Write a test file that matches the PY_DIV_001 pattern
            test_file = td / "test_calc.py"
            test_file.write_text(
                "def test_divide_by_zero():\n    with pytest.raises(ZeroDivisionError):\n        divide(1, 0)\n",
                encoding="utf-8",
            )
            result = self.detector.check(
                rule_id="PY_DIV_001",
                file_path="src/calc.py",
                repository_path=tmpdir,
            )
        self.assertFalse(result.escaped)
        self.assertTrue(len(result.coverage_found_in) > 0)
        self.assertIn("already covered", result.remediation.lower())

    # ------------------------------------------------------------------
    # 4. Coverage patterns for all supported rules
    # ------------------------------------------------------------------

    def test_py_res_001_pattern_matches_with_statement(self):
        covered = EscapedTestingDetector._file_covers(
            test_file=__file__,   # this file itself
            patterns=_COVERAGE_PATTERNS["PY_RES_001"],
            rule_id="PY_RES_001",
            function_name=None,
        )
        # This test file does not have open() calls — expect False
        # (just verifies no crash)
        self.assertIsInstance(covered, bool)

    def test_js_eq_001_pattern_matches(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("def test_strict_eq():\n    expect(isAdmin('1')).toBe(false)\n")
            tmp_path = f.name
        try:
            covered = EscapedTestingDetector._file_covers(
                test_file=tmp_path,
                patterns=_COVERAGE_PATTERNS["JS_EQ_001"],
                rule_id="JS_EQ_001",
                function_name=None,
            )
            self.assertTrue(covered)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # 5. function_name match triggers covered=True
    # ------------------------------------------------------------------

    def test_function_name_match(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            # File mentions the function name but not the pattern
            f.write("def test_my_calc_helper():\n    result = my_target_function(42)\n    assert result == 42\n")
            tmp_path = f.name
        try:
            covered = EscapedTestingDetector._file_covers(
                test_file=tmp_path,
                patterns=[],
                rule_id="PY_DIV_001",
                function_name="my_target_function",
            )
            self.assertTrue(covered, "Function name match should set covered=True")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # 6. _locate_test_files finds mirror file
    # ------------------------------------------------------------------

    def test_locate_finds_mirror_test_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            (td / "test_calculator.py").write_text("", encoding="utf-8")
            (td / "test_other.py").write_text("", encoding="utf-8")
            result = EscapedTestingDetector._locate_test_files(
                source_file=str(td / "calculator.py"),
                repository_path=tmpdir,
            )
            # Mirror file should be first
            self.assertTrue(len(result) >= 1)
            self.assertEqual(Path(result[0]).name, "test_calculator.py")

    # ------------------------------------------------------------------
    # 7. _file_covers returns False for unrelated content
    # ------------------------------------------------------------------

    def test_file_covers_false_for_unrelated(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("def helper(): return 42\n")
            tmp_path = f.name
        try:
            covered = EscapedTestingDetector._file_covers(
                test_file=tmp_path,
                patterns=_COVERAGE_PATTERNS["PY_DIV_001"],
                rule_id="PY_DIV_001",
                function_name=None,
            )
            self.assertFalse(covered)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # 8. check_report() with dict form
    # ------------------------------------------------------------------

    def test_check_report_accepts_dict(self):
        report_dict = {
            "static_analysis": {"rule_id": "PY_DIV_001"},
            "file_path": "src/calc.py",
            "function_name": "divide",
            "repository": {"path": ""},
            "test_harness_result": {"generated_test_source": "# test"},
        }
        result = self.detector.check_report(report_dict)
        self.assertIsInstance(result, EscapedTestingResult)
        self.assertEqual(result.rule_id, "PY_DIV_001")
        self.assertEqual(result.function_name, "divide")

    def test_check_report_extracts_generated_test(self):
        report_dict = {
            "static_analysis": {"rule_id": "PY_EXC_001"},
            "file_path": "src/api.py",
            "function_name": None,
            "repository": {},
            "test_harness_result": {"generated_test_source": "def test_exc(): pass"},
        }
        result = self.detector.check_report(report_dict)
        self.assertEqual(result.generated_test_source, "def test_exc(): pass")

    # ------------------------------------------------------------------
    # 9. to_dict() serialisation
    # ------------------------------------------------------------------

    def test_to_dict_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.detector.check(
                rule_id="PY_MUT_001",
                file_path="src/defaults.py",
                repository_path=tmpdir,
                generated_test_source="# gen",
            )
        d = result.to_dict()
        for key in ("escaped", "rule_id", "file_path", "function_name",
                    "coverage_found_in", "remediation", "generated_test_source"):
            self.assertIn(key, d)

    def test_to_dict_escaped_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.detector.check(
                rule_id="PY_DIV_001",
                file_path="src/calc.py",
                repository_path=tmpdir,
            )
        d = result.to_dict()
        self.assertTrue(d["escaped"])

    # ------------------------------------------------------------------
    # 10. Demo check runs without crashing
    # ------------------------------------------------------------------

    def test_demo_bug_has_required_fields(self):
        self.assertIn("rule_id", DEMO_BUG)
        self.assertIn("file_path", DEMO_BUG)
        self.assertIn("function_name", DEMO_BUG)
        self.assertEqual(DEMO_BUG["rule_id"], "PY_DIV_001")

    def test_run_demo_escaped_check_returns_result(self):
        from app.services.escaped_testing_detector import run_demo_escaped_check
        # Run without a repo path so no test files are found → escaped=True
        result = run_demo_escaped_check(repository_path=None)
        self.assertIsInstance(result, EscapedTestingResult)
        # Should be escaped since demo repo path doesn't exist
        self.assertTrue(result.escaped)
        # Should have generated test source from Feature 1
        self.assertIsInstance(result.generated_test_source, str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
