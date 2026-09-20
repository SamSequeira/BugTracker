"""
JAVA_NULL_001 — Obvious Null Dereference (Java)
-----------------------------------------------
Detects method calls and field dereferences on variables that are provably `null`
at the point of invocation via local variable tracking.

High-confidence detection criteria:
- Variable explicitly initialized or assigned to `null` (`String s = null; s.length();`)
  without subsequent non-null reassignment or guard checks.

Suppression criteria (provably safe / guarded):
- Assigned non-null value: `String s = "hello"; s.length();` or `s = new Object();`
- Guarded by null check: `if (s != null) { s.length(); }`
- Protected by early exit: `if (s == null) { return; } s.length();`
"""

from __future__ import annotations

from typing import Iterator, List, Optional

from ..analysis.guard_analyzer import GuardAnalyzer, GuardType
from ..analysis.reachability_analyzer import ReachabilityAnalyzer
from ..analysis.variable_tracker import ScopeEnvironment, VariableStateTracker, VarInfo, VarState
from ..base_rule import BaseRule
from ..models import CandidateIssue


class JavaNullDereference(BaseRule):

    LANGUAGES = ["Java"]

    @property
    def rule_id(self) -> str:
        return "JAVA_NULL_001"

    @property
    def issue_type(self) -> str:
        return "null_dereference"

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

        # 1. Local variable declaration: String s = null;
        if ntype == "local_variable_declaration":
            for decl in node.get("children", []):
                if decl.get("type") == "variable_declarator":
                    kids = decl.get("children", [])
                    if len(kids) >= 3:
                        lhs = kids[0]
                        rhs = kids[-1]
                        VariableStateTracker.process_assignment(lhs, rhs, env)

        # 2. Assignment expression: s = null;
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
                    if g.guard_type == GuardType.NON_NULL:
                        then_env.update_state(g.var_name, VarState.GUARDED_NON_NULL)
                    elif g.guard_type == GuardType.NULL:
                        then_env.update_state(g.var_name, VarState.DEFINITELY_NULL)

            if then_node:
                yield from self._analyze_node(then_node, then_env, file_path, source_lines)

            # Else branch
            if else_node:
                else_env = env.fork()
                for g in guards:
                    if g.var_name:
                        if g.guard_type == GuardType.NULL:
                            else_env.update_state(g.var_name, VarState.GUARDED_NON_NULL)
                        elif g.guard_type == GuardType.NON_NULL:
                            else_env.update_state(g.var_name, VarState.DEFINITELY_NULL)
                yield from self._analyze_node(else_node, else_env, file_path, source_lines)

            # Early exit in then-branch protects subsequent statements
            if guards and not else_node and then_node:
                if ReachabilityAnalyzer._block_unconditionally_terminates(then_node):
                    for g in guards:
                        if g.var_name and g.guard_type == GuardType.NULL:
                            env.update_state(g.var_name, VarState.GUARDED_NON_NULL)
            return

        # 4. Method invocation on a variable: s.length()
        if ntype == "method_invocation":
            children = node.get("children", [])
            if children:
                target_node = children[0]
                target_name = VariableStateTracker.extract_target_name(target_node)
                if target_name:
                    vinfo = env.get(target_name)
                    if vinfo and vinfo.is_definitely_null:
                        snippet = self._snippet(node, source_lines)
                        self.record_syntax_match()
                        yield self._make_issue(
                            node=node,
                            file_path=file_path,
                            source_lines=source_lines,
                            message=f"Definite null dereference: variable `{target_name}` is null when calling `{snippet}`.",
                            evidence={
                                "variable": target_name,
                                "invocation": snippet,
                                "reason": "variable_assigned_null",
                                "confidence": "high",
                            },
                            confidence="high",
                        )

        # 5. Field access on a variable: s.field
        if ntype == "field_access":
            children = node.get("children", [])
            if children:
                target_node = children[0]
                target_name = VariableStateTracker.extract_target_name(target_node)
                if target_name:
                    vinfo = env.get(target_name)
                    if vinfo and vinfo.is_definitely_null:
                        snippet = self._snippet(node, source_lines)
                        self.record_syntax_match()
                        yield self._make_issue(
                            node=node,
                            file_path=file_path,
                            source_lines=source_lines,
                            message=f"Definite null dereference: variable `{target_name}` is null when accessing `{snippet}`.",
                            evidence={
                                "variable": target_name,
                                "field_access": snippet,
                                "reason": "variable_assigned_null",
                                "confidence": "high",
                            },
                            confidence="high",
                        )

        for child in node.get("children", []):
            yield from self._analyze_node(child, env, file_path, source_lines)
