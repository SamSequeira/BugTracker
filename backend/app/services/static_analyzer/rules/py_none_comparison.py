"""
PY_NONE_001 — Incorrect None Comparison (Python)
-------------------------------------------------
Detects comparison with `None` using `==` or `!=` instead of identity operators `is` or `is not`.
In Python, singletons like `None` should always be checked with identity (`is None`)
because classes can override `__eq__` and produce unexpected truthiness or performance issues.
"""

from __future__ import annotations

from typing import Iterator, List

from ..base_rule import BaseRule
from ..models import CandidateIssue


class PythonNoneComparison(BaseRule):

    LANGUAGES = ["Python"]

    @property
    def rule_id(self) -> str:
        return "PY_NONE_001"

    @property
    def issue_type(self) -> str:
        return "none_equality_comparison"

    @property
    def severity(self) -> str:
        return "low"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        for node in self._walk(ast):
            if node.get("type") != "comparison_operator":
                continue

            children = node.get("children", [])
            if len(children) < 3:
                continue

            # Check if any operator is `==` or `!=`
            ops = [c.get("text", "") for c in children]
            for idx, op in enumerate(ops):
                if op in ("==", "!="):
                    left = children[idx - 1] if idx > 0 else None
                    right = children[idx + 1] if idx + 1 < len(children) else None

                    left_text = (left.get("text") or "").strip() if left else ""
                    right_text = (right.get("text") or "").strip() if right else ""

                    if left_text == "None" or right_text == "None":
                        var_target = right_text if left_text == "None" else left_text
                        rec_op = "is None" if op == "==" else "is not None"
                        snippet = self._snippet(node, source_lines)

                        self.record_syntax_match()
                        yield self._make_issue(
                            node=node,
                            file_path=file_path,
                            source_lines=source_lines,
                            message=f"Comparison with `None` using `{op}`. Use `{var_target} {rec_op}` instead.",
                            evidence={
                                "operator": op,
                                "recommended": rec_op,
                                "expression": snippet,
                                "confidence": "high",
                            },
                            confidence="high",
                        )
