"""
JAVA_LOOP_001 — while(true) without a break or return (Java)
-------------------------------------------------------------
Detects while_statement nodes whose condition is the literal `true`
and whose body block contains no break_statement or return_statement
at the top level of the loop body.

Java AST pattern (tree-sitter):
  while_statement
    ├─ "while"
    ├─ parenthesized_expression
    │    └─ true              ← condition is the boolean literal true
    └─ block
         └─ ... (no break_statement or return_statement at top level)
"""

from typing import Iterator, List

from ..base_rule import BaseRule
from ..models import CandidateIssue

_EXIT_TYPES = {"break_statement", "return_statement", "throw_statement"}


class JavaInfiniteLoop(BaseRule):

    LANGUAGES = ["Java"]

    @property
    def rule_id(self) -> str:
        return "JAVA_LOOP_001"

    @property
    def issue_type(self) -> str:
        return "infinite_loop"

    @property
    def severity(self) -> str:
        return "medium"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        for node in self._walk(ast):
            if node["type"] != "while_statement":
                continue

            children = node.get("children", [])

            # Find condition: parenthesized_expression directly inside while
            condition = next(
                (c for c in children if c["type"] == "parenthesized_expression"),
                None,
            )
            if condition is None:
                continue

            # Condition must be the single literal `true`
            inner = condition.get("children", [])
            true_nodes = [c for c in inner if c["type"] == "true"]
            if not true_nodes:
                continue

            # Find the loop body block
            body = next(
                (c for c in children if c["type"] == "block"),
                None,
            )
            if body is None:
                continue

            # Check recursively through the block for any exit paths
            if self._has_exit(body):
                continue

            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    "`while (true)` loop with no break, return, or throw at the "
                    "top level of its body. This loop may run forever. Add an "
                    "explicit exit condition."
                ),
                evidence={
                    "loop_body_statement_types": sorted(
                        {c["type"] for c in body.get("children", [])}
                    ),
                },
            )

    # ------------------------------------------------------------------
    def _has_exit(self, node: dict) -> bool:
        """Return True if any descendant of node is a break/return/throw."""
        if node["type"] in _EXIT_TYPES:
            return True
        # Don't cross into nested loop/function boundaries
        if node["type"] in (
            "for_statement", "while_statement", "do_statement",
            "enhanced_for_statement", "lambda_expression",
        ):
            return False
        return any(self._has_exit(c) for c in node.get("children", []))
