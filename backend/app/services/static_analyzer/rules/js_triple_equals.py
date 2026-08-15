"""
JS_EQ_001 — Use of == instead of === (JavaScript)
--------------------------------------------------
Detects binary_expression nodes that use the loose equality operator
`==` or `!=`.  JavaScript's type coercion rules make these operators
produce surprising results (e.g. `0 == false` is true).

AST pattern (JavaScript):
  binary_expression
    └─ "=="  or  "!="   ← operator child
"""

from typing import Iterator, List

from ..base_rule import BaseRule
from ..models import CandidateIssue

_LOOSE_OPS = {"==", "!="}


class JavaScriptTripleEquals(BaseRule):

    LANGUAGES = ["JavaScript"]

    @property
    def rule_id(self) -> str:
        return "JS_EQ_001"

    @property
    def issue_type(self) -> str:
        return "loose_equality"

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
            if node["type"] != "binary_expression":
                continue

            children = node.get("children", [])
            if len(children) < 3:
                continue

            operator_node = children[1]
            op_text = operator_node.get("text", "")
            if op_text not in _LOOSE_OPS:
                continue

            strict = "===" if op_text == "==" else "!=="
            yield self._make_issue(
                node=operator_node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"Loose equality operator `{op_text}` performs type coercion "
                    f"and can produce unexpected results.  "
                    f"Use `{strict}` for strict equality."
                ),
                evidence={
                    "operator": op_text,
                    "strict_alternative": strict,
                    "expression": node.get("text", "?"),
                },
            )
