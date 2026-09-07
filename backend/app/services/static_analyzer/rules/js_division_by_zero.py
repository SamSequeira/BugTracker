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

        # Hexadecimal: 0x…
        if text.startswith(("0x", "0X")):
            try:
                return float(int(text, 16))
            except ValueError:
                return None

        # Binary: 0b…
        if text.startswith(("0b", "0B")):
            try:
                return float(int(text, 2))
            except ValueError:
                return None

        # Octal: 0o… (ES6+) or legacy 0…
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
JS_DIV_001 — Division by zero or potentially-zero divisor (JavaScript)
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



import re
from typing import Iterator, List, Optional

from ..base_rule import BaseRule
from ..models import CandidateIssue


def _has_js_guard_wrapper(node: dict) -> bool:
    """Check for Math.max(x, 1) or (d || 1) pattern."""
    text = (node.get("text") or "").replace(" ", "")
    if re.search(r'Math\.max\([^,]+,[1-9]\d*\)', text) or re.search(r'Math\.max\([1-9]\d*,[^)]+\)', text):
        return True
    if re.search(r'\|\|[1-9]\d*', text) or re.search(r'\?\?[1-9]\d*', text):
        return True
    return False


def _is_guarded_in_js_ancestors(node: dict, parent_map: dict, var_name: str) -> bool:
    """Check if variable is guarded against zero in enclosing if or ternary."""
    if not var_name or var_name == "?":
        return False

    curr = node
    while id(curr) in parent_map:
        parent = parent_map[id(curr)]
        ptype = parent.get("type", "")

        # Ternary: cond ? cons : alt
        if ptype in ("ternary_expression", "conditional_expression"):
            cond = parent.get("children", [{}])[0]
            cond_text = (cond.get("text") or "").replace(" ", "")
            if (
                f"{var_name}!==0" in cond_text
                or f"{var_name}!=0" in cond_text
                or f"{var_name}>0" in cond_text
                or cond_text == var_name
            ):
                return True

        # If statement: if (total !== 0)
        if ptype == "if_statement":
            cond = next((c for c in parent.get("children", []) if c.get("type") in ("parenthesized_expression", "condition")), None)
            if cond:
                cond_text = (cond.get("text") or "").replace(" ", "")
                if (
                    f"{var_name}!==0" in cond_text
                    or f"{var_name}!=0" in cond_text
                    or f"{var_name}>0" in cond_text
                    or cond_text == f"({var_name})"
                    or cond_text == var_name
                ):
                    return True

        curr = parent

    return False


def _is_intentional_infinity(node: dict, parent_map: dict) -> bool:
    """Check if 1 / 0 is used deliberately to define Infinity."""
    curr = node
    while id(curr) in parent_map:
        parent = parent_map[id(curr)]
        ptype = parent.get("type", "")
        ptext = (parent.get("text") or "").lower()
        if "infinity" in ptext:
            return True
        if ptype in ("variable_declarator", "assignment_expression", "lexical_declaration"):
            if "inf" in ptext:
                return True
        curr = parent
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
            right_type = right_node.get("type", "")

            # 1. Check true (coerces to 1 in JS) -> non-zero
            if right_type == "true":
                self.record_suppression("boolean_true_coerces_to_1")
                continue

            # 2. Constant evaluation
            const_val = self._evaluate_constant_expr(right_node)
            if const_val is not None and isinstance(const_val, (int, float)):
                if const_val != 0:
                    self.record_suppression(f"constant_non_zero_{const_val}")
                    continue
                else:
                    # Divisor is 0 -> check intentional Infinity
                    if _is_intentional_infinity(node, parent_map):
                        self.record_suppression("intentional_infinity_pattern")
                        continue

                    yield self._make_issue(
                        node=node,
                        file_path=file_path,
                        source_lines=source_lines,
                        message=f"Division by zero: divisor `{right_text}` evaluates to 0.",
                        evidence={
                            "operator": op_text,
                            "right_operand": right_text,
                            "evaluated_value": 0,
                            "confidence": "high",
                            "reason": "Evaluated constant divisor is 0.",
                        },
                        confidence="high",
                    )
                    continue

            # 3. Explicit null / false literals (coerce to 0 in JS)
            if right_type in ("null", "false"):
                yield self._make_issue(
                    node=node,
                    file_path=file_path,
                    source_lines=source_lines,
                    message=f"Division by zero: `{right_text}` coerces to 0 in arithmetic operations.",
                    evidence={
                        "operator": op_text,
                        "right_operand": right_text,
                        "confidence": "high",
                        "reason": f"Literal `{right_text}` coerces to 0 in JavaScript arithmetic.",
                    },
                    confidence="high",
                )
                continue

            # 4. Guard wrappers like Math.max(x, 1) or (d || 1)
            if _has_js_guard_wrapper(right_node):
                self.record_suppression("guard_wrapper_detected")
                continue

            # 5. Local zero guard in if/ternary
            var_name = right_text if right_type == "identifier" else ""
            if var_name and _is_guarded_in_js_ancestors(node, parent_map, var_name):
                self.record_suppression(f"local_zero_guard_for_{var_name}")
                continue

            confidence = "low" if is_test else "medium"

            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"Division by potentially zero value: divisor `{right_text}` "
                    f"is not guarded against 0. Ensure divisor is non-zero before dividing."
                ),
                evidence={
                    "operator": op_text,
                    "right_operand": right_text,
                    "right_node_type": right_type,
                    "confidence": confidence,
                    "reason": f"Dynamic divisor `{right_text}` has no static zero guard.",
                },
                confidence=confidence,
            )

        if op == "!":
            inner = self._classify(operand)
            if inner == _Z.DEFINITELY_ZERO:
                return _Z.DEFINITELY_NON_ZERO
            if inner == _Z.DEFINITELY_NON_ZERO:
                return _Z.DEFINITELY_ZERO

        return _Z.POTENTIALLY_ZERO
