"""
JS_DIV_001 — Division by zero (JavaScript)
-------------------------------------------
Detects `/` and `%` arithmetic binary expressions where the divisor is
provably zero via literal constants, constant folding, or local variable tracking.

Special JavaScript semantics:
- In JavaScript, `1 / 0` evaluates to `Infinity` and `0 / 0` evaluates to `NaN`.
- Intentional Infinity patterns (e.g. `const INF = 1 / 0;`) are recognized and exempted.
- Logical fallbacks `b || 1` and `b ?? 1` are recognized as non-zero.
- Generic unconstrained dynamic divisors (`a / b`) are NOT flagged to prevent false positives.
"""

from __future__ import annotations

from typing import Iterator, List, Optional

from ..analysis.constant_evaluator import ConstantEvaluator, evaluate_constant
from ..analysis.guard_analyzer import GuardAnalyzer, GuardType
from ..analysis.reachability_analyzer import ReachabilityAnalyzer
from ..analysis.variable_tracker import ScopeEnvironment, VariableStateTracker, VarInfo, VarState
from ..base_rule import BaseRule
from ..models import CandidateIssue


def _is_intentional_infinity_pattern(node: dict, parent_map: dict) -> bool:
    """Detects intentional Infinity / NEG_INF constant declarations."""
    curr = node
    for _ in range(4):
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
        env = ScopeEnvironment(scope_type="module")
        yield from self._analyze_node(ast, env, parent_map, file_path, source_lines)

    def _analyze_node(
        self,
        node: dict,
        env: ScopeEnvironment,
        parent_map: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:
        ntype = node.get("type", "")

        # 1. Variable declaration / declarator: const d = 0, let d = 0, var d = 0
        if ntype == "variable_declarator":
            kids = node.get("children", [])
            if len(kids) >= 3:
                lhs = kids[0]
                rhs = kids[-1]
                VariableStateTracker.process_assignment(lhs, rhs, env)

        # 2. Assignment expression: d = 0
        if ntype == "assignment_expression":
            kids = node.get("children", [])
            if len(kids) >= 3:
                lhs = kids[0]
                rhs = kids[-1]
                VariableStateTracker.process_assignment(lhs, rhs, env)

        # 3. If statement branching & guards
        if ntype == "if_statement":
            children = node.get("children", [])
            cond_node = next((c for c in children if c.get("type") == "parenthesized_expression"), None)
            guards = GuardAnalyzer.analyze_condition(cond_node) if cond_node else []

            then_node = next((c for c in children if c.get("type") in ("statement_block", "block")), None)
            else_node = next((c for c in children if c.get("type") == "else_clause"), None)

            # Then branch
            then_env = env.fork()
            for g in guards:
                if g.var_name:
                    if g.guard_type == GuardType.NON_ZERO:
                        then_env.update_state(g.var_name, VarState.GUARDED_NON_ZERO)
                    elif g.guard_type == GuardType.ZERO:
                        then_env.update_state(g.var_name, VarState.DEFINITELY_ZERO, constant_value=0)

            if then_node:
                yield from self._analyze_node(then_node, then_env, parent_map, file_path, source_lines)

            # Else branch
            if else_node:
                else_env = env.fork()
                for g in guards:
                    if g.var_name:
                        if g.guard_type == GuardType.ZERO:
                            else_env.update_state(g.var_name, VarState.GUARDED_NON_ZERO)
                        elif g.guard_type == GuardType.NON_ZERO:
                            else_env.update_state(g.var_name, VarState.DEFINITELY_ZERO, constant_value=0)
                yield from self._analyze_node(else_node, else_env, parent_map, file_path, source_lines)

            # Early exit in then-branch protects subsequent statements
            if guards and not else_node and then_node:
                if ReachabilityAnalyzer._block_unconditionally_terminates(then_node):
                    for g in guards:
                        if g.var_name and g.guard_type == GuardType.ZERO:
                            env.update_state(g.var_name, VarState.GUARDED_NON_ZERO)
            return

        # 4. Binary expression: / or %
        if ntype == "binary_expression":
            children = node.get("children", [])
            if len(children) >= 3:
                op_node = children[1]
                op_text = (op_node.get("text") or "").strip()
                if op_text in ("/", "%"):
                    # Check intentional Infinity pattern: const INF = 1 / 0;
                    if not _is_intentional_infinity_pattern(node, parent_map):
                        right_node = children[2]
                        right_text = (right_node.get("text") or "?").strip()

                        # Check fallback: (b || 1) or (b ?? 1)
                        if self._is_safe_fallback(right_node):
                            self.record_suppression("safe_logical_fallback")
                            return

                        # A. Constant evaluation
                        const_val = evaluate_constant(right_node)
                        if const_val is not None:
                            if isinstance(const_val, (int, float, bool)) and const_val == 0:
                                self.record_syntax_match()
                                yield self._make_issue(
                                    node=node,
                                    file_path=file_path,
                                    source_lines=source_lines,
                                    message=f"Division by zero: divisor `{right_text}` evaluates to 0.",
                                    evidence={
                                        "operator": op_text,
                                        "divisor": right_text,
                                        "reason": "constant_zero",
                                        "confidence": "high",
                                    },
                                    confidence="high",
                                )
                                return
                            # Safe non-zero constant
                            self.record_suppression("non_zero_constant")
                            return

                        # B. Variable tracking
                        vname = VariableStateTracker.extract_target_name(right_node)
                        if vname:
                            vinfo = env.get(vname)
                            if vinfo:
                                if vinfo.is_definitely_zero:
                                    self.record_syntax_match()
                                    yield self._make_issue(
                                        node=node,
                                        file_path=file_path,
                                        source_lines=source_lines,
                                        message=f"Division by zero: variable `{vname}` is known to be 0 at this point.",
                                        evidence={
                                            "operator": op_text,
                                            "variable": vname,
                                            "reason": "variable_assigned_zero",
                                            "confidence": "high",
                                        },
                                        confidence="high",
                                    )
                                    return
                                if vinfo.is_definitely_non_zero:
                                    self.record_suppression("guarded_or_non_zero_variable")
                                    return

                        # Dynamic unestablished divisor: do not flag
                        self.record_suppression("unestablished_divisor")

        for child in node.get("children", []):
            yield from self._analyze_node(child, env, parent_map, file_path, source_lines)

    @staticmethod
    def _is_safe_fallback(node: dict) -> bool:
        """Checks if divisor is wrapped in `(b || 1)` or `(b ?? 1)` with non-zero fallback."""
        ntype = node.get("type", "")
        if ntype == "parenthesized_expression":
            inner = [c for c in node.get("children", []) if c.get("text", "") not in ("(", ")")]
            if len(inner) == 1:
                return JavaScriptDivisionByZero._is_safe_fallback(inner[0])

        if ntype in ("binary_expression", "logical_expression"):
            children = node.get("children", [])
            if len(children) >= 3:
                op = (children[1].get("text") or "").strip()
                if op in ("||", "??"):
                    right_val = evaluate_constant(children[2])
                    if right_val is not None and isinstance(right_val, (int, float)) and right_val != 0:
                        return True
        return False
