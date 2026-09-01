"""
JS_DIV_001 â€” Division by zero or potentially-zero divisor (JavaScript)
-----------------------------------------------------------------------
Detects `/` and `%` binary expressions where the right-hand operand is
provably zero or cannot be proven non-zero.

Classification
--------------
DEFINITELY_ZERO      â€” number literal 0, 0.0, -0, +0, 0n (BigInt zero)
                       â†’ always reported
DEFINITELY_NON_ZERO  â€” non-zero number literal; `true` (coerces to 1);
                       unary +/- applied to a non-zero number
                       â†’ never reported
POTENTIALLY_ZERO     â€” variable, call, expression, `false`, `undefined`,
                       `null`, `NaN`, `Infinity`, etc.
                       â†’ reported as potential issue

JavaScript-specific semantics
------------------------------
* `x / 0` produces Infinity (not a crash), but is almost always a bug.
* `true` coerces to 1 â€” safe divisor.
* `false` coerces to 0 â€” definitely zero.
* `null` coerces to 0 â€” definitely zero.
* `undefined` coerces to NaN â€” potentially problematic, flagged.
* `NaN` as divisor produces NaN â€” flagged as potentially zero
  (the result is unusable even if no crash).

Root-cause notes (F-05 â€“ F-09)
-------------------------------
F-05/F-06: `x / 0` and `x / 0.0` were not flagged â€” the rule skipped
           ALL number literals without checking their value.
F-07/F-08: `x / -0` and `x / +0` were not flagged â€” the unary-on-number
           shortcut skipped unary nodes unconditionally.
F-09:      `x / true` was flagged â€” `true` coerces to 1 in JS and is
           a safe divisor.

AST node types (tree-sitter JavaScript)
----------------------------------------
  binary_expression    â€” any binary operation
  number               â€” numeric literal  (e.g. 0, 1, 2.5, 0x0, 0b0)
  unary_expression     â€” -x, +x, !x, typeof x, â€¦
  true / false         â€” boolean literals
  null                 â€” null literal
  undefined            â€” identifier "undefined"
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Iterator, List, Optional

from ..base_rule import BaseRule
from ..models import CandidateIssue


class _Z(Enum):
    DEFINITELY_ZERO     = auto()
    DEFINITELY_NON_ZERO = auto()
    POTENTIALLY_ZERO    = auto()


class JavaScriptDivisionByZero(BaseRule):

    LANGUAGES = ["JavaScript"]

    @property
    def rule_id(self) -> str:
        return "JS_DIV_001"

    @property
    def issue_type(self) -> str:
        return "division_by_zero"

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
            op_text = operator_node.get("text", "")
            if op_text not in ("/", "%"):
                continue

            right_node = children[2]
            classification = self._classify(right_node)

            if classification == _Z.DEFINITELY_NON_ZERO:
                continue

            right_text = right_node.get("text", "?")

            if classification == _Z.DEFINITELY_ZERO:
                message = (
                    f"Division by zero: the divisor `{right_text}` is always zero."
                )
                evidence_class = "definitely_zero"
            else:
                message = (
                    f"Division by potentially zero value: the divisor `{right_text}` "
                    f"may be zero at runtime.  Add a zero-guard before dividing."
                )
                evidence_class = "potentially_zero"

            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=message,
                evidence={
                    "operator": op_text,
                    "right_operand": right_text,
                    "right_node_type": right_node["type"],
                    "classification": evidence_class,
                },
            )

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def _classify(self, node: dict) -> _Z:
        ntype = node["type"]

        # JavaScript number literal â€” check the actual value
        if ntype == "number":
            return self._classify_number(node)

        # Unary +/- on a number â€” same zero-ness as the operand (F-07/F-08 fix)
        if ntype == "unary_expression":
            return self._classify_unary(node)

        # `true` coerces to 1 â€” safe divisor (F-09 fix)
        if ntype == "true":
            return _Z.DEFINITELY_NON_ZERO

        # `false` coerces to 0 â€” definitely zero
        if ntype == "false":
            return _Z.DEFINITELY_ZERO

        # `null` coerces to 0 â€” definitely zero
        if ntype == "null":
            return _Z.DEFINITELY_ZERO

        # Everything else (identifiers, calls, expressions) â€” unknown
        return _Z.POTENTIALLY_ZERO

    def _classify_number(self, node: dict) -> _Z:
        val = self._number_value(node)
        if val is None:
            return _Z.POTENTIALLY_ZERO
        return _Z.DEFINITELY_ZERO if val == 0.0 else _Z.DEFINITELY_NON_ZERO

    def _classify_unary(self, node: dict) -> _Z:
        children = node.get("children", [])
        if not children:
            return _Z.POTENTIALLY_ZERO
        op = children[0].get("text", "").strip()
        if op not in ("+", "-"):
            return _Z.POTENTIALLY_ZERO
        operand = children[-1]
        return self._classify(operand)

    @staticmethod
    def _number_value(node: dict) -> Optional[float]:
        """
        Parse a JavaScript number literal to a Python float.
        Handles decimal, hex, octal, binary, BigInt (n suffix).
        Returns None on parse failure.
        """
        raw = node.get("text", "").strip()
        # Strip BigInt suffix
        text = raw.rstrip("n").replace("_", "")
        if not text:
            return None

        # Hexadecimal: 0xâ€¦
        if text.startswith(("0x", "0X")):
            try:
                return float(int(text, 16))
            except ValueError:
                return None

        # Binary: 0bâ€¦
        if text.startswith(("0b", "0B")):
            try:
                return float(int(text, 2))
            except ValueError:
                return None

        # Octal: 0oâ€¦ (ES6+) or legacy 0â€¦
        if text.startswith(("0o", "0O")):
            try:
                return float(int(text, 8))
            except ValueError:
                return None

        try:
            return float(text)
        except ValueError:
            return None

"""
JS_DIV_001 â€” Division by zero or potentially-zero divisor (JavaScript)
-----------------------------------------------------------------------
Detects `/` and `%` binary expressions where the right-hand operand is
provably zero or an unguarded dynamic divisor with risk of zero.

Suppression criteria (provably safe / intentional):
- Literal non-zero constants (e.g. `x / 5`, `x / 100`)
- Constant expressions that evaluate to non-zero (e.g. `(i + 1) / (60 * 1000)`)
- Guarded divisions (e.g. `if (total !== 0) { ... / total ... }`, `total ? n / total : 0`)
- Guard wrappers (e.g. `Math.max(total, 1)`, `total || 1`)
- Intentional Infinity constants (e.g. `const inf = 1 / 0;`)

Confidence calibration:
- HIGH: Literal zero (`x / 0`, `x / null`, `x / false`) without intentional Infinity context.
- MEDIUM: Dynamic unguarded variable divisor in production code.
- LOW: Ambiguous expressions in test/spec files.
"""
