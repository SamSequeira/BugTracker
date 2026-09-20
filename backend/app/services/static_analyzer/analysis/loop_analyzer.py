"""
loop_analyzer.py
----------------
Loop termination, counter progression, and break-reachability analyzer.
Specialized for detecting infinite loops and analyzing loop exit conditions in Java.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Dict, Iterator, List, Optional, Set, Tuple

from .constant_evaluator import ConstantEvaluator, evaluate_constant


class LoopExitStatus(Enum):
    DEFINITELY_TERMINATING = auto()  # Unconditional break/return/throw
    REACHABLE_EXIT         = auto()  # Exit protected by valid dynamic condition or progressing counter
    DIVERGING_COUNTER      = auto()  # Counter moves away from exit condition (e.g. x-- while waiting for x > 10)
    UNREACHABLE_EXIT       = auto()  # Exit protected by constant false (e.g. if (false) break;)
    NO_EXIT                = auto()  # No break/return/throw in loop


# Constructs that capture unlabeled break statements
_INNER_BREAK_TARGETS = {
    "for_statement", "while_statement", "do_statement", "enhanced_for_statement",
    "switch_statement", "switch_block", "switch_expression",
}


class LoopAnalyzer:
    """Analyzes Java loop constructs for infinite iteration hazards."""

    @classmethod
    def is_infinite_loop_candidate(cls, loop_node: dict) -> bool:
        """Returns True if loop has condition `true` or empty for-header `for (;;)`."""
        ntype = loop_node.get("type", "")

        if ntype == "while_statement":
            children = loop_node.get("children", [])
            # Find parenthesized condition
            cond = next((c for c in children if c.get("type") == "parenthesized_expression"), None)
            if cond:
                val = evaluate_constant(cond)
                return val is True

        if ntype == "for_statement":
            # Check for empty condition child or `true`
            text = (loop_node.get("text") or "").replace(" ", "")
            if text.startswith("for(;;") or text.startswith("for(;") or ";;" in text or ";true;" in text:
                return True

        if ntype == "do_statement":
            cond = next((c for c in loop_node.get("children", []) if c.get("type") == "parenthesized_expression"), None)
            if cond:
                val = evaluate_constant(cond)
                return val is True

        return False

    @classmethod
    def analyze_loop_exits(
        cls,
        loop_node: dict,
        outer_vars: Optional[Dict[str, float]] = None,
    ) -> Tuple[LoopExitStatus, str]:
        """
        Analyzes the body of loop_node for reachable exits.
        Returns (LoopExitStatus, explanation_message).
        """
        body = next((c for c in loop_node.get("children", []) if c.get("type") == "block"), None)
        if not body:
            return LoopExitStatus.NO_EXIT, "Loop has no statement block body."

        # Collect all exit candidates directly associated with this loop
        exits = cls._collect_direct_loop_exits(body)
        if not exits:
            return LoopExitStatus.NO_EXIT, "Loop has no break, return, or throw statements."

        has_dynamic_exit = False
        diverging_exits = []

        for exit_node, enclosing_if in exits:
            # 1. Unconditional exit directly in body
            if enclosing_if is None:
                return LoopExitStatus.DEFINITELY_TERMINATING, "Loop contains unconditional exit statement."

            # 2. Conditional exit: evaluate the if condition
            cond_node = next((c for c in enclosing_if.get("children", []) if c.get("type") == "parenthesized_expression"), None)
            if cond_node:
                const_val = evaluate_constant(cond_node)
                if const_val is False:
                    # Constant false -> unreachable break!
                    continue
                if const_val is True:
                    return LoopExitStatus.DEFINITELY_TERMINATING, "Exit condition evaluates statically to true."

                # Dynamic condition: inspect counter progression if counter is modified in loop
                trend_status, msg = cls._analyze_counter_progression(cond_node, body, outer_vars)
                if trend_status == LoopExitStatus.DIVERGING_COUNTER:
                    diverging_exits.append(msg)
                    continue
                if trend_status == LoopExitStatus.UNREACHABLE_EXIT:
                    continue
                if trend_status in (LoopExitStatus.REACHABLE_EXIT, LoopExitStatus.DEFINITELY_TERMINATING):
                    return LoopExitStatus.REACHABLE_EXIT, msg

                has_dynamic_exit = True

        if diverging_exits:
            return LoopExitStatus.DIVERGING_COUNTER, diverging_exits[0]

        if has_dynamic_exit:
            return LoopExitStatus.REACHABLE_EXIT, "Loop contains conditionally reachable exit."

        return LoopExitStatus.UNREACHABLE_EXIT, "All break conditions inside loop are statically unreachable."

    @classmethod
    def _collect_direct_loop_exits(cls, body_node: dict) -> List[Tuple[dict, Optional[dict]]]:
        """
        Recursively finds break/return/throw statements belonging to this loop.
        Does NOT cross into inner loops/switches for unlabeled breaks.
        """
        results: List[Tuple[dict, Optional[dict]]] = []

        def _traverse(node: dict, current_if: Optional[dict]) -> None:
            ntype = node.get("type", "")

            # If statement
            if ntype == "if_statement":
                # Find then-block and else-block
                children = node.get("children", [])
                for c in children:
                    if c.get("type") not in ("if", "parenthesized_expression"):
                        _traverse(c, node)
                return

            # Return / throw statements / System.exit exit all loops
            if ntype in ("return_statement", "throw_statement"):
                results.append((node, current_if))
                return

            # System.exit(...) or Runtime.getRuntime().halt(...)
            if ntype == "expression_statement":
                text = (node.get("text") or "").replace(" ", "")
                if "System.exit(" in text or "getRuntime().halt(" in text or "getRuntime().exit(" in text:
                    results.append((node, current_if))
                    return

            # Break statement
            if ntype == "break_statement":
                results.append((node, current_if))
                return

            # Stop recursion into nested loops and switches for unlabeled breaks
            if ntype in _INNER_BREAK_TARGETS:
                # Inside inner loop, returns, throws, and labeled breaks still exit
                for inner_n in cls._walk(node):
                    if inner_n.get("type") in ("return_statement", "throw_statement"):
                        results.append((inner_n, current_if))
                    elif inner_n.get("type") == "break_statement":
                        text = (inner_n.get("text") or "").strip()
                        if len(text.split()) > 1 and not text.endswith("break;"):
                            results.append((inner_n, current_if))
                return

            for c in node.get("children", []):
                _traverse(c, current_if)

        _traverse(body_node, None)
        return results

    @classmethod
    def _analyze_counter_progression(
        cls,
        cond_node: dict,
        body_node: dict,
        outer_vars: Optional[Dict[str, float]],
    ) -> Tuple[LoopExitStatus, str]:
        """
        Inspects condition AST (e.g. `x >= 10` or `x > 10`) and checks how `x` is modified in `body_node` AST.
        Uses exact AST node matching rather than source text substring inspection.
        """
        cond_info = cls._extract_counter_condition(cond_node)
        if not cond_info:
            return LoopExitStatus.REACHABLE_EXIT, "Dynamic condition without detectable counter pattern."

        var_name, op, target_val = cond_info

        # Traverse AST of body to detect actual induction updates targeting var_name
        is_incremented, is_decremented = cls._inspect_induction_var_updates(body_node, var_name)

        # Assume standard 0.0 start value if not provided
        start_val = outer_vars.get(var_name, 0.0) if outer_vars else 0.0

        if op in (">=", ">"):
            if target_val > start_val:
                if is_decremented and not is_incremented:
                    return (
                        LoopExitStatus.DIVERGING_COUNTER,
                        f"Counter `{var_name}` decrements away from exit condition `{op} {target_val}`.",
                    )
                if is_incremented:
                    return (
                        LoopExitStatus.REACHABLE_EXIT,
                        f"Counter `{var_name}` increments towards exit threshold `{target_val}`.",
                    )
                if not is_incremented and not is_decremented:
                    return (
                        LoopExitStatus.UNREACHABLE_EXIT,
                        f"Counter `{var_name}` is not updated in loop body to reach exit condition `{op} {target_val}`.",
                    )

        if op in ("<=", "<"):
            if target_val < start_val:
                if is_incremented and not is_decremented:
                    return (
                        LoopExitStatus.DIVERGING_COUNTER,
                        f"Counter `{var_name}` increments away from exit condition `{op} {target_val}`.",
                    )
                if is_decremented:
                    return (
                        LoopExitStatus.REACHABLE_EXIT,
                        f"Counter `{var_name}` decrements towards exit threshold `{target_val}`.",
                    )
                if not is_incremented and not is_decremented:
                    return (
                        LoopExitStatus.UNREACHABLE_EXIT,
                        f"Counter `{var_name}` is not updated in loop body to reach exit condition `{op} {target_val}`.",
                    )

        if op == "==":
            if target_val > start_val:
                if is_incremented:
                    return (
                        LoopExitStatus.REACHABLE_EXIT,
                        f"Counter `{var_name}` increments towards exit threshold `{target_val}`.",
                    )
                if is_decremented and not is_incremented:
                    return (
                        LoopExitStatus.DIVERGING_COUNTER,
                        f"Counter `{var_name}` decrements away from exit threshold `{target_val}`.",
                    )
                if not is_incremented and not is_decremented:
                    return (
                        LoopExitStatus.UNREACHABLE_EXIT,
                        f"Counter `{var_name}` is not updated in loop body to reach exit threshold `{target_val}`.",
                    )
            elif target_val < start_val:
                if is_decremented:
                    return (
                        LoopExitStatus.REACHABLE_EXIT,
                        f"Counter `{var_name}` decrements towards exit threshold `{target_val}`.",
                    )
                if is_incremented and not is_decremented:
                    return (
                        LoopExitStatus.DIVERGING_COUNTER,
                        f"Counter `{var_name}` increments away from exit threshold `{target_val}`.",
                    )
                if not is_incremented and not is_decremented:
                    return (
                        LoopExitStatus.UNREACHABLE_EXIT,
                        f"Counter `{var_name}` is not updated in loop body to reach exit threshold `{target_val}`.",
                    )

        return LoopExitStatus.REACHABLE_EXIT, "Dynamic loop exit."

    @classmethod
    def _extract_counter_condition(cls, cond_node: dict) -> Optional[Tuple[str, str, float]]:
        """
        Extracts (var_name, normalized_op, target_value) from condition AST.
        Supports parenthesized binary expressions like (x > 10), (10 <= x), (x == 5).
        """
        # Unwrap parenthesized_expression
        inner = cond_node
        while inner.get("type") == "parenthesized_expression":
            expr_children = [c for c in inner.get("children", []) if c.get("type") not in ("(", ")")]
            if expr_children:
                inner = expr_children[0]
            else:
                break

        if inner.get("type") != "binary_expression":
            return None

        kids = inner.get("children", [])
        if len(kids) < 3:
            return None

        left, op_node, right = kids[0], kids[1], kids[2]
        op = (op_node.get("text") or "").strip()
        if op not in (">", ">=", "<", "<=", "=="):
            return None

        # Case 1: left is identifier, right is constant number
        if left.get("type") == "identifier":
            var_name = (left.get("text") or "").strip()
            const_val = evaluate_constant(right)
            if const_val is not None and isinstance(const_val, (int, float)):
                return (var_name, op, float(const_val))

        # Case 2: right is identifier, left is constant number (invert operator)
        if right.get("type") == "identifier":
            var_name = (right.get("text") or "").strip()
            const_val = evaluate_constant(left)
            if const_val is not None and isinstance(const_val, (int, float)):
                inverted_ops = {
                    ">": "<",
                    ">=": "<=",
                    "<": ">",
                    "<=": ">=",
                    "==": "==",
                }
                return (var_name, inverted_ops.get(op, op), float(const_val))

        return None

    @classmethod
    def _inspect_induction_var_updates(cls, body_node: dict, var_name: str) -> Tuple[bool, bool]:
        """
        Walks body_node AST to find genuine update and assignment operations modifying var_name.
        Returns (is_incremented, is_decremented).
        Does NOT rely on source text search (comments and string literals are ignored).
        """
        is_incremented = False
        is_decremented = False

        for node in cls._walk(body_node):
            ntype = node.get("type", "")

            # 1. Update expression: x++, ++x, x--, --x
            if ntype == "update_expression":
                kids = node.get("children", [])
                ident = next((c for c in kids if c.get("type") == "identifier"), None)
                if ident and (ident.get("text") or "").strip() == var_name:
                    op = next((c for c in kids if (c.get("text") or "").strip() in ("++", "--")), None)
                    if op:
                        op_txt = (op.get("text") or "").strip()
                        if op_txt == "++":
                            is_incremented = True
                        elif op_txt == "--":
                            is_decremented = True

            # 2. Assignment expression: x += 1, x -= 1, x = x + 1, x = x - 1
            elif ntype == "assignment_expression":
                kids = node.get("children", [])
                if len(kids) >= 3:
                    lhs, op_node, rhs = kids[0], kids[1], kids[2]
                    lhs_name = (lhs.get("text") or "").strip()
                    if lhs.get("type") == "identifier" and lhs_name == var_name:
                        op_txt = (op_node.get("text") or "").strip()
                        if op_txt == "+=":
                            val = evaluate_constant(rhs)
                            if val is not None and isinstance(val, (int, float)):
                                if val > 0:
                                    is_incremented = True
                                elif val < 0:
                                    is_decremented = True
                            else:
                                is_incremented = True
                        elif op_txt == "-=":
                            val = evaluate_constant(rhs)
                            if val is not None and isinstance(val, (int, float)):
                                if val > 0:
                                    is_decremented = True
                                elif val < 0:
                                    is_incremented = True
                            else:
                                is_decremented = True
                        elif op_txt == "=":
                            if rhs.get("type") == "binary_expression":
                                r_kids = rhs.get("children", [])
                                if len(r_kids) >= 3:
                                    r_lhs, r_op, r_rhs = r_kids[0], r_kids[1], r_kids[2]
                                    r_op_txt = (r_op.get("text") or "").strip()
                                    r_lhs_name = (r_lhs.get("text") or "").strip() if r_lhs.get("type") == "identifier" else ""
                                    r_rhs_name = (r_rhs.get("text") or "").strip() if r_rhs.get("type") == "identifier" else ""

                                    if r_op_txt == "+":
                                        if r_lhs_name == var_name:
                                            val = evaluate_constant(r_rhs)
                                            if val is None or val > 0:
                                                is_incremented = True
                                        elif r_rhs_name == var_name:
                                            val = evaluate_constant(r_lhs)
                                            if val is None or val > 0:
                                                is_incremented = True
                                    elif r_op_txt == "-":
                                        if r_lhs_name == var_name:
                                            val = evaluate_constant(r_rhs)
                                            if val is None or val > 0:
                                                is_decremented = True

        return is_incremented, is_decremented

    @classmethod
    def _walk(cls, node: dict) -> Iterator[dict]:
        yield node
        for child in node.get("children", []):
            yield from cls._walk(child)
