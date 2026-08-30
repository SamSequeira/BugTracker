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

"""
JS_EQ_001 — Use of == instead of === (JavaScript)
--------------------------------------------------
Detects binary_expression nodes that use the loose equality operators
`==` or `!=`. JavaScript's implicit type coercion rules make loose
equality produce surprising results (e.g. `0 == false`, `"" == false`,
`"0" == 0`).

Suppression criteria (provably safe / intentional):
- Idiomatic null/undefined checks: `x == null`, `null == x`, `x == undefined`, `x == void 0`
- `typeof x == 'string'` (typeof always returns string; `==` and `===` are identical)
- Same literal types: `"a" == "b"`, `1 == 2`, `true == false`

Confidence calibration:
- HIGH: Cross-type coercion hazard (e.g. `string == boolean`, `number == boolean`, `string == number`).
- MEDIUM: Variable compared to primitive literal with loose equality.
- LOW: Ambiguous variable-to-variable loose equality.
"""

from typing import Iterator, List, Optional, Tuple

from ..base_rule import BaseRule
from ..models import CandidateIssue

_LOOSE_OPS = {"==", "!="}


def _is_null_or_undefined(node: dict) -> bool:
    ntype = node.get("type", "")
    text = (node.get("text") or "").strip()
    if ntype in ("null", "null_literal") or text == "null":
        return True
    if ntype == "identifier" and text == "undefined":
        return True
    if ntype == "unary_expression" and text in ("void 0", "void(0)"):
        return True
    return False


def _is_typeof_expression(node: dict) -> bool:
    if node.get("type") != "unary_expression":
        return False
    children = node.get("children", [])
    return bool(children) and (children[0].get("text") or "").strip() == "typeof"


def _infer_js_type(node: dict) -> str:
    """Infer basic literal/expression type in JavaScript AST."""
    ntype = node.get("type", "")
    text = (node.get("text") or "").strip()

    if ntype in ("string", "string_fragment", "template_string"):
        return "string"
    if ntype == "number":
        return "number"
    if ntype in ("true", "false", "boolean_literal"):
        return "boolean"
    if ntype in ("null", "null_literal") or text == "null":
        return "null"
    if ntype == "identifier" and text == "undefined":
        return "undefined"
    if ntype == "unary_expression" and _is_typeof_expression(node):
        return "string"
    if ntype == "array":
        return "array"
    if ntype == "object":
        return "object"
    if ntype == "identifier":
        lower = text.lower()
        if lower.startswith("is") or lower.startswith("has") or lower.startswith("should"):
            return "boolean"
        if lower.endswith("count") or lower.endswith("index") or lower.endswith("length") or lower.endswith("size"):
            return "number"
        if lower.endswith("name") or lower.endswith("str") or lower.endswith("id") or lower.endswith("url"):
            return "string"
    return "unknown"


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
            if node.get("type") != "binary_expression":
                continue

            children = node.get("children", [])
            if len(children) < 3:
                continue

            operator_node = children[1]
            op_text = (operator_node.get("text") or "").strip()
            if op_text not in _LOOSE_OPS:
                continue

            self.record_syntax_match()

            left, right = children[0], children[2]

            # 1. Intentional null/undefined check idiom
            if _is_null_or_undefined(left) or _is_null_or_undefined(right):
                self.record_suppression("null_undefined_check_idiom")
                continue

            # 2. typeof always returns string
            if _is_typeof_expression(left) or _is_typeof_expression(right):
                self.record_suppression("typeof_comparison")
                continue

            left_type = _infer_js_type(left)
            right_type = _infer_js_type(right)

            # 3. Same literal types (e.g. "a" == "b", 1 == 2, true == true)
            if left_type == right_type and left_type in ("string", "number", "boolean"):
                # Both are identical static primitive types -> stylistic but low-risk
                self.record_suppression(f"same_primitive_type_{left_type}")
                continue

            strict = "===" if op_text == "==" else "!=="
            left_text = (left.get("text") or "?").strip()
            right_text = (right.get("text") or "?").strip()

            # Check cross-type coercion risk
            coercion_risk = "unknown"
            confidence = "low"

            if left_type != "unknown" and right_type != "unknown" and left_type != right_type:
                coercion_risk = f"high ({left_type} coerced with {right_type})"
                confidence = "high"
            elif left_type in ("boolean", "number") or right_type in ("boolean", "number"):
                # Comparing dynamic value against boolean or number literal is high coercion hazard in JS
                coercion_risk = f"high (coercion with {left_type if left_type != 'unknown' else right_type})"
                confidence = "high"
            elif left_type == "string" or right_type == "string":
                coercion_risk = f"moderate ({left_type} vs {right_type})"
                confidence = "medium"


            yield self._make_issue(
                node=node,  # Pass full binary_expression node for complete code snippet
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"Loose equality operator `{op_text}` performs type coercion "
                    f"and can produce unexpected results ({left_type} vs {right_type}). Use `{strict}` instead."
                ),
                evidence={
                    "operator": op_text,
                    "strict_alternative": strict,
                    "left_operand": left_text,
                    "left_type": left_type,
                    "right_operand": right_text,
                    "right_type": right_type,
                    "coercion_risk": coercion_risk,
                    "confidence": confidence,
                    "reason": f"Loose equality between `{left_text}` ({left_type}) and `{right_text}` ({right_type}).",
                },
                confidence=confidence,
            )

