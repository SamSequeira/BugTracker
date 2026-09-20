"""
PY_RES_001 — Unclosed Resource (Python)
---------------------------------------
Detects unmanaged `open()` resource allocations that are not guaranteed
to be closed, transferred, or managed by a `with` statement.

High-confidence detection criteria:
- `f = open(...)` assigned to a local variable and scope exits without `.close()` or `return`.
- Resource opened and closed only conditionally without a `finally` block.

Suppression criteria (provably safe / managed):
- Context management: `with open(...) as f:`
- Direct returns: `return open(...)` or `f = open(...); return f`
- Explicit closure: `f = open(...); ... f.close()`
- Safe cleanup in `finally: f.close()`
"""

from __future__ import annotations

from typing import Iterator, List, Optional, Set

from ..analysis.resource_tracker import ResourceLifecycleTracker, ResourceState
from ..analysis.variable_tracker import ScopeEnvironment, VariableStateTracker, VarInfo, VarState
from ..base_rule import BaseRule
from ..models import CandidateIssue


class PythonUnclosedResource(BaseRule):

    LANGUAGES = ["Python"]

    @property
    def rule_id(self) -> str:
        return "PY_RES_001"

    @property
    def issue_type(self) -> str:
        return "unclosed_resource"

    @property
    def severity(self) -> str:
        return "medium"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:
        parent_map: dict = {}
        self._build_parent_map(ast, parent_map)

        for node in self._walk(ast):
            # Check call to open()
            if not ResourceLifecycleTracker.is_python_open_call(node):
                continue

            # 1. Safe if inside `with` context manager
            if ResourceLifecycleTracker.is_inside_python_with(node, parent_map):
                self.record_suppression("inside_with_statement")
                continue

            # 2. Check parent node: returned directly or assigned to variable
            parent = parent_map.get(id(node))
            if parent:
                # Returned directly: return open(...)
                if parent.get("type") == "return_statement":
                    self.record_suppression("returned_directly")
                    continue

                # Assigned to variable: f = open(...)
                if parent.get("type") == "assignment":
                    lhs = parent.get("children", [{}])[0]
                    var_name = VariableStateTracker.extract_target_name(lhs)
                    if var_name:
                        # Find enclosing function / module scope
                        scope_root = self._find_enclosing_scope(parent, parent_map)
                        status = ResourceLifecycleTracker.analyze_scope_for_allocation(scope_root, node, var_name)

                        if status in (ResourceState.DEFINITELY_CLOSED, ResourceState.TRANSFERRED):
                            self.record_suppression("safely_closed_or_transferred")
                            continue

                        if status == ResourceState.POTENTIALLY_LEAKED:
                            self.record_syntax_match()
                            yield self._make_issue(
                                node=parent,
                                file_path=file_path,
                                source_lines=source_lines,
                                message=f"Resource `{var_name}` opened at this point is only conditionally closed without a `finally` block.",
                                evidence={
                                    "variable": var_name,
                                    "lifecycle_status": "potentially_leaked",
                                    "confidence": "medium",
                                },
                                confidence="medium",
                            )
                            continue

                        if status == ResourceState.DEFINITELY_LEAKED:
                            self.record_syntax_match()
                            yield self._make_issue(
                                node=parent,
                                file_path=file_path,
                                source_lines=source_lines,
                                message=f"Resource `{var_name}` opened via `open()` called outside `with` statement is never closed or returned.",
                                evidence={
                                    "variable": var_name,
                                    "lifecycle_status": "definitely_leaked",
                                    "confidence": "high",
                                },
                                confidence="high",
                            )
                            continue

            # Bare open() not assigned or returned
            self.record_syntax_match()
            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message="`open()` called without context manager (`with`) or variable handle to close it.",
                evidence={
                    "call": "bare_open",
                    "lifecycle_status": "unmanaged_allocation",
                    "confidence": "high",
                },
                confidence="high",
            )

    @staticmethod
    def _find_enclosing_scope(node: dict, parent_map: dict) -> dict:
        curr = node
        while id(curr) in parent_map:
            curr = parent_map[id(curr)]
            if curr.get("type") in ("function_definition", "async_function_definition", "module"):
                return curr
        return curr
