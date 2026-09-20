"""
PY_DIV_001 — Division by zero (Python)
---------------------------------------
Detects `/` and `//` arithmetic division operations where the divisor is
provably zero via literal constants, constant folding, or local variable state tracking.

High-confidence detection criteria:
- Literal numeric zeros: `0`, `0.0`, `-0.0`, `+0`, `0x0`, `0b0`, `False`
- Constant arithmetic folding to zero: `10 / (2 - 2)`, `10 / (0 * 5)`
- Variables assigned to zero: `z = 0; x / z`
- Divisors guarded inside a known-zero condition: `if z == 0: x / z`

Suppression / Safe criteria (provably safe or unestablished):
- Non-zero literals and expressions: `x / 2`, `x / (1 + 1)`
- Guarded divisions:
    - `if y != 0: x / y`
    - `if y > 0: x / y`
    - `if y: x / y`
    - `assert y != 0; x / y`
    - `if y == 0: return; x / y` (early-exit guard)
- Protected by exception handlers: `try: x / y except (ZeroDivisionError, Exception): ...`
- Unconstrained dynamic variables (`x / y` where `y` is an unknown parameter or function result).
"""

from __future__ import annotations

from typing import Dict, Iterator, List, Optional, Set

from ..analysis.constant_evaluator import ConstantEvaluator, evaluate_constant
from ..analysis.guard_analyzer import GuardAnalyzer, GuardType
from ..analysis.reachability_analyzer import ReachabilityAnalyzer
from ..analysis.variable_tracker import ScopeEnvironment, VariableStateTracker, VarInfo, VarState
from ..base_rule import BaseRule
from ..models import CandidateIssue

_SCOPE_NODES = {
    "function_definition",
    "async_function_definition",
    "lambda",
    "class_definition",
}


