"""
JAVA_DIV_001 — Division without a zero-guard (Java)
----------------------------------------------------
Detects binary_expression nodes whose operator is "/" or "%"
where the right-hand operand is NOT an integer/decimal literal.

Java AST pattern (tree-sitter):
  binary_expression
    ├─ <left>
    ├─ "/"  or  "%"
    └─ <right>    ← flagged when NOT decimal_integer_literal / decimal_floating_point_literal
"""

from typing import Iterator, List

from ..base_rule import BaseRule
from ..models import CandidateIssue


class JavaDivisionByZero(BaseRule):

    LANGUAGES = ["Java"]

    @property
    def rule_id(self) -> str:
        return "JAVA_DIV_001"

    @property
    def issue_type(self) -> str:
        return "division_by_zero"

    @property
    def severity(self) -> str:
        return "high"

    _LITERAL_TYPES = {
        "decimal_integer_literal",
        "decimal_floating_point_literal",
        "hex_integer_literal",
        "octal_integer_literal",
        "binary_integer_literal",
        "integer_literal",
        "floating_point_literal",
    }

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
            if operator_node.get("text", "") not in ("/", "%"):
                continue

            right_node = children[2]
            if right_node["type"] in self._LITERAL_TYPES:
                continue

            right_text = right_node.get("text", "?")
            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"Division by potentially zero value: the divisor `{right_text}` "
                    f"is not a numeric literal. Add a zero-guard before dividing."
                ),
                evidence={
                    "operator": operator_node["text"],
                    "right_operand": right_text,
                    "right_node_type": right_node["type"],
                },
            )
