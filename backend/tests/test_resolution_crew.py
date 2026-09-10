"""
test_resolution_crew.py
-----------------------
Tests for the CrewAI resolution crew (Task 8).

Focuses on the direct-tool-fallback path (_run_direct) which is always
available regardless of whether crewai is installed.

Covers:
  1. _tool_build_explanation returns a non-empty string
  2. _tool_generate_fix returns dict with remove/add/note keys
  3. _tool_review_fix approves a valid fix
  4. _tool_review_fix rejects an empty fix
  5. _tool_review_fix rejects an oversized fix
  6. _tool_review_fix rejects a fix that misses expected keywords
  7. run_resolution_crew returns required keys
  8. run_resolution_crew produces a non-empty root_cause
  9. run_resolution_crew produces a fix_diff with at least one non-empty field
  10. prior_failure context is incorporated into crew output
  11. reviewer critique loop: one revision pass on rejection
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.orchestration.resolution_crew import (
    _tool_build_explanation,
    _tool_generate_fix,
    _tool_review_fix,
    _run_direct,
    run_resolution_crew,
)


def _sample_issue(rule_id: str = "PY_DIV_001") -> dict:
    return {
        "rule_id": rule_id,
        "issue_type": "division_by_zero",
        "message": "Potential division by zero",
        "file_path": "src/calc.py",
        "line_number": 10,
        "column": 0,
        "code_snippet": "x / y",
        "evidence": {"right_operand": "y"},
        "severity": "high",
    }


class TestToolBuildExplanation(unittest.TestCase):

    def test_returns_nonempty_string(self):
        result = _tool_build_explanation(
            rule_id="PY_DIV_001",
            language="Python",
            code_snippet="x / y",
            severity="high",
            raw_issue=_sample_issue(),
        )
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_includes_rule_id_on_failure(self):
        # Simulate a broken enrichment service by patching the local import target
        with patch(
            "app.services.bug_enrichment_service.BugEnrichmentService",
            side_effect=RuntimeError("boom"),
        ):
            result = _tool_build_explanation(
                rule_id="PY_DIV_001",
                language="Python",
                code_snippet="x / y",
                severity="high",
                raw_issue={},
            )
        self.assertIn("PY_DIV_001", result)

    def test_works_for_all_python_rules(self):
        for rule_id in ("PY_DIV_001", "PY_RES_001", "PY_EXC_001", "PY_ASS_001", "PY_MUT_001"):
            result = _tool_build_explanation(
                rule_id=rule_id,
                language="Python",
                code_snippet="x / y",
                severity="medium",
                raw_issue=_sample_issue(rule_id),
            )
            self.assertIsInstance(result, str, f"Failed for {rule_id}")
            self.assertTrue(len(result) > 0, f"Empty explanation for {rule_id}")


class TestToolGenerateFix(unittest.TestCase):

    def test_returns_dict_with_required_keys(self):
        result = _tool_generate_fix(
            rule_id="PY_DIV_001",
            issue_type="division_by_zero",
            code_snippet="x / y",
            evidence={"right_operand": "y"},
            language="Python",
        )
        for key in ("remove", "add", "note"):
            self.assertIn(key, result, f"Key '{key}' missing from fix dict")

    def test_py_div_001_add_contains_guard(self):
        result = _tool_generate_fix(
            rule_id="PY_DIV_001",
            issue_type="division_by_zero",
            code_snippet="total / divisor",
            evidence={"right_operand": "divisor"},
            language="Python",
        )
        add = result.get("add", "")
        self.assertIsNotNone(add)
        # Should contain a zero-guard of some form
        self.assertTrue(
            "0" in str(add) or "zero" in str(add).lower(),
            f"Expected zero-guard in add: {add!r}",
        )

    def test_py_res_001_add_contains_with(self):
        result = _tool_generate_fix(
            rule_id="PY_RES_001",
            issue_type="unclosed_resource",
            code_snippet="f = open(path)",
            evidence={},
            language="Python",
        )
        add = result.get("add", "")
        self.assertIn("with", str(add))

    def test_note_is_nonempty_for_known_rules(self):
        for rule_id in ("PY_DIV_001", "PY_RES_001", "PY_EXC_001", "JS_EQ_001"):
            result = _tool_generate_fix(
                rule_id=rule_id,
                issue_type="generic",
                code_snippet="x",
                evidence={},
                language="Python" if rule_id.startswith("PY") else "JavaScript",
            )
            self.assertTrue(len(result.get("note", "")) > 0, f"Empty note for {rule_id}")


class TestToolReviewFix(unittest.TestCase):

    def test_approves_valid_fix(self):
        fix = {
            "remove": "- x / y",
            "add": "+ if y != 0:\n+     return x / y",
            "note": "Guard divisor against zero before division.",
        }
        result = _tool_review_fix("PY_DIV_001", "Division by zero", fix)
        self.assertEqual(result["approved"], "true")
        self.assertEqual(result["critique"], "")

    def test_rejects_empty_fix(self):
        fix = {"remove": "", "add": "", "note": ""}
        result = _tool_review_fix("PY_DIV_001", "Root cause", fix)
        self.assertEqual(result["approved"], "false")
        self.assertIn("empty", result["critique"].lower())

    def test_rejects_oversized_fix(self):
        add_lines = "\n".join(f"+ line {i}" for i in range(25))
        fix = {"remove": "", "add": add_lines, "note": "big"}
        result = _tool_review_fix("PY_DIV_001", "Root cause", fix)
        self.assertEqual(result["approved"], "false")
        self.assertIn("lines", result["critique"].lower())

    def test_rejects_unrelated_fix(self):
        # Fix for PY_DIV_001 that mentions nothing about zero/divisor
        fix = {
            "remove": "- import logging",
            "add": "+ import structlog",
            "note": "Switch to structured logging.",
        }
        result = _tool_review_fix("PY_DIV_001", "Division by zero root cause", fix)
        self.assertEqual(result["approved"], "false")

    def test_js_eq_001_approves_strict_equality(self):
        fix = {
            "remove": "- if (x == 1)",
            "add": "+ if (x === 1)",
            "note": "Use strict equality to avoid type coercion.",
        }
        result = _tool_review_fix("JS_EQ_001", "Loose equality", fix)
        self.assertEqual(result["approved"], "true")


class TestRunResolutionCrew(unittest.TestCase):

    def test_returns_required_keys(self):
        result = run_resolution_crew(
            rule_id="PY_DIV_001",
            language="Python",
            code_snippet="x / y",
            severity="high",
            raw_issue=_sample_issue(),
        )
        for key in ("root_cause", "fix_diff", "reviewer_critique", "approved"):
            self.assertIn(key, result, f"Key '{key}' missing from crew result")

    def test_root_cause_nonempty(self):
        result = run_resolution_crew(
            rule_id="PY_DIV_001",
            language="Python",
            code_snippet="x / y",
            severity="high",
            raw_issue=_sample_issue(),
        )
        self.assertIsInstance(result["root_cause"], str)
        self.assertTrue(len(result["root_cause"]) > 0)

    def test_fix_diff_has_content(self):
        result = run_resolution_crew(
            rule_id="PY_DIV_001",
            language="Python",
            code_snippet="x / y",
            severity="high",
            raw_issue=_sample_issue(),
        )
        fix = result["fix_diff"]
        # At least one of remove/add/note should be non-empty
        content = (fix.get("remove") or "") + (fix.get("add") or "") + (fix.get("note") or "")
        self.assertTrue(len(content) > 0)

    def test_prior_failure_accepted(self):
        # Should not raise even with a prior failure message
        result = run_resolution_crew(
            rule_id="PY_EXC_001",
            language="Python",
            code_snippet="except:",
            severity="medium",
            raw_issue=_sample_issue("PY_EXC_001"),
            prior_failure="Post-fix test failed: test_safe_parse returned None",
        )
        self.assertIn("approved", result)

    def test_works_for_js_rule(self):
        issue = {
            "rule_id": "JS_EQ_001",
            "issue_type": "loose_equality",
            "message": "Use === instead of ==",
            "file_path": "src/auth.js",
            "line_number": 5,
            "column": 0,
            "code_snippet": "if (role == 1)",
            "evidence": {"operator": "=="},
            "severity": "medium",
        }
        result = run_resolution_crew(
            rule_id="JS_EQ_001",
            language="JavaScript",
            code_snippet="if (role == 1)",
            severity="medium",
            raw_issue=issue,
        )
        self.assertIn("fix_diff", result)

    def test_reviewer_critique_loop_one_revision(self):
        """
        When reviewer rejects the first fix, _run_direct should attempt
        one revision and return the second review result.
        """
        call_count = {"review": 0}
        original_review = _tool_review_fix

        def patched_review(rule_id, root_cause, fix_diff):
            call_count["review"] += 1
            if call_count["review"] == 1:
                return {"approved": "false", "critique": "Missing zero-guard keyword"}
            return original_review(rule_id, root_cause, fix_diff)

        with patch(
            "app.services.orchestration.resolution_crew._tool_review_fix",
            patched_review,
        ):
            result = _run_direct(
                rule_id="PY_DIV_001",
                language="Python",
                code_snippet="x / y",
                severity="high",
                raw_issue=_sample_issue(),
                prior_failure=None,
            )

        # Should have called review twice (first rejection + one revision)
        self.assertEqual(call_count["review"], 2)
        # Result must still have required keys
        for key in ("root_cause", "fix_diff", "reviewer_critique", "approved"):
            self.assertIn(key, result)


class TestResolutionTraceExport(unittest.TestCase):
    """Tests for the trace export functions added to report_exporter.py."""

    def _sample_trace_state(self) -> dict:
        return {
            "bug_id": "BUG-2026-0001",
            "terminal_status": "VERIFIED",
            "validation_status": "VERIFIED",
            "ai_confidence": 0.92,
            "routing_decision": "AUTO_ACCEPT",
            "routing_rationale": "HIGH_CONFIDENCE_TRUE_POSITIVE",
            "root_cause": "Division by zero possible when divisor is 0.",
            "fix_diff": {
                "remove": "- x / y",
                "add": "+ if y != 0:\n+     return x / y",
                "note": "Guard before division.",
            },
            "reviewer_critique": "",
            "crew_approved": True,
            "test_source": "def test_div_zero():\n    with pytest.raises(ZeroDivisionError): divide(1, 0)",
            "pre_fix_passed": False,
            "post_fix_passed": True,
            "test_error": None,
            "retry_count": 0,
            "trace": ["[classify] routing=AUTO_ACCEPT", "[resolution]", "[test] validated=True", "[terminal] status=VERIFIED"],
        }

    def test_json_export_has_required_keys(self):
        import json
        from app.services.report_exporter import export_resolution_trace_json
        state = self._sample_trace_state()
        content = export_resolution_trace_json(state)
        data = json.loads(content)
        for key in ("trace_type", "bug_id", "terminal_status", "routing", "resolution", "test_harness", "trace_log"):
            self.assertIn(key, data, f"Key '{key}' missing from JSON trace export")

    def test_json_export_validation_status(self):
        import json
        from app.services.report_exporter import export_resolution_trace_json
        content = export_resolution_trace_json(self._sample_trace_state())
        data = json.loads(content)
        self.assertEqual(data["validation_status"], "VERIFIED")

    def test_markdown_export_contains_sections(self):
        from app.services.report_exporter import export_resolution_trace_markdown
        content = export_resolution_trace_markdown(self._sample_trace_state())
        text = content.decode("utf-8")
        for section in ("Root Cause", "Proposed Fix", "Test Harness", "Routing", "Execution Trace"):
            self.assertIn(section, text, f"Section '{section}' missing from Markdown trace")

    def test_markdown_export_contains_verification(self):
        from app.services.report_exporter import export_resolution_trace_markdown
        content = export_resolution_trace_markdown(self._sample_trace_state())
        text = content.decode("utf-8")
        self.assertIn("VERIFIED", text)

    def test_markdown_export_contains_trace_log(self):
        from app.services.report_exporter import export_resolution_trace_markdown
        content = export_resolution_trace_markdown(self._sample_trace_state())
        text = content.decode("utf-8")
        self.assertIn("[classify]", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
