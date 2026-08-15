"""
PY_DIV_001 — Division without a zero-guard (Python)
----------------------------------------------------
Detects any binary_operator node whose operator child is "/" or "//"
where the right-hand operand is NOT a numeric literal.  When the
divisor comes from a variable or function call there is no guarantee
it is non-zero.

AST pattern (Python):
  binary_operator
    ├─ <left>
    ├─ "/"  or  "//"    ← operator child text
    └─ <right>          ← flagged when NOT an integer/float literal
"""

from typing import Iterator, List

from ..base_rule import BaseRule
from ..models import CandidateIssue


class PythonDivisionByZero(BaseRule):

    LANGUAGES = ["Python"]

    @property
    def rule_id(self) -> str:
        return "PY_DIV_001"

    @property
    def issue_type(self) -> str:
        return "division_by_zero"

    @property
    def severity(self) -> str:
        return "high"

    # Node types that represent safe, non-zero literals in most contexts
    _LITERAL_TYPES = {"integer", "float"}

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        for node in self._walk(ast):
            if node["type"] != "binary_operator":
                continue

            children = node.get("children", [])
            if len(children) < 3:
                continue

            operator_node = children[1]
            if operator_node.get("text", "") not in ("/", "//"):
                continue

            right_node = children[2]

            # Safe: a plain numeric literal (e.g. `x / 2`)
            if right_node["type"] in self._LITERAL_TYPES:
                continue

            # Safe: a unary minus applied to a literal (e.g. `x / -1`)
            if (
                right_node["type"] == "unary_operator"
                and right_node.get("children", [{}])[-1]["type"] in self._LITERAL_TYPES
            ):
                continue

            right_text = right_node.get("text", "?")
            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"Division by potentially zero value: the divisor `{right_text}` "
                    f"is not a numeric literal.  Add a zero-guard before dividing."
                ),
                evidence={
                    "operator": operator_node["text"],
                    "right_operand": right_text,
                    "right_node_type": right_node["type"],
                },
            )
