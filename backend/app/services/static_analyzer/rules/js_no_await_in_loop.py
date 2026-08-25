"""
JS_AWA_001 — await inside a loop body (JavaScript)
---------------------------------------------------
Detects await_expression nodes that are direct descendants of a loop
body (for_statement, while_statement, for_in_statement, for_of_statement).
Sequential awaits inside loops process items one-at-a-time instead of
concurrently, causing unnecessary latency.

AST pattern (JavaScript):
  for_statement | while_statement | for_in_statement | for_of_statement
    └─ statement_block
         └─ ... (any depth)
              └─ await_expression   ← flagged
"""

from typing import Iterator, List, Set

from ..base_rule import BaseRule
from ..models import CandidateIssue

_LOOP_TYPES: Set[str] = {
    "for_statement",
    "while_statement",
    "do_statement",
    "for_in_statement",
    "for_of_statement",
}


class JavaScriptNoAwaitInLoop(BaseRule):

    LANGUAGES = ["JavaScript"]

    @property
    def rule_id(self) -> str:
        return "JS_AWA_001"

    @property
    def issue_type(self) -> str:
        return "await_in_loop"

    @property
    def severity(self) -> str:
        return "medium"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        # Build child→parent map for upward traversal
        parent_map: dict = {}
        self._build_parent_map(ast, parent_map)

        for node in self._walk(ast):
            if node["type"] != "await_expression":
                continue

            if not self._inside_loop(node, parent_map):
                continue

            # Don't flag if already inside an async function defined inside
            # the loop — that is intentional nesting, not sequential awaiting
            awaited_text = node.get("text", "await ...")
            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"`await` found inside a loop body.  "
                    f"This processes items sequentially.  "
                    f"Consider collecting promises and using Promise.all() instead."
                ),
                evidence={
                    "await_expression": awaited_text,
                },
            )

    # ------------------------------------------------------------------
    def _build_parent_map(self, node: dict, mapping: dict) -> None:
        for child in node.get("children", []):
            mapping[id(child)] = node
            self._build_parent_map(child, mapping)

    def _inside_loop(self, node: dict, parent_map: dict) -> bool:
        current = node
        while id(current) in parent_map:
            current = parent_map[id(current)]
            if current["type"] in _LOOP_TYPES:
                return True
            # Stop at function/method boundaries — await in a nested async
            # function or class method is its own concern, not sequential
            # awaiting in the outer loop.
            if current["type"] in (
                "function_declaration",
                "function_expression",
                "arrow_function",
                "method_definition",     # F-20 fix: class methods are boundaries
                "generator_function",
                "generator_function_declaration",
            ):
                return False
        return False
