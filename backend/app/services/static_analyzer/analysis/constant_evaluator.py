"""
constant_evaluator.py
--------------------
Compile-time constant expression evaluator for Python, JavaScript, and Java ASTs.
Returns static literal values (int, float, bool, str, None) or None if dynamic.
"""

from __future__ import annotations

import re
from typing import Any, Optional, Union

# Constant literal types across tree-sitter grammars
_NUMERIC_TYPES = {
    # Python
    "integer", "float",
    # JavaScript
    "number",
    # Java
    "decimal_integer_literal", "hex_integer_literal", "octal_integer_literal",
    "binary_integer_literal", "decimal_floating_point_literal", "hex_floating_point_literal",
    "integer_literal", "floating_point_literal",
}

_BOOLEAN_TYPES = {
    "true", "false", "boolean_literal",
}

_NULL_TYPES = {
    "null", "null_literal", "none", "undefined",
}

_STRING_TYPES = {
    "string", "string_literal", "character_literal", "concatenated_string",
}


class ConstantEvaluator:
    """Evaluates AST nodes to Python primitive constant values when statically known."""

    @classmethod
    def evaluate(cls, node: Optional[dict]) -> Optional[Union[int, float, bool, str]]:
        if not node or not isinstance(node, dict):
            return None

        ntype = node.get("type", "")
        text = (node.get("text") or "").strip()

        # 1. Null / None / undefined
        if ntype in _NULL_TYPES or text in ("None", "null", "undefined"):
            return None  # Represents None / null constant

        # 2. Boolean literals
        if ntype in _BOOLEAN_TYPES or text in ("True", "False", "true", "false"):
            if text in ("True", "true"):
                return True
            if text in ("False", "false"):
                return False

        # 3. Numeric literals
        if ntype in _NUMERIC_TYPES:
            return cls._parse_numeric(text)

        # 4. String / Character literals
        if ntype in _STRING_TYPES:
            return cls._parse_string(node, text)

        # 5. Parenthesized expression: (expr)
        if ntype in ("parenthesized_expression",):
            inner = cls._unwrap_parens(node)
            if inner is not node:
                return cls.evaluate(inner)

        # 6. Unary expressions (+x, -x, !x, not x, ~x)
        if ntype in ("unary_expression", "unary_operator", "unary_op"):
            return cls._eval_unary(node)

        # 7. Binary expressions (+, -, *, /, //, %, **, <<, >>, &, |, ^, ==, !=, <, <=, >, >=)
        if ntype in ("binary_expression", "binary_operator", "binary_op", "comparison_operator"):
            return cls._eval_binary(node)

        # 8. Boolean / Logical expressions (and, or, &&, ||, ??)
        if ntype in ("boolean_operator", "logical_expression"):
            return cls._eval_logical(node)

        # 9. Conditional / Ternary expression (cond ? a : b, a if cond else b)
        if ntype in ("conditional_expression", "ternary_expression"):
            return cls._eval_conditional(node)

        return None

    @classmethod
    def is_static_none_or_null(cls, node: Optional[dict]) -> bool:
        if not node or not isinstance(node, dict):
            return False
        ntype = node.get("type", "")
        text = (node.get("text") or "").strip()
        return ntype in _NULL_TYPES or text in ("None", "null", "undefined")

    @classmethod
    def _parse_numeric(cls, text: str) -> Optional[Union[int, float]]:
        if not text:
            return None
        # Remove Java/C suffixes (e.g. 100L, 0.5f, 1000_000)
        clean = re.sub(r"[lLfFdD_]", "", text).strip()
        if not clean:
            return None

        # Hexadecimal: 0x... / 0X...
        if clean.startswith(("0x", "0X")):
            try:
                return int(clean, 16)
            except ValueError:
                return None

        # Binary: 0b... / 0B...
        if clean.startswith(("0b", "0B")):
            try:
                return int(clean, 2)
            except ValueError:
                return None

        # Octal: 0o... / 0O... or legacy 0777 (Java/C style octal if only digits and starts with 0)
        if clean.startswith(("0o", "0O")):
            try:
                return int(clean, 8)
            except ValueError:
                return None
        if clean.startswith("0") and len(clean) > 1 and clean.isdigit() and all(c in "01234567" for c in clean):
            try:
                return int(clean, 8)
            except ValueError:
                pass

        # Floating point or Scientific notation
        if "." in clean or "e" in clean.lower():
            try:
                return float(clean)
            except ValueError:
                return None

        # Standard decimal integer
        try:
            return int(clean)
        except ValueError:
            return None

    @classmethod
    def _parse_string(cls, node: dict, text: str) -> Optional[str]:
        if not text:
            return ""
        # Single or double quotes or triple quotes
        if (text.startswith(("'''", '"""')) and text.endswith(("'''", '"""')) and len(text) >= 6):
            return text[3:-3]
        if (text.startswith(('"', "'", "`")) and text.endswith(('"', "'", "`")) and len(text) >= 2):
            return text[1:-1]
        return None

    @classmethod
    def _unwrap_parens(cls, node: dict) -> dict:
        children = [c for c in node.get("children", []) if c.get("text", "") not in ("(", ")")]
        if len(children) == 1:
            return cls._unwrap_parens(children[0]) if children[0].get("type") == "parenthesized_expression" else children[0]
        return node

    @classmethod
    def _eval_unary(cls, node: dict) -> Optional[Union[int, float, bool]]:
        children = node.get("children", [])
        if not children:
            return None

        op = (children[0].get("text") or "").strip()
        operand = children[-1]
        val = cls.evaluate(operand)

        if val is None:
            return None

        if op in ("+",):
            if isinstance(val, (int, float)):
                return +val
        elif op in ("-",):
            if isinstance(val, (int, float)):
                return -val
        elif op in ("!", "not"):
            return not bool(val)
        elif op in ("~",):
            if isinstance(val, int):
                return ~val
        return None

    @classmethod
    def _eval_binary(cls, node: dict) -> Optional[Union[int, float, bool, str]]:
        children = node.get("children", [])
        if len(children) < 3:
            return None

        left_node = children[0]
        op = (children[1].get("text") or "").strip()
        right_node = children[2]

        # Logical operators in binary_expression (e.g. Java false && unknown())
        if op in ("&&", "and", "||", "or", "??"):
            return cls._eval_logical(node)

        left_val = cls.evaluate(left_node)
        right_val = cls.evaluate(right_node)

        # Handle string concatenation: "a" + "b"
        if op == "+" and (isinstance(left_val, str) or isinstance(right_val, str)):
            if left_val is not None and right_val is not None:
                return str(left_val) + str(right_val)

        # Numeric and Boolean arithmetic
        if left_val is not None and right_val is not None:
            if isinstance(left_val, (int, float, bool)) and isinstance(right_val, (int, float, bool)):
                # Convert bool to int for arithmetic
                lv = int(left_val) if isinstance(left_val, bool) else left_val
                rv = int(right_val) if isinstance(right_val, bool) else right_val

                try:
                    if op == "+":
                        return lv + rv
                    if op == "-":
                        return lv - rv
                    if op == "*":
                        return lv * rv
                    if op == "/":
                        if rv == 0:
                            return None  # Let division-by-zero rules catch the 0 denominator
                        return lv / rv
                    if op == "//":
                        if rv == 0:
                            return None
                        return lv // rv
                    if op == "%":
                        if rv == 0:
                            return None
                        return lv % rv
                    if op == "**":
                        if abs(rv) > 100:  # Prevent huge power exponent explosion
                            return None
                        return lv ** rv
                    if op == "<<" and isinstance(lv, int) and isinstance(rv, int):
                        return lv << rv if 0 <= rv < 64 else None
                    if op == ">>" and isinstance(lv, int) and isinstance(rv, int):
                        return lv >> rv if 0 <= rv < 64 else None
                    if op == "&" and isinstance(lv, int) and isinstance(rv, int):
                        return lv & rv
                    if op == "|" and isinstance(lv, int) and isinstance(rv, int):
                        return lv | rv
                    if op == "^" and isinstance(lv, int) and isinstance(rv, int):
                        return lv ^ rv

                    # Comparisons
                    if op in ("==", "==="):
                        return lv == rv
                    if op in ("!=", "!=="):
                        return lv != rv
                    if op == "<":
                        return lv < rv
                    if op == "<=":
                        return lv <= rv
                    if op == ">":
                        return lv > rv
                    if op == ">=":
                        return lv >= rv
                except (ZeroDivisionError, OverflowError, ValueError):
                    return None

        # Comparisons for strings
        if isinstance(left_val, str) and isinstance(right_val, str):
            if op in ("==", "==="):
                return left_val == right_val
            if op in ("!=", "!=="):
                return left_val != right_val

        return None

    @classmethod
    def _eval_logical(cls, node: dict) -> Optional[Union[int, float, bool, str]]:
        children = node.get("children", [])
        if len(children) < 3:
            return None

        left_node = children[0]
        op = (children[1].get("text") or "").strip()
        right_node = children[2]

        left_val = cls.evaluate(left_node)
        right_val = cls.evaluate(right_node)

        # Short-circuit logic if left is known
        if op in ("and", "&&"):
            if left_val is not None and not bool(left_val):
                return left_val
            if left_val is not None and right_val is not None:
                return right_val if bool(left_val) else left_val

        if op in ("or", "||"):
            if left_val is not None and bool(left_val):
                return left_val
            if left_val is not None and right_val is not None:
                return left_val if bool(left_val) else right_val

        if op == "??" and left_val is not None:
            # JavaScript nullish coalescing
            return left_val

        return None

    @classmethod
    def _eval_conditional(cls, node: dict) -> Optional[Any]:
        # Python: true_val if cond else false_val
        # JS/Java: cond ? true_val : false_val
        children = node.get("children", [])
        if not children:
            return None

        # Detect Python ternary: <expr> if <cond> else <expr>
        kw_texts = [c.get("text", "") for c in children]
        if "if" in kw_texts and "else" in kw_texts:
            if_idx = kw_texts.index("if")
            else_idx = kw_texts.index("else")
            if if_idx > 0 and else_idx > if_idx:
                true_node = children[0]
                cond_node = children[if_idx + 1]
                false_node = children[else_idx + 1]
                true_val = cls.evaluate(true_node)
                false_val = cls.evaluate(false_node)
                if true_val is not None and false_val is not None and true_val == false_val:
                    return true_val
                cond_val = cls.evaluate(cond_node)
                if cond_val is not None:
                    return true_val if bool(cond_val) else false_val

        # JS / Java ternary: cond ? true_val : false_val
        if "?" in kw_texts:
            q_idx = kw_texts.index("?")
            cond_node = children[0]
            true_node = children[q_idx + 1] if q_idx + 1 < len(children) else None
            colon_idx = kw_texts.index(":") if ":" in kw_texts else -1
            false_node = children[colon_idx + 1] if colon_idx != -1 and colon_idx + 1 < len(children) else None

            if true_node and false_node:
                true_val = cls.evaluate(true_node)
                false_val = cls.evaluate(false_node)
                if true_val is not None and false_val is not None and true_val == false_val:
                    return true_val
                cond_val = cls.evaluate(cond_node)
                if cond_val is not None:
                    return true_val if bool(cond_val) else false_val

        return None


def evaluate_constant(node: Optional[dict]) -> Optional[Union[int, float, bool, str]]:
    """Convenience functional interface."""
    return ConstantEvaluator.evaluate(node)
