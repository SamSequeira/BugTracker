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

import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, List, Optional, Set, Union

from .models import CandidateIssue


class BaseRule(ABC):
    """Abstract base for all static analysis rules."""

    # Languages this rule applies to.  Use the same strings as ASTGenerator:
    # "Python", "JavaScript", "Java"
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
        """'critical' | 'high' | 'medium' | 'low'"""

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
        Detect if the file is part of a test suite or fixture directory.
        Used for contextual evidence calibration, NOT unconditional suppression.
        """
        norm = file_path.replace("\\", "/").lower()
        parts = norm.split("/")
        filename = parts[-1] if parts else ""

        # Directory markers
        test_dirs = {"test", "tests", "testing", "test_cases", "__tests__", "fixtures", "spec", "specs"}
        if any(d in parts[:-1] for d in test_dirs):
            return True

        # File name markers
        if (
            filename.startswith("test_")
            or filename.endswith(("_test.py", "_test.js", ".test.js", ".spec.js", "_spec.js"))
            or filename.endswith(("test.java", "testcase.java", "tests.java", "it.java"))
            or (filename.endswith(".java") and re.search(r'test', filename, re.IGNORECASE))
        ):
            return True

        return False

    def _evaluate_constant_expr(self, node: dict) -> Optional[Union[int, float, bool]]:
        """
        Recursively evaluate constant arithmetic/literal expressions in Java/JS/Python ASTs.
        Returns None if dynamic variables, calls, or unknown operations are encountered.
        """
        if not node or not isinstance(node, dict):
            return None

        ntype = node.get("type", "")
        text = (node.get("text") or "").strip()

        # Numeric literals
        if ntype in (
            "decimal_integer_literal", "hex_integer_literal", "octal_integer_literal",
            "binary_integer_literal", "integer_literal", "integer",
            "decimal_floating_point_literal", "floating_point_literal", "float",
            "number",
        ):
            clean_text = text.rstrip("lLfFdDnN").replace("_", "")
            try:
                if clean_text.startswith(("0x", "0X")):
                    return int(clean_text, 16)
                if clean_text.startswith(("0b", "0B")):
                    return int(clean_text, 2)
                if clean_text.startswith(("0o", "0O")):
                    return int(clean_text, 8)
                if "." in clean_text or "e" in clean_text.lower():
                    return float(clean_text)
                return int(clean_text)
            except Exception:
                return None

        # Boolean literals
        if ntype in ("true", "false", "boolean_literal"):
            return text.lower() == "true"

        # Parenthesized expression: (expr)
        if ntype in ("parenthesized_expression", "parenthesized_expression"):
            children = [c for c in node.get("children", []) if c.get("text", "") not in ("(", ")")]
            if len(children) == 1:
                return self._evaluate_constant_expr(children[0])

        # Unary expression: +expr, -expr
        if ntype in ("unary_expression", "unary_op"):
            children = node.get("children", [])
            if len(children) >= 2:
                op = (children[0].get("text") or "").strip()
                val = self._evaluate_constant_expr(children[-1])
                if val is not None and isinstance(val, (int, float)):
                    if op == "+":
                        return +val
                    if op == "-":
                        return -val

        # Binary expression: left OP right
        if ntype in ("binary_expression", "binary_op"):
            children = node.get("children", [])
            if len(children) >= 3:
                left_val = self._evaluate_constant_expr(children[0])
                op = (children[1].get("text") or "").strip()
                right_val = self._evaluate_constant_expr(children[2])
                if left_val is not None and right_val is not None and isinstance(left_val, (int, float)) and isinstance(right_val, (int, float)):
                    try:
                        if op == "+":
                            return left_val + right_val
                        if op == "-":
                            return left_val - right_val
                        if op == "*":
                            return left_val * right_val
                        if op == "/" and right_val != 0:
                            return left_val / right_val
                        if op == "//" and right_val != 0:
                            return left_val // right_val
                        if op == "%" and right_val != 0:
                            return left_val % right_val
                        if op == "**":
                            return left_val ** right_val
                        if op == "<<" and isinstance(left_val, int) and isinstance(right_val, int):
                            return left_val << right_val
                        if op == ">>" and isinstance(left_val, int) and isinstance(right_val, int):
                            return left_val >> right_val
                    except Exception:
                        return None

        return None

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
            severity=self.severity,
            confidence=conf,
        )

