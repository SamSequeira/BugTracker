"""
guard_analyzer.py
-----------------
Analyzes branch conditions, guards, and assertions across Python, JS, and Java.
Extracts zero/non-zero and null/non-null constraints on variables.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Tuple

from .constant_evaluator import ConstantEvaluator, evaluate_constant


class GuardType(Enum):
    ZERO            = auto()  # x == 0
    NON_ZERO        = auto()  # x != 0, x > 0, if (x)
    NULL            = auto()  # x == null, x is None
    NON_NULL        = auto()  # x != null, x is not None, if (x)
    CONSTANT_TRUE   = auto()  # True, true, 1 == 1
    CONSTANT_FALSE  = auto()  # False, false, 1 == 2
    UNKNOWN         = auto()


@dataclass
class GuardInfo:
    guard_type: GuardType
    var_name: Optional[str] = None
    node: Optional[dict] = None
    constant_value: Optional[bool] = None


class GuardAnalyzer:
    """Extracts variable constraints from conditions and assertions."""

    @classmethod
    def analyze_condition(cls, cond_node: Optional[dict]) -> List[GuardInfo]:
        if not cond_node or not isinstance(cond_node, dict):
            return []

        # 1. Check compile-time constant condition
        const_val = evaluate_constant(cond_node)
        if const_val is not None:
            g_type = GuardType.CONSTANT_TRUE if bool(const_val) else GuardType.CONSTANT_FALSE
            return [GuardInfo(guard_type=g_type, node=cond_node, constant_value=bool(const_val))]

        ntype = cond_node.get("type", "")
        text = (cond_node.get("text") or "").strip()

        # Unwrap parentheses
        if ntype == "parenthesized_expression":
            inner = cls._unwrap_parens(cond_node)
            if inner is not cond_node:
                return cls.analyze_condition(inner)

        # 2. Simple truthiness identifier: `if (x)` or `if x:`
        if ntype == "identifier":
            var_name = text
            if var_name:
                return [
                    GuardInfo(guard_type=GuardType.NON_ZERO, var_name=var_name, node=cond_node),
                    GuardInfo(guard_type=GuardType.NON_NULL, var_name=var_name, node=cond_node),
                ]

        # 3. Negation: `if (!x)` or `if not x:`
        if ntype in ("unary_expression", "unary_operator"):
            children = cond_node.get("children", [])
            if children:
                op = (children[0].get("text") or "").strip()
                if op in ("!", "not"):
                    inner = children[-1]
                    if inner.get("type") == "identifier":
                        var_name = (inner.get("text") or "").strip()
                        return [
                            GuardInfo(guard_type=GuardType.ZERO, var_name=var_name, node=cond_node),
                            GuardInfo(guard_type=GuardType.NULL, var_name=var_name, node=cond_node),
                        ]

        # 4. Binary comparisons: `x != 0`, `x == 0`, `x != null`, `x is None`, `x > 0`
        if ntype in ("binary_expression", "binary_operator", "comparison_operator"):
            return cls._analyze_comparison(cond_node)

        return []

    @classmethod
    def _analyze_comparison(cls, comp_node: dict) -> List[GuardInfo]:
        children = comp_node.get("children", [])
        if len(children) < 3:
            return []

        # Extract operator text
        # In Python comparison_operator, children might be [left, op, right]
        left_node = children[0]
        op = (children[1].get("text") or "").strip()
        right_node = children[2]

        left_name = cls._extract_var_name(left_node)
        right_name = cls._extract_var_name(right_node)

        left_const = evaluate_constant(left_node)
        right_const = evaluate_constant(right_node)

        left_is_null = ConstantEvaluator.is_static_none_or_null(left_node)
        right_is_null = ConstantEvaluator.is_static_none_or_null(right_node)

        guards = []

        # Case A: left is variable, right is constant zero / null
        if left_name:
            if right_const == 0 and not isinstance(right_const, bool):
                if op in ("!=", "!=="):
                    guards.append(GuardInfo(guard_type=GuardType.NON_ZERO, var_name=left_name, node=comp_node))
                elif op in ("==", "==="):
                    guards.append(GuardInfo(guard_type=GuardType.ZERO, var_name=left_name, node=comp_node))
                elif op in (">", ">="):
                    guards.append(GuardInfo(guard_type=GuardType.NON_ZERO, var_name=left_name, node=comp_node))
                elif op in ("<", "<="):
                    guards.append(GuardInfo(guard_type=GuardType.NON_ZERO, var_name=left_name, node=comp_node))
            elif right_is_null:
                if op in ("!=", "!==", "is not"):
                    guards.append(GuardInfo(guard_type=GuardType.NON_NULL, var_name=left_name, node=comp_node))
                elif op in ("==", "===", "is"):
                    guards.append(GuardInfo(guard_type=GuardType.NULL, var_name=left_name, node=comp_node))

        # Case B: right is variable, left is constant zero / null
        if right_name:
            if left_const == 0 and not isinstance(left_const, bool):
                if op in ("!=", "!=="):
                    guards.append(GuardInfo(guard_type=GuardType.NON_ZERO, var_name=right_name, node=comp_node))
                elif op in ("==", "==="):
                    guards.append(GuardInfo(guard_type=GuardType.ZERO, var_name=right_name, node=comp_node))
            elif left_is_null:
                if op in ("!=", "!==", "is not"):
                    guards.append(GuardInfo(guard_type=GuardType.NON_NULL, var_name=right_name, node=comp_node))
                elif op in ("==", "===", "is"):
                    guards.append(GuardInfo(guard_type=GuardType.NULL, var_name=right_name, node=comp_node))

        return guards

    @classmethod
    def analyze_assert(cls, assert_node: dict) -> List[GuardInfo]:
        """Extracts guard facts established by an assert statement."""
        children = assert_node.get("children", [])
        # Python: assert_statement [assert, condition, (, message)]
        # Java: assert_statement [assert, condition, (:, message), ;]
        non_kw = [c for c in children if (c.get("text") or "") not in ("assert", ",", ";")]
        if non_kw:
            return cls.analyze_condition(non_kw[0])
        return []

    @classmethod
    def is_idiomatic_non_constant(cls, node: dict) -> bool:
        """
        Check if a constant-looking condition is actually a legitimate idiom
        such as `if __name__ == '__main__':` or `if TYPE_CHECKING:` in Python.
        """
        text = (node.get("text") or "").replace(" ", "").replace('"', "'")
        if "__name__=='__main__'" in text:
            return True
        if "TYPE_CHECKING" in text:
            return True
        return False

    @staticmethod
    def _extract_var_name(node: Optional[dict]) -> Optional[str]:
        if not node or not isinstance(node, dict):
            return None
        ntype = node.get("type", "")
        if ntype == "identifier":
            return (node.get("text") or "").strip() or None
        if ntype == "parenthesized_expression":
            children = [c for c in node.get("children", []) if c.get("text", "") not in ("(", ")")]
            if len(children) == 1:
                return GuardAnalyzer._extract_var_name(children[0])
        return None

    @staticmethod
    def _unwrap_parens(node: dict) -> dict:
        children = [c for c in node.get("children", []) if c.get("text", "") not in ("(", ")")]
        if len(children) == 1:
            return children[0]
        return node
