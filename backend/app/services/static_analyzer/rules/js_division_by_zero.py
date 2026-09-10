"""
JS_DIV_001 — Division by zero or potentially-zero divisor (JavaScript)
-----------------------------------------------------------------------
Detects `/` and `%` binary expressions where the right-hand operand is
provably zero or cannot be proven non-zero.
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


def _is_intentional_infinity_pattern(node: dict, parent_map: dict) -> bool:
    """Detect intentional Infinity / NEG_INF constant declarations like `const INF = 1 / 0;`."""
    curr = node
    for _ in range(3):
        p = parent_map.get(id(curr))
        if not p:
            break
        ptype = p.get("type", "")
        if ptype in ("variable_declarator", "lexical_declaration", "variable_declaration", "assignment_expression"):
            ptext = (p.get("text") or "").upper()
            if "INF" in ptext or "INFINITY" in ptext:
                return True
        curr = p
    return False


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

        parent_map: dict = {}
        self._build_parent_map(ast, parent_map)

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

            # Check intentional Infinity patterns (e.g. const INF = 1 / 0;)
            if _is_intentional_infinity_pattern(node, parent_map):
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
                    f"may be zero at runtime.  Add a zero-guard before dividing."
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
        # Check constant expression evaluation
        c_val = self._evaluate_constant_expr(node)
        if c_val is not None and isinstance(c_val, (int, float)):
            return _Z.DEFINITELY_ZERO if c_val == 0 else _Z.DEFINITELY_NON_ZERO

        ntype = node.get("type", "")

        # Check logical fallback: b || 1 or b ?? 1
        if ntype in ("binary_expression", "logical_expression", "binary_operator"):
            children = node.get("children", [])
            if len(children) >= 3:
                op = children[1].get("text", "")
                if op in ("||", "??"):
                    if self._classify(children[2]) == _Z.DEFINITELY_NON_ZERO:
                        return _Z.DEFINITELY_NON_ZERO

        # JavaScript number literal — check the actual value
        if ntype == "number":
            return self._classify_number(node)

        # Unary minus / plus / bitwise NOT on a number
        if ntype == "unary_expression":
            return self._classify_unary(node)

        # Boolean literals: true -> 1 (non-zero), false -> 0 (zero)
        if ntype == "true":
            return _Z.DEFINITELY_NON_ZERO
        if ntype == "false":
            return _Z.DEFINITELY_ZERO

        # null -> coerces to 0
        if ntype == "null":
            return _Z.DEFINITELY_ZERO

        # Parenthesized expression
        if ntype == "parenthesized_expression":
            inner = [c for c in node.get("children", []) if c.get("text", "") not in ("(", ")")]
            if len(inner) == 1:
                return self._classify(inner[0])

        return _Z.POTENTIALLY_ZERO

    def _classify_number(self, node: dict) -> _Z:
        text = (node.get("text") or "").strip()
        clean = text.rstrip("nN").replace("_", "")

        if not clean:
            return _Z.POTENTIALLY_ZERO

        try:
            if clean.startswith(("0x", "0X")):
                val = int(clean, 16)
            elif clean.startswith(("0b", "0B")):
                val = int(clean, 2)
            elif clean.startswith(("0o", "0O")):
                val = int(clean, 8)
            elif "." in clean or "e" in clean.lower():
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

        if op == "!":
            inner = self._classify(operand)
            if inner == _Z.DEFINITELY_ZERO:
                return _Z.DEFINITELY_NON_ZERO
            if inner == _Z.DEFINITELY_NON_ZERO:
                return _Z.DEFINITELY_ZERO

        return _Z.POTENTIALLY_ZERO
