"""
JAVA_DIV_001 — Division by zero (Java)
---------------------------------------
Detects `/` and `%` arithmetic binary expressions where the divisor is
provably zero via literal constants, constant folding, or local variable tracking.

High-confidence detection criteria:
- Literal zeros: `10 / 0`, `10 / 0.0`, `10 / 0.0f`, `10 / 0L`, `10 / 0x0`
- Constant folded zeros: `10 / (2 - 2)`, `10 / (60 * 0)`
- Variable assigned to zero: `int d = 0; int x = total / d;`

Suppression criteria (provably safe or unestablished):
- Non-zero literals: `10 / 1`, `10 / 0xFF` (255), `10 / 1.5`, `10 / 10L`
- Constant folded non-zero: `ms / (60 * 1000)`
- Math.max guards: `total / Math.max(1, count)`
- Guarded divisions: `if (d != 0) { x / d; }` or `if (d == 0) return; x / d;`
- Unconstrained dynamic variables (`x / y` where `y` is an unknown parameter or method result).
"""

from __future__ import annotations

from typing import Iterator, List, Optional

from ..analysis.constant_evaluator import ConstantEvaluator, evaluate_constant
from ..analysis.guard_analyzer import GuardAnalyzer, GuardType
from ..analysis.reachability_analyzer import ReachabilityAnalyzer
from ..analysis.variable_tracker import ScopeEnvironment, VariableStateTracker, VarInfo, VarState
from ..base_rule import BaseRule
from ..models import CandidateIssue


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
        env = ScopeEnvironment(scope_type="module")
        yield from self._analyze_node(ast, env, file_path, source_lines)

    def _analyze_node(
        self,
        node: dict,
        env: ScopeEnvironment,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:
        ntype = node.get("type", "")

        # 1. Local variable declaration: int d = 0;
        if ntype == "local_variable_declaration":
            # Children typically include type and variable_declarator
            for decl in node.get("children", []):
                if decl.get("type") == "variable_declarator":
                    kids = decl.get("children", [])
                    if len(kids) >= 3:
                        lhs = kids[0]
                        rhs = kids[-1]
                        VariableStateTracker.process_assignment(lhs, rhs, env)

        # 2. Assignment expression: d = 0;
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

            then_node = next((c for c in children if c.get("type") == "block"), None)
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
                yield from self._analyze_node(then_node, then_env, file_path, source_lines)

            # Else branch
            if else_node:
                else_env = env.fork()
                for g in guards:
                    if g.var_name:
                        if g.guard_type == GuardType.ZERO:
                            else_env.update_state(g.var_name, VarState.GUARDED_NON_ZERO)
                        elif g.guard_type == GuardType.NON_ZERO:
                            else_env.update_state(g.var_name, VarState.DEFINITELY_ZERO, constant_value=0)
                yield from self._analyze_node(else_node, else_env, file_path, source_lines)

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
                op_text = (children[1].get("text") or "").strip()
                if op_text in ("/", "%"):
                    right_node = children[2]
                    right_text = (right_node.get("text") or "?").strip()

                    # Check Math.max(1, count) / Math.max(count, 1) guard
                    if self._is_math_max_guard(right_node):
                        self.record_suppression("math_max_guard")
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
                        # Non-zero constant
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
            yield from self._analyze_node(child, env, file_path, source_lines)

    @staticmethod
    def _is_math_max_guard(node: dict) -> bool:
        """Check for Math.max(1, x) or Math.max(x, 1) pattern in divisor."""
        ntype = node.get("type", "")
        if ntype == "method_invocation":
            text = (node.get("text") or "").replace(" ", "")
            if "Math.max(" in text or "max(" in text:
                args = next((c for c in node.get("children", []) if c.get("type") == "argument_list"), None)
                if args:
                    for arg in args.get("children", []):
                        val = evaluate_constant(arg)
                        if val is not None and isinstance(val, (int, float)) and val >= 1:
                            return True
        return False