class PythonDivisionByZero(BaseRule):

    LANGUAGES = ["Python"]

    @property
    def rule_id(self) -> str:
        return "PY_DIV_001"

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
        yield from self._analyze_scope(ast, env, file_path, source_lines)

    def _analyze_scope(
        self,
        scope_node: dict,
        env: ScopeEnvironment,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:
        # Form parameters bind as dynamic variables (shadow outer scope)
        ntype = scope_node.get("type", "")
        if ntype in ("function_definition", "async_function_definition", "lambda"):
            params_node = next(
                (c for c in scope_node.get("children", []) if c.get("type") == "parameters"),
                None,
            )
            if params_node:
                for p in params_node.get("children", []):
                    ptype = p.get("type", "")
                    if ptype == "identifier":
                        pname = (p.get("text") or "").strip()
                        if pname:
                            env.set(pname, VarInfo(name=pname, state=VarState.UNKNOWN))
                    elif ptype == "default_parameter":
                        pkids = p.get("children", [])
                        if pkids and pkids[0].get("type") == "identifier":
                            pname = (pkids[0].get("text") or "").strip()
                            env.set(pname, VarInfo(name=pname, state=VarState.UNKNOWN))

        yield from self._analyze_block(scope_node, env, file_path, source_lines, is_scope_root=True)

    def _analyze_block(
        self,
        node: dict,
        env: ScopeEnvironment,
        file_path: str,
        source_lines: List[str],
        is_scope_root: bool = False,
        in_try_protected: bool = False,
    ) -> Iterator[CandidateIssue]:
        children = node.get("children", [])
        if not children and is_scope_root:
            return

        i = 0
        while i < len(children):
            child = children[i]
            ntype = child.get("type", "")

            # 1. Child scope (function, lambda, class)
            if ntype in _SCOPE_NODES:
                child_env = env.fork(scope_type=ntype)
                yield from self._analyze_scope(child, child_env, file_path, source_lines)
                i += 1
                continue

            # Unwrap expression_statement for assignment or augmented_assignment
            actual_node = child
            if ntype == "expression_statement":
                inner_kids = child.get("children", [])
                if inner_kids and inner_kids[0].get("type") in ("assignment", "augmented_assignment"):
                    actual_node = inner_kids[0]
                    ntype = actual_node.get("type", "")

            # 2. Assignment: var = <rhs>
            if ntype == "assignment":
                yield from self._check_divisions(actual_node, env, file_path, source_lines, in_try_protected)
                assign_kids = actual_node.get("children", [])
                if len(assign_kids) >= 3:
                    lhs = assign_kids[0]
                    rhs = assign_kids[-1]
                    VariableStateTracker.process_assignment(lhs, rhs, env)
                i += 1
                continue

            # 3. Augmented assignment: var += 1 -> kill state
            if ntype == "augmented_assignment":
                yield from self._check_divisions(actual_node, env, file_path, source_lines, in_try_protected)
                assign_kids = actual_node.get("children", [])
                if assign_kids:
                    vname = VariableStateTracker.extract_target_name(assign_kids[0])
                    if vname:
                        env.kill(vname)
                i += 1
                continue

            # 4. Assert guard: assert d != 0 / assert d
            if ntype == "assert_statement":
                yield from self._check_divisions(child, env, file_path, source_lines, in_try_protected)
                guards = GuardAnalyzer.analyze_assert(child)
                for g in guards:
                    if g.var_name and g.guard_type == GuardType.NON_ZERO:
                        env.update_state(g.var_name, VarState.GUARDED_NON_ZERO)
                i += 1
                continue

            # 5. If statement (branching and guards)
            if ntype == "if_statement":
                yield from self._analyze_if_statement(child, env, file_path, source_lines, in_try_protected)
                i += 1
                continue

            # 6. Try statement
            if ntype == "try_statement":
                yield from self._analyze_try_statement(child, env, file_path, source_lines)
                i += 1
                continue

            # 7. Loops (while / for)
            if ntype in ("while_statement", "for_statement"):
                loop_env = env.fork(scope_type="loop")
                yield from self._analyze_block(child, loop_env, file_path, source_lines, in_try_protected=in_try_protected)
                i += 1
                continue

            # 8. Division in statement
            if ntype == "binary_operator":
                op_kids = child.get("children", [])
                if len(op_kids) >= 3 and (op_kids[1].get("text") or "") in ("/", "//"):
                    yield from self._eval_division_node(child, env, file_path, source_lines, in_try_protected)
                    yield from self._check_divisions(op_kids[0], env, file_path, source_lines, in_try_protected)
                    i += 1
                    continue

            if ntype in ("expression_statement", "return_statement"):
                yield from self._check_divisions(child, env, file_path, source_lines, in_try_protected)
                i += 1
                continue

            if ntype in ("block", "with_statement", "else_clause", "elif_clause"):
                yield from self._analyze_block(child, env, file_path, source_lines, in_try_protected=in_try_protected)
                i += 1
                continue

            # Default
            yield from self._check_divisions(child, env, file_path, source_lines, in_try_protected)
            yield from self._analyze_block(child, env, file_path, source_lines, in_try_protected=in_try_protected)
            i += 1

    def _analyze_if_statement(
        self,
        if_node: dict,
        env: ScopeEnvironment,
        file_path: str,
        source_lines: List[str],
        in_try_protected: bool = False,
    ) -> Iterator[CandidateIssue]:
        children = if_node.get("children", [])
        # Extract condition node
        cond_node = next((c for c in children if c.get("type") not in ("if", "elif", ":", "block", "else_clause", "elif_clause")), None)
        if cond_node:
            yield from self._check_divisions(cond_node, env, file_path, source_lines, in_try_protected)

        guards = GuardAnalyzer.analyze_condition(cond_node) if cond_node else []

        then_block = next((c for c in children if c.get("type") == "block"), None)
        elif_clauses = [c for c in children if c.get("type") == "elif_clause"]
        else_clause = next((c for c in children if c.get("type") == "else_clause"), None)

        # 1. Then branch
        then_env = env.fork()
        for g in guards:
            if g.var_name:
                if g.guard_type == GuardType.NON_ZERO:
                    then_env.update_state(g.var_name, VarState.GUARDED_NON_ZERO)
                elif g.guard_type == GuardType.ZERO:
                    then_env.update_state(g.var_name, VarState.DEFINITELY_ZERO, constant_value=0)

        if then_block:
            yield from self._analyze_block(then_block, then_env, file_path, source_lines, in_try_protected=in_try_protected)

        # 2. Elif branches
        for elif_c in elif_clauses:
            elif_env = env.fork()
            yield from self._analyze_block(elif_c, elif_env, file_path, source_lines, in_try_protected=in_try_protected)

        # 3. Else branch
        if else_clause:
            else_env = env.fork()
            for g in guards:
                if g.var_name:
                    if g.guard_type == GuardType.ZERO:
                        else_env.update_state(g.var_name, VarState.GUARDED_NON_ZERO)
                    elif g.guard_type == GuardType.NON_ZERO:
                        else_env.update_state(g.var_name, VarState.DEFINITELY_ZERO, constant_value=0)
            yield from self._analyze_block(else_clause, else_env, file_path, source_lines, in_try_protected=in_try_protected)

        # 4. Early-exit guard clause handling:
        # e.g. `if d == 0: return` -> for the remainder of this scope, `d` is guarded non-zero!
        if guards and not elif_clauses and not else_clause and then_block:
            if ReachabilityAnalyzer._block_unconditionally_terminates(then_block):
                for g in guards:
                    if g.var_name and g.guard_type == GuardType.ZERO:
                        env.update_state(g.var_name, VarState.GUARDED_NON_ZERO)

        # 5. Merge branch facts if both then and else assign the exact same constant state
        if then_block and else_clause and not elif_clauses:
            for var_name, then_info in then_env.symbols.items():
                if var_name in else_env.symbols:
                    else_info = else_env.symbols[var_name]
                    if (
                        then_info.state == else_info.state == VarState.DEFINITELY_ZERO
                        and then_info.constant_value == else_info.constant_value == 0
                    ):
                        env.update_state(var_name, VarState.DEFINITELY_ZERO, constant_value=0)
                    elif (
                        then_info.state == else_info.state == VarState.DEFINITELY_NON_ZERO
                        or then_info.state == else_info.state == VarState.GUARDED_NON_ZERO
                    ):
                        env.update_state(var_name, VarState.GUARDED_NON_ZERO)

    def _analyze_try_statement(
        self,
        try_node: dict,
        env: ScopeEnvironment,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:
        children = try_node.get("children", [])
        try_block = next((c for c in children if c.get("type") == "block"), None)
        except_clauses = [c for c in children if c.get("type") == "except_clause"]

        is_zero_div_caught = False
        for ec in except_clauses:
            text = ec.get("text") or ""
            # Bare except or catches ZeroDivisionError / ArithmeticError / Exception
            if not ec.get("children") or len(ec.get("children", [])) <= 2 or any(e in text for e in ("ZeroDivisionError", "ArithmeticError", "Exception", "BaseException")):
                is_zero_div_caught = True
                break

        if try_block:
            try_env = env.fork()
            yield from self._analyze_block(try_block, try_env, file_path, source_lines, in_try_protected=is_zero_div_caught)

        for ec in except_clauses:
            ec_env = env.fork()
            yield from self._analyze_block(ec, ec_env, file_path, source_lines, in_try_protected=False)

    def _check_divisions(
        self,
        node: dict,
        env: ScopeEnvironment,
        file_path: str,
        source_lines: List[str],
        in_try_protected: bool = False,
    ) -> Iterator[CandidateIssue]:
        ntype = node.get("type", "")
        if ntype in _SCOPE_NODES:
            return

        if ntype == "binary_operator":
            children = node.get("children", [])
            if len(children) >= 3 and (children[1].get("text") or "") in ("/", "//"):
                yield from self._eval_division_node(node, env, file_path, source_lines, in_try_protected)
                yield from self._check_divisions(children[0], env, file_path, source_lines, in_try_protected)
                return

        for child in node.get("children", []):
            yield from self._check_divisions(child, env, file_path, source_lines, in_try_protected)

    def _eval_division_node(
        self,
        binop_node: dict,
        env: ScopeEnvironment,
        file_path: str,
        source_lines: List[str],
        in_try_protected: bool = False,
    ) -> Iterator[CandidateIssue]:
        if in_try_protected:
            self.record_suppression("protected_by_try_except")
            return

        children = binop_node.get("children", [])
        if len(children) < 3:
            return

        op_text = (children[1].get("text") or "/").strip()
        if op_text not in ("/", "//"):
            return

        right_node = children[2]
        right_text = (right_node.get("text") or "?").strip()

        # 1. Constant evaluation on divisor
        const_val = evaluate_constant(right_node)
        if const_val is not None:
            if isinstance(const_val, (int, float, bool)) and const_val == 0:
                self.record_syntax_match()
                yield self._make_issue(
                    node=binop_node,
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
            # Non-zero constant -> safe!
            self.record_suppression("non_zero_constant")
            return

        # 2. Check variable state in scope
        var_name = VariableStateTracker.extract_target_name(right_node)
        if var_name:
            var_info = env.get(var_name)
            if var_info:
                if var_info.is_definitely_zero:
                    self.record_syntax_match()
                    yield self._make_issue(
                        node=binop_node,
                        file_path=file_path,
                        source_lines=source_lines,
                        message=f"Division by zero: variable `{var_name}` is known to be 0 at this point.",
                        evidence={
                            "operator": op_text,
                            "variable": var_name,
                            "reason": "variable_assigned_zero",
                            "confidence": "high",
                        },
                        confidence="high",
                    )
                    return
                if var_info.is_definitely_non_zero:
                    self.record_suppression("guarded_or_non_zero_variable")
                    return

        # Unconstrained unknown dynamic variable (e.g. `x / y` where y is unknown):
        # By non-negotiable requirement: DO NOT flag unknown variables as division by zero!
        self.record_suppression("unestablished_divisor")
