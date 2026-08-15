"""
PY_RES_001 — open() called outside a with-statement (Python)
-------------------------------------------------------------
Detects calls to the builtin open() that are NOT inside a
with_statement.  Files opened this way may leak handles when an
exception is raised before .close() is called.

AST pattern (Python):
  assignment  OR  expression_statement
    └─ call
         └─ identifier  text="open"

The rule checks the ancestor chain: if none of the ancestors of the
call node is a "with_statement", the call is flagged.
"""

from typing import Iterator, List

from ..base_rule import BaseRule
from ..models import CandidateIssue


class PythonUnclosedResource(BaseRule):

    LANGUAGES = ["Python"]

    @property
    def rule_id(self) -> str:
        return "PY_RES_001"

    @property
    def issue_type(self) -> str:
        return "unclosed_resource"

    @property
    def severity(self) -> str:
        return "high"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        # Build a child→parent map so we can walk upward
        parent_map: dict = {}
        self._build_parent_map(ast, parent_map)

        for node in self._walk(ast):
            if node["type"] != "call":
                continue

            children = node.get("children", [])
            if not children:
                continue

            # The function being called must be the bare identifier "open"
            func_node = children[0]
            if func_node["type"] != "identifier":
                continue
            if func_node.get("text", "") != "open":
                continue

            # Walk ancestors — safe if any is a with_statement
            if self._inside_with(node, parent_map):
                continue

            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    "open() called outside a `with` statement.  "
                    "Use `with open(...) as f:` to guarantee the file is "
                    "closed even when an exception occurs."
                ),
                evidence={"call_text": node.get("text", "open(...)")},
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_parent_map(self, node: dict, mapping: dict) -> None:
        for child in node.get("children", []):
            mapping[id(child)] = node
            self._build_parent_map(child, mapping)

    def _inside_with(self, node: dict, parent_map: dict) -> bool:
        current = node
        while id(current) in parent_map:
            current = parent_map[id(current)]
            if current["type"] == "with_statement":
                return True
        return False
