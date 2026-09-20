"""
base_rule.py
------------
Abstract base class that every analysis rule must implement.

A rule is a self-contained, stateless object that:
  - declares which language(s) it applies to
  - receives the full AST dict and the raw source lines
  - yields zero or more CandidateIssue instances

Adding a new rule means:
  1. Create a subclass of BaseRule in the rules/ directory.
  2. Register it in rules/__init__.py.
  No other file needs to change.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, List, Optional, Set, Union

from .analysis.constant_evaluator import ConstantEvaluator, evaluate_constant
from .models import CandidateIssue
from .severity import normalize_scanner_severity


class BaseRule(ABC):
    """Abstract base for all static analysis rules."""

    # Languages this rule applies to: "Python", "JavaScript", "Java"
    LANGUAGES: List[str] = []

    def __init__(self) -> None:
        self._metrics: Dict[str, Any] = {
            "raw_syntax_matches": 0,
            "suppressed_matches": 0,
            "reported_matches": 0,
            "reported_high": 0,
            "reported_medium": 0,
            "reported_low": 0,
            "suppression_reasons": {},
        }

    def reset_metrics(self) -> None:
        self._metrics = {
            "raw_syntax_matches": 0,
            "suppressed_matches": 0,
            "reported_matches": 0,
            "reported_high": 0,
            "reported_medium": 0,
            "reported_low": 0,
            "suppression_reasons": {},
        }

    def get_metrics(self) -> Dict[str, Any]:
        return dict(self._metrics)

    def record_syntax_match(self) -> None:
        self._metrics["raw_syntax_matches"] += 1

    def record_suppression(self, reason: str) -> None:
        self._metrics["suppressed_matches"] += 1
        reasons = self._metrics["suppression_reasons"]
        reasons[reason] = reasons.get(reason, 0) + 1

    def record_report(self, confidence: str) -> None:
        self._metrics["reported_matches"] += 1
        conf_key = f"reported_{confidence.lower()}"
        if conf_key in self._metrics:
            self._metrics[conf_key] += 1
        else:
            self._metrics["reported_medium"] += 1

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Unique rule identifier, e.g. 'PY_DIV_001'."""

    @property
    @abstractmethod
    def issue_type(self) -> str:
        """Short category label, e.g. 'division_by_zero'."""

    @property
    @abstractmethod
    def severity(self) -> str:
        """'high' | 'medium' | 'low'"""

    @abstractmethod
    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:
        """
        Traverse *ast* and yield a CandidateIssue for every violation found.

        Parameters
        ----------
        ast          : The normalized AST dict produced by ASTGenerator.
        file_path    : Path of the file being analyzed (for issue reporting).
        source_lines : The original source split by line (0-indexed), used
                       to populate code_snippet without re-reading the file.
        """

    # ------------------------------------------------------------------
    # Shared traversal & AST helper utilities
    # ------------------------------------------------------------------

    def _walk(self, node: dict) -> Iterator[dict]:
        """
        Depth-first pre-order traversal of the normalized AST dict.
        Yields every node (including the root).
        """
        yield node
        for child in node.get("children", []):
            yield from self._walk(child)

    def _build_parent_map(self, node: dict, mapping: dict) -> None:
        """Populate mapping from id(child) -> parent node dict."""
        for child in node.get("children", []):
            mapping[id(child)] = node
            self._build_parent_map(child, mapping)

    def _is_test_file(self, file_path: str) -> bool:
        """
        Detect if the file is part of a test suite, fixture directory, or specification.
        Used for contextual evidence calibration, NOT unconditional suppression.
        """
        norm = file_path.replace("\\", "/").lower()
        parts = norm.split("/")
        filename = parts[-1] if parts else ""

        # Directory markers
        test_dirs = {"test", "tests", "testing", "test_cases", "__tests__", "fixtures", "spec", "specs"}
        if any(d in parts[:-1] for d in test_dirs):
            return True

        # File name markers across Python, JS, Java
        if (
            filename.startswith(("test_", "spec_"))
            or filename.endswith(("_test.py", "_spec.py"))
            or filename.endswith(("_test.js", ".test.js", ".spec.js", "_spec.js"))
            or filename.endswith(("_test.java", "testcase.java", "tests.java", "it.java"))
            or (filename.endswith(".java") and re.search(r'(?:^|_)test', filename, re.IGNORECASE))
        ):
            return True

        return False

    def _evaluate_constant_expr(self, node: dict) -> Optional[Union[int, float, bool, str]]:
        """Evaluate constant arithmetic/literal expressions in Java/JS/Python ASTs."""
        return evaluate_constant(node)

    def _snippet(self, node: dict, source_lines: List[str]) -> str:
        """
        Return the source text for *node* using source_lines as a fallback
        when node["text"] is empty or spans multiple lines ambiguously.
        """
        raw_text = node.get("text")
        text = str(raw_text).strip() if raw_text is not None else ""
        if text:
            first_line = text.split("\n")[0].strip()
            return first_line if first_line else text
        # Fallback: pull from source_lines
        start = node.get("start") or {}
        line_idx = start.get("line", 0)
        if 0 <= line_idx < len(source_lines):
            return source_lines[line_idx].rstrip()
        return ""

    def _make_issue(
        self,
        node: dict,
        file_path: str,
        source_lines: List[str],
        message: str,
        evidence: dict,
        confidence: Optional[str] = None,
    ) -> CandidateIssue:
        """Convenience factory — builds a CandidateIssue from a node and records metrics."""
        conf = confidence or evidence.get("confidence", "medium")
        if conf not in ("high", "medium", "low"):
            conf = "medium"
        evidence["confidence"] = conf

        start = node.get("start") or {}
        line_num = start.get("line", 0) + 1
        col_num = start.get("column", 0)

        self.record_report(conf)

        return CandidateIssue(
            rule_id=self.rule_id,
            issue_type=self.issue_type,
            message=message,
            file_path=file_path,
            line_number=line_num,
            column=col_num,
            code_snippet=self._snippet(node, source_lines),
            evidence=evidence,
            severity=normalize_scanner_severity(self.severity),
            confidence=conf,
        )
