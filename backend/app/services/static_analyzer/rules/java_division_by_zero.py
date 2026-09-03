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
