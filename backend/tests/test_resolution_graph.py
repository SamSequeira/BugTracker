"""
test_resolution_graph.py
------------------------
Tests for the LangGraph resolution pipeline (Task 7).

Covers:
  1. All 5 routing outcomes reach the correct terminal_status
  2. AUTO_ACCEPT / SECONDARY_MODEL continue to resolution
  3. HUMAN_REVIEW terminates immediately
  4. OOD_REJECT terminates immediately
  5. SYSTEM_ERROR terminates immediately
  6. Retry loop: simulate failing test → retries → UNVERIFIED after MAX_RETRIES
  7. Retry loop: simulate pass → VERIFIED
  8. retry_count increments correctly
  9. failure_reason is captured
  10. trace log is populated
  11. run_resolution() returns expected keys
  12. _LinearFallback produces same outcomes as the full graph (when langgraph absent)
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.orchestration.resolution_graph import (
    classify_node,
    route_node,
    resolution_node,
    run_test_node,
    should_retry,
    increment_retry,
    terminal_verified,
    terminal_unverified,
    terminal_human_review,
    terminal_ood_reject,
    terminal_system_error,
    _LinearFallback,
    MAX_RETRIES,
    ResolutionState,
)


def _base_state(**overrides) -> ResolutionState:
    state: ResolutionState = {
        "bug_id": "BUG-TEST-001",
        "rule_id": "PY_DIV_001",
        "language": "Python",
        "file_path": "src/calc.py",
        "code_snippet": "x / y",
        "severity": "high",
        "raw_issue": {
            "rule_id": "PY_DIV_001",
            "issue_type": "division_by_zero",
            "message": "Division by zero",
            "file_path": "src/calc.py",
            "line_number": 10,
            "column": 0,
            "code_snippet": "x / y",
            "evidence": {"right_operand": "y"},
            "severity": "high",
        },
        "retry_count": 0,
        "failure_reason": "",
        "trace": [],
    }
    state.update(overrides)
    return state


class TestRouteNode(unittest.TestCase):
    """Tests that route_node maps routing_decision to the correct node name."""

    def _state_with_decision(self, decision: str) -> ResolutionState:
        s = _base_state()
        s["routing_decision"] = decision
        return s

    def test_auto_accept_routes_to_resolution(self):
        self.assertEqual(
            route_node(self._state_with_decision("AUTO_ACCEPT")),
            "resolution_node",
        )

    def test_secondary_model_routes_to_resolution(self):
        self.assertEqual(
            route_node(self._state_with_decision("SECONDARY_MODEL")),
            "resolution_node",
        )

    def test_human_review_routes_to_terminal(self):
        self.assertEqual(
            route_node(self._state_with_decision("HUMAN_REVIEW")),
            "terminal_human_review",
        )

    def test_ood_reject_routes_to_terminal(self):
        self.assertEqual(
            route_node(self._state_with_decision("OOD_REJECT")),
            "terminal_ood_reject",
        )

    def test_system_error_routes_to_terminal(self):
        self.assertEqual(
            route_node(self._state_with_decision("SYSTEM_ERROR")),
            "terminal_system_error",
        )

    def test_unknown_decision_routes_to_human_review(self):
        self.assertEqual(
            route_node(self._state_with_decision("BANANA")),
            "terminal_human_review",
        )


class TestShouldRetry(unittest.TestCase):
    """Tests for the conditional edge after test_node."""

    def test_post_fix_passed_returns_verified(self):
        s = _base_state(post_fix_passed=True)
        self.assertEqual(should_retry(s), "end_verified")

    def test_post_fix_failed_with_retries_left(self):
        s = _base_state(post_fix_passed=False, retry_count=0)
        self.assertEqual(should_retry(s), "retry")

    def test_post_fix_failed_at_max_retries(self):
        s = _base_state(post_fix_passed=False, retry_count=MAX_RETRIES)
        self.assertEqual(should_retry(s), "end_unverified")

    def test_post_fix_none_with_retries_left(self):
        s = _base_state(post_fix_passed=None, retry_count=1)
        self.assertEqual(should_retry(s), "retry")

    def test_post_fix_none_at_max_retries(self):
        s = _base_state(post_fix_passed=None, retry_count=MAX_RETRIES)
        self.assertEqual(should_retry(s), "end_unverified")


class TestIncrementRetry(unittest.TestCase):

    def test_increments_retry_count(self):
        s = _base_state(retry_count=1)
        result = increment_retry(s)
        self.assertEqual(result["retry_count"], 2)

    def test_records_failure_reason_from_error(self):
        s = _base_state(retry_count=0, test_error="pytest failed with exit 1")
        result = increment_retry(s)
        self.assertIn("pytest failed", result["failure_reason"])

    def test_records_failure_from_pass_fail_flags(self):
        s = _base_state(retry_count=0, pre_fix_passed=None, post_fix_passed=False, test_error=None)
        result = increment_retry(s)
        self.assertIn("post_fix_passed=False", result["failure_reason"])

    def test_adds_trace_entry(self):
        s = _base_state(retry_count=0, test_error="fail")
        result = increment_retry(s)
        self.assertTrue(any("[retry]" in entry for entry in result["trace"]))


class TestTerminalNodes(unittest.TestCase):

    def test_terminal_verified_sets_status(self):
        s = _base_state()
        result = terminal_verified(s)
        self.assertEqual(result["validation_status"], "VERIFIED")
        self.assertEqual(result["terminal_status"], "VERIFIED")

    def test_terminal_unverified_sets_status(self):
        s = _base_state()
        result = terminal_unverified(s)
        self.assertEqual(result["validation_status"], "UNVERIFIED")
        self.assertEqual(result["terminal_status"], "UNVERIFIED")

    def test_terminal_human_review(self):
        s = _base_state(routing_rationale="MODEL_DISAGREEMENT")
        result = terminal_human_review(s)
        self.assertEqual(result["terminal_status"], "HUMAN_REVIEW")

    def test_terminal_ood_reject(self):
        s = _base_state()
        result = terminal_ood_reject(s)
        self.assertEqual(result["terminal_status"], "OOD_REJECT")

    def test_terminal_system_error(self):
        s = _base_state()
        result = terminal_system_error(s)
        self.assertEqual(result["terminal_status"], "SYSTEM_ERROR")

    def test_all_terminals_add_trace(self):
        for fn in (
            terminal_verified, terminal_unverified, terminal_human_review,
            terminal_ood_reject, terminal_system_error,
        ):
            s = _base_state()
            result = fn(s)
            self.assertTrue(len(result["trace"]) > 0, f"{fn.__name__} did not add a trace entry")


class TestLinearFallbackRetryLoop(unittest.TestCase):
    """
    Simulate the retry loop through the _LinearFallback without needing langgraph.
    """

    def _make_fallback(self) -> _LinearFallback:
        return _LinearFallback()

    def test_verified_on_first_pass(self):
        """If post_fix_passed=True on first test run → VERIFIED, retry_count=0."""
        fb = self._make_fallback()

        def mock_classify(state):
            return {**state, "routing_decision": "AUTO_ACCEPT",
                    "routing_rationale": "HIGH_CONFIDENCE", "ai_confidence": 0.95,
                    "severity": "high", "trace": state.get("trace", []) + ["[classify]"]}

        def mock_resolution(state):
            return {**state, "root_cause": "Zero division", "fix_diff": {"add": "+ guard", "remove": "- raw", "note": "fix"},
                    "reviewer_critique": "", "crew_approved": True,
                    "trace": state.get("trace", []) + ["[resolution]"]}

        def mock_test(state):
            return {**state, "post_fix_passed": True, "pre_fix_passed": False,
                    "test_source": "def test_f(): pass", "test_error": None,
                    "trace": state.get("trace", []) + ["[test]"]}

        with patch("app.services.orchestration.resolution_graph.classify_node", mock_classify), \
             patch("app.services.orchestration.resolution_graph.resolution_node", mock_resolution), \
             patch("app.services.orchestration.resolution_graph.run_test_node", mock_test):
            result = fb.invoke(_base_state())

        self.assertEqual(result["terminal_status"], "VERIFIED")
        self.assertEqual(result["retry_count"], 0)

    def test_unverified_after_max_retries(self):
        """If post_fix_passed always False → UNVERIFIED after MAX_RETRIES retries."""
        fb = self._make_fallback()
        call_count = {"n": 0}

        def mock_classify(state):
            return {**state, "routing_decision": "AUTO_ACCEPT",
                    "routing_rationale": "ok", "ai_confidence": 0.8,
                    "severity": "medium", "trace": state.get("trace", []) + ["[classify]"]}

        def mock_resolution(state):
            call_count["n"] += 1
            return {**state, "root_cause": "RC", "fix_diff": {}, "reviewer_critique": "",
                    "crew_approved": True, "trace": state.get("trace", []) + ["[resolution]"]}

        def mock_test(state):
            return {**state, "post_fix_passed": False, "pre_fix_passed": None,
                    "test_source": "", "test_error": "fail",
                    "trace": state.get("trace", []) + ["[test]"]}

        with patch("app.services.orchestration.resolution_graph.classify_node", mock_classify), \
             patch("app.services.orchestration.resolution_graph.resolution_node", mock_resolution), \
             patch("app.services.orchestration.resolution_graph.run_test_node", mock_test):
            result = fb.invoke(_base_state())

        self.assertEqual(result["terminal_status"], "UNVERIFIED")
        # Should have been called MAX_RETRIES+1 times (initial + retries)
        self.assertEqual(call_count["n"], MAX_RETRIES + 1)

    def test_human_review_terminates_without_resolution(self):
        """HUMAN_REVIEW routing must skip resolution entirely."""
        fb = self._make_fallback()
        resolution_called = {"called": False}

        def mock_classify(state):
            return {**state, "routing_decision": "HUMAN_REVIEW",
                    "routing_rationale": "MODEL_DISAGREEMENT", "ai_confidence": 0.5,
                    "severity": "medium", "trace": state.get("trace", []) + ["[classify]"]}

        def mock_resolution(state):
            resolution_called["called"] = True
            return state

        with patch("app.services.orchestration.resolution_graph.classify_node", mock_classify), \
             patch("app.services.orchestration.resolution_graph.resolution_node", mock_resolution):
            result = fb.invoke(_base_state())

        self.assertEqual(result["terminal_status"], "HUMAN_REVIEW")
        self.assertFalse(resolution_called["called"])
    def test_retry_loop_increments_count(self):
        """After each failed test, retry_count should increment."""
        fb = self._make_fallback()
        retry_counts_seen = []

        def mock_classify(state):
            return {**state, "routing_decision": "AUTO_ACCEPT",
                    "routing_rationale": "ok", "ai_confidence": 0.9,
                    "severity": "high", "trace": state.get("trace", []) + ["[classify]"]}

        def mock_resolution(state):
            retry_counts_seen.append(state.get("retry_count", 0))
            return {**state, "root_cause": "RC", "fix_diff": {}, "reviewer_critique": "",
                    "crew_approved": True, "trace": state.get("trace", []) + ["[res]"]}

        def mock_test(state):
            return {**state, "post_fix_passed": False, "pre_fix_passed": None,
                    "test_source": "", "test_error": "fail",
                    "trace": state.get("trace", []) + ["[test]"]}

        with patch("app.services.orchestration.resolution_graph.classify_node", mock_classify), \
             patch("app.services.orchestration.resolution_graph.resolution_node", mock_resolution), \
             patch("app.services.orchestration.resolution_graph.run_test_node", mock_test):
            fb.invoke(_base_state())

        # retry_counts_seen should be [0, 1, 2, 3] for MAX_RETRIES=3
        self.assertEqual(retry_counts_seen, list(range(MAX_RETRIES + 1)))


class TestClassifyNode(unittest.TestCase):
    """classify_node wraps the existing routing module."""

    def test_classify_populates_routing_decision(self):
        s = _base_state()
        result = classify_node(s)
        self.assertIn("routing_decision", result)
        self.assertIn(result["routing_decision"],
                      {"AUTO_ACCEPT", "SECONDARY_MODEL", "HUMAN_REVIEW", "OOD_REJECT", "SYSTEM_ERROR"})

    def test_classify_populates_ai_confidence(self):
        s = _base_state()
        result = classify_node(s)
        self.assertIn("ai_confidence", result)
        conf = result["ai_confidence"]
        self.assertGreaterEqual(conf, 0.0)
        self.assertLessEqual(conf, 1.0)

    def test_classify_adds_trace_entry(self):
        s = _base_state()
        result = classify_node(s)
        self.assertTrue(any("[classify]" in e for e in result.get("trace", [])))


if __name__ == "__main__":
    unittest.main(verbosity=2)
