"""
JAVA_DIV_001 — Division by zero or potentially-zero divisor (Java)
-------------------------------------------------------------------
Detects `/` and `%` binary expressions where the right-hand operand is
provably zero or cannot be proven non-zero.
"""

from __future__ import annotations

import re
from enum import Enum, auto
from typing import Iterator, List, Optional

from ..base_rule import BaseRule
from ..models import CandidateIssue


class _Z(Enum):
    DEFINITELY_ZERO     = auto()
    DEFINITELY_NON_ZERO = auto()
    POTENTIALLY_ZERO    = auto()


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

    # All tree-sitter node types that represent Java numeric literals
    _LITERAL_TYPES = {
        "decimal_integer_literal",
        "decimal_floating_point_literal",
        "hex_integer_literal",
        "octal_integer_literal",
        "binary_integer_literal",
        "hex_floating_point_literal",
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
                confidence = "high"
            else:
                message = (
                    f"Division by potentially zero value: the divisor `{right_text}` "
                    f"may be zero at runtime. Add a zero-guard before dividing."
                )
                evidence_class = "potentially_zero"
                confidence = "medium"

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
                    "confidence": confidence,
                },
                confidence=confidence,
            )

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def _classify(self, node: dict) -> _Z:
        # Check constant evaluation first (e.g. 60 * 1000)
        c_val = self._evaluate_constant_expr(node)
        if c_val is not None and isinstance(c_val, (int, float)):
            return _Z.DEFINITELY_ZERO if c_val == 0 else _Z.DEFINITELY_NON_ZERO

        ntype = node.get("type", "")

        # Check Math.max(1, x) or Math.max(x, 1)
        if ntype == "method_invocation":
            text = node.get("text", "")
            if "Math.max" in text or "max(" in text:
                args = [c for c in node.get("children", []) if c.get("type") == "argument_list"]
                if args:
                    for arg in args[0].get("children", []):
                        if arg.get("text", "") not in (",", "(", ")"):
                            val = self._evaluate_constant_expr(arg)
                            if val is not None and isinstance(val, (int, float)) and val >= 1:
                                return _Z.DEFINITELY_NON_ZERO

        # Numeric literal — check its value
        if ntype in self._LITERAL_TYPES:
            return self._classify_literal(node)

        # Unary +/- on a literal: same zero-ness as the operand
        if ntype == "unary_expression":
            return self._classify_unary(node)

        # Parenthesised expression
        if ntype == "parenthesized_expression":
            inner = [c for c in node.get("children", []) if c.get("text", "") not in ("(", ")")]
            if len(inner) == 1:
                return self._classify(inner[0])

        return _Z.POTENTIALLY_ZERO

    def _classify_literal(self, node: dict) -> _Z:
        text = (node.get("text") or "").strip()
        clean = re.sub(r"[lLfFdD_]", "", text).lower()

        if not clean:
            return _Z.POTENTIALLY_ZERO

        try:
            if clean.startswith("0x"):
                val = int(clean, 16)
            elif clean.startswith("0b"):
                val = int(clean, 2)
            elif clean.startswith("0") and len(clean) > 1 and clean.isdigit():
                val = int(clean, 8)
            elif "." in clean or "e" in clean or "p" in clean:
                val = float(clean)
            else:
                val = int(clean)

            return _Z.DEFINITELY_ZERO if val == 0 else _Z.DEFINITELY_NON_ZERO
        except ValueError:
            return None

"""
JAVA_DIV_001 — Division by zero or potentially-zero divisor (Java)
-------------------------------------------------------------------
Detects `/` and `%` binary expressions where the right-hand operand is
provably zero or an unguarded dynamic divisor with risk of zero.

Suppression criteria (provably safe / intentional):
- Literal non-zero constants (e.g. `x / 5`, `x / 60000L`)
- Constant expressions that evaluate to non-zero (e.g. `offset / (60 * 1000)`)
- Built-in non-zero math wrappers (e.g. `Math.max(x, 1)`)
- Guarded divisions (e.g. `if (d != 0) { ... / d ... }` or `d != 0 ? n / d : 0`)

Confidence calibration:
- HIGH: Literal zero (`x / 0`, `x / 0.0`) or constant expression evaluating to 0.
- MEDIUM: Unguarded dynamic variable divisor with potential zero values.
- LOW: Weak risk in test helper or complex context.
"""



import re
from typing import Iterator, List, Optional, Set

