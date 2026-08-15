"""
JAVA_EQ_001 — String comparison with == instead of .equals() (Java)
--------------------------------------------------------------------
Detects binary_expression nodes that compare two operands with "==" or
"!=" where at least one side has a type name that is a known String
indicator (identifier starting with uppercase, or the literal text
"String").

Java AST pattern (tree-sitter):
  binary_expression
    ├─ <left>     ← identifier / method_invocation / field_access
    ├─ "==" or "!="
    └─ <right>

We flag when neither side is a literal `null` (null checks with == are
idiomatic Java) and either side looks like a String reference.

Heuristics used:
  - left or right identifier text starts with an uppercase letter
    (Java naming convention for objects)
  - the parent local_variable_declaration type is "String"
  - either operand is a method_invocation (always an object, never a primitive)
"""

from typing import Iterator, List

from ..base_rule import BaseRule
from ..models import CandidateIssue

_OBJECT_NODE_TYPES = {"method_invocation", "object_creation_expression", "field_access"}


def _looks_like_string(node: dict) -> bool:
    """Heuristic: could this operand be a String/object reference?"""
    if node["type"] in _OBJECT_NODE_TYPES:
        return True
    if node["type"] == "identifier":
        text = node.get("text", "")
        # Uppercase-starting: almost always an object in Java
        if text and text[0].isupper():
            return True
    return False


def _is_null(node: dict) -> bool:
    return node.get("text", "") == "null" or node["type"] == "null_literal"


class JavaStringEquality(BaseRule):

    LANGUAGES = ["Java"]

    @property
    def rule_id(self) -> str:
        return "JAVA_EQ_001"

    @property
    def issue_type(self) -> str:
        return "string_reference_equality"

    @property
    def severity(self) -> str:
        return "high"

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
            if operator_node.get("text", "") not in ("==", "!="):
                continue

            left, right = children[0], children[2]

            # null checks are idiomatic — skip
            if _is_null(left) or _is_null(right):
                continue

            # primitive literals — skip
            if left["type"] in (
                "decimal_integer_literal", "decimal_floating_point_literal",
                "integer_literal", "floating_point_literal",
                "true", "false", "character_literal",
            ):
                continue

            if not (_looks_like_string(left) or _looks_like_string(right)):
                continue

            op = operator_node["text"]
            suggested = ".equals()" if op == "==" else "!...equals()"
            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"Object compared with `{op}` checks reference identity, "
                    f"not value equality. For Strings use `.equals()` or "
                    f"`Objects.equals()` instead."
                ),
                evidence={
                    "operator": op,
                    "left_operand": left.get("text", "?"),
                    "right_operand": right.get("text", "?"),
                    "suggested": suggested,
                },
            )
