"""
JAVA_DIV_001 — Division by zero or potentially-zero divisor (Java)
-------------------------------------------------------------------
Detects `/` and `%` binary expressions where the right-hand operand is
provably zero or cannot be proven non-zero.

Classification
--------------
DEFINITELY_ZERO      — literal 0, 0L, 0.0f, 0.0d, -0, +0, 0x0, 0b0
                       → always reported (definite error)
DEFINITELY_NON_ZERO  — any other numeric literal whose value ≠ 0
                       → never reported (provably safe)
POTENTIALLY_ZERO     — variable, field, method call, ternary, etc.
                       → reported as a potential issue (warning)

Root-cause notes (F-03, F-04)
------------------------------
The original rule skipped ALL numeric literals regardless of their value,
so `x / 0` was silently accepted.  Fix: parse each literal to detect zeros.

Java numeric literal types (tree-sitter)
-----------------------------------------
  decimal_integer_literal       e.g.  0  1  42  100_000L
  decimal_floating_point_literal  e.g.  0.0  0.0f  1.5d
  hex_integer_literal           e.g.  0x0  0xFF
  octal_integer_literal         e.g.  00  07
  binary_integer_literal        e.g.  0b0  0b1010
  hex_floating_point_literal    e.g.  0x0.0p0
  integer_literal / floating_point_literal  (older tree-sitter versions)

Unary minus / plus on a literal
---------------------------------
  `-0`  →  still zero  → flag
  `-1`  →  non-zero    → safe
  `+0`  →  still zero  → flag
  `+1`  →  non-zero    → safe
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
            else:
                message = (
                    f"Division by potentially zero value: the divisor `{right_text}` "
                    f"may be zero at runtime. Add a zero-guard before dividing."
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

        # Numeric literal — check its value
        if ntype in self._LITERAL_TYPES:
            return self._classify_literal(node)

        # Unary +/- on a literal: same zero-ness as the operand
        if ntype == "unary_expression":
            return self._classify_unary(node)

        # Everything else: variable, field, call, ternary, etc.
        return _Z.POTENTIALLY_ZERO

    def _classify_unary(self, node: dict) -> _Z:
        children = node.get("children", [])
        if not children:
            return _Z.POTENTIALLY_ZERO
        op = children[0].get("text", "").strip()
        if op not in ("+", "-"):
            return _Z.POTENTIALLY_ZERO
        operand = children[-1]
        return self._classify(operand)

    def _classify_literal(self, node: dict) -> _Z:
        val = self._literal_value(node)
        if val is None:
            return _Z.POTENTIALLY_ZERO
        return _Z.DEFINITELY_ZERO if val == 0.0 else _Z.DEFINITELY_NON_ZERO

    @staticmethod
    def _literal_value(node: dict) -> Optional[float]:
        """
        Parse a Java numeric literal node to a float.
        Returns None on parse failure.

        Handles:
        - Java type suffixes: L, l, f, F, d, D  — BUT only after determining
          the base so we don't accidentally strip a valid hex digit.
        - Digit group separators: _
        """
        raw = node.get("text", "").strip()
        text = raw.replace("_", "")
        if not text:
            return None

        # --- Hex: 0x… or 0X… ---
        # Strip only non-hex suffix chars (L only; f/F/d/D are valid hex digits)
        if re.match(r'^[+-]?0[xX]', text):
            hex_body = text.rstrip("lL")   # only Long suffix after hex
            try:
                return float.fromhex(hex_body)   # handles 0x1.0p0
            except ValueError:
                pass
            try:
                return float(int(hex_body, 16))
            except ValueError:
                return None

        # --- Binary: 0b… or 0B… ---
        if re.match(r'^[+-]?0[bB]', text):
            bin_body = text.rstrip("lL")
            try:
                return float(int(bin_body, 2))
            except ValueError:
                return None

        # --- Octal: starts with 0 followed by octal digits only ---
        if re.match(r'^[+-]?0[0-7]+$', text.rstrip("lL")):
            oct_body = text.rstrip("lL")
            try:
                return float(int(oct_body, 8))
            except ValueError:
                return None

        # --- Decimal integer or float (with optional L/f/d suffix) ---
        dec_body = text.rstrip("lLfFdD")
        try:
            return float(dec_body)
        except ValueError:
            return None
