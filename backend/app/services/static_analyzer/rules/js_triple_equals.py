"""
JS_EQ_001 — Use of == instead of === (JavaScript)
--------------------------------------------------
Detects binary_expression nodes that use the loose equality operators
`==` or `!=`.  JavaScript's type coercion rules make these operators
produce surprising and inconsistent results (e.g. `0 == false` is true,
`"" == false` is true, etc.).

Intentional exemptions
-----------------------
Two patterns use `==` / `!=` intentionally and correctly in JavaScript:

1. `x == null`  (or `null == x`)
   This is a well-known JS idiom that catches both `null` and `undefined`
   in a single expression.  The equivalent strict check would be
   `x === null || x === undefined`.  Many style guides permit `== null`.

2. `typeof x == 'string'`  (or with any typeof operand on either side)
   `typeof` always returns a string, so `==` and `===` are equivalent.
   Flagging this creates noise without adding safety.

Root-cause notes (F-18, F-19)
-------------------------------
F-18: `x == null` was flagged even though this is an intentional JS idiom.
F-19: `typeof x == 'string'` was flagged even though typeof always
      returns a string, making == and === equivalent here.

AST node types (tree-sitter JavaScript)
----------------------------------------
  binary_expression   — binary operation
  null                — null literal
  undefined           — identifier "undefined"
  unary_expression    — typeof x, void x, !x, …
"""

from typing import Iterator, List

from ..base_rule import BaseRule
from ..models import CandidateIssue

_LOOSE_OPS = {"==", "!="}


def _is_null_or_undefined(node: dict) -> bool:
    """
    Return True for the `null` literal or the `undefined` identifier.
    These are the operands of the `x == null` idiom.

    tree-sitter JavaScript uses node type "null" for the null keyword.
    Some older grammar versions or harness helpers may emit "null_literal".
    """
    if node["type"] in ("null", "null_literal"):
        return True
    if node.get("text", "") == "null":
        return True
    if node["type"] == "identifier" and node.get("text", "") == "undefined":
        return True
    return False


def _is_typeof_expression(node: dict) -> bool:
    """Return True when the node is a `typeof <expr>` unary expression."""
    if node["type"] != "unary_expression":
        return False
    children = node.get("children", [])
    return bool(children) and children[0].get("text", "") == "typeof"


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

            left, right = children[0], children[2]

            # Exemption 1: x == null  /  null == x  (F-18 fix)
            # This is the canonical JS idiom for catching null + undefined.
            if _is_null_or_undefined(left) or _is_null_or_undefined(right):
                continue

            # Exemption 2: typeof x == 'string'  (F-19 fix)
            # typeof always returns a string; == and === are equivalent here.
            if _is_typeof_expression(left) or _is_typeof_expression(right):
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