from ..base_rule import BaseRule
from ..models import CandidateIssue


def _has_math_max_guard(node: dict) -> bool:
    """Check for Math.max(x, 1) or Math.max(1, x) pattern in divisor."""
    text = (node.get("text") or "").replace(" ", "")
    if re.search(r'Math\.max\([^,]+,[1-9]\d*\)', text) or re.search(r'Math\.max\([1-9]\d*,[^)]+\)', text):
        return True
    return False


def _is_guarded_in_ancestors(node: dict, parent_map: dict, var_name: str) -> bool:
    """
    Check if the division occurs inside an `if` block or ternary with a non-zero guard
    for `var_name`.
    """
    if not var_name or var_name == "?":
        return False

    curr = node
    while id(curr) in parent_map:
        parent = parent_map[id(curr)]
        ptype = parent.get("type", "")

        # Ternary conditional expression: cond ? cons : alt
        if ptype in ("ternary_expression", "conditional_expression"):
            cond = parent.get("children", [{}])[0]
            cond_text = (cond.get("text") or "").replace(" ", "")
            # e.g. d != 0 ? n / d : 0
            if f"{var_name}!=0" in cond_text or f"0!={var_name}" in cond_text or f"{var_name}>0" in cond_text:
                return True

        # If statement: if (d != 0) { ... }
        if ptype == "if_statement":
            cond = next((c for c in parent.get("children", []) if c.get("type") in ("parenthesized_expression", "condition")), None)
            if cond:
                cond_text = (cond.get("text") or "").replace(" ", "")
                if f"{var_name}!=0" in cond_text or f"0!={var_name}" in cond_text or f"{var_name}>0" in cond_text:
                    return True

        curr = parent

    return False


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

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        parent_map: dict = {}
        self._build_parent_map(ast, parent_map)
        is_test = self._is_test_file(file_path)

        for node in self._walk(ast):
            if node.get("type") != "binary_expression":
                continue

            children = node.get("children", [])
            if len(children) < 3:
                continue

            operator_node = children[1]
            op_text = (operator_node.get("text") or "").strip()
            if op_text not in ("/", "%"):
                continue

            self.record_syntax_match()

            right_node = children[2]
            right_text = (right_node.get("text") or "?").strip()

            # 1. Constant expression evaluation
            const_val = self._evaluate_constant_expr(right_node)
            if const_val is not None and isinstance(const_val, (int, float)):
                if const_val != 0:
                    self.record_suppression(f"constant_non_zero_{const_val}")
                    continue
                else:
                    # Literal 0 or constant expression = 0
                    yield self._make_issue(
                        node=node,
                        file_path=file_path,
                        source_lines=source_lines,
                        message=f"Division by zero: divisor `{right_text}` evaluates to 0 at compile-time.",
                        evidence={
                            "operator": op_text,
                            "right_operand": right_text,
                            "evaluated_value": 0,
                            "confidence": "high",
                            "reason": "Evaluated compile-time constant divisor is exactly zero.",
                        },
                        confidence="high",
                    )
                    continue

            # 2. Check Math.max non-zero bounds (e.g. Math.max(x, 1))
            if _has_math_max_guard(right_node):
                self.record_suppression("math_max_lower_bound_guard")
                continue

            # 3. Check for local conditional guards (if (denom != 0) / ternary)
            var_name = right_text if right_node.get("type") == "identifier" else ""
            if var_name and _is_guarded_in_ancestors(node, parent_map, var_name):
                self.record_suppression(f"local_zero_guard_for_{var_name}")
                continue

            # Dynamic divisor without proved safety
            confidence = "low" if is_test else "medium"

            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"Division by potentially zero value: divisor `{right_text}` "
                    f"is not guarded against 0. Ensure divisor is validated before dividing."
                ),
                evidence={
                    "operator": op_text,
                    "right_operand": right_text,
                    "right_node_type": right_node.get("type", "unknown"),
                    "confidence": confidence,
                    "reason": f"Dynamic divisor `{right_text}` has no static zero guard.",
                },
                confidence=confidence,
            )

            return _Z.POTENTIALLY_ZERO

    def _classify_unary(self, node: dict) -> _Z:
        children = node.get("children", [])
        if len(children) < 2:
            return _Z.POTENTIALLY_ZERO

        op = (children[0].get("text") or "").strip()
        operand = children[1]

        if op in ("-", "+"):
            return self._classify(operand)

        return _Z.POTENTIALLY_ZERO
