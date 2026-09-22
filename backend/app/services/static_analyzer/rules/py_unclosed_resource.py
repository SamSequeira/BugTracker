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
"""
PY_RES_001 — open() called outside a with-statement (Python)
-------------------------------------------------------------
Detects calls to the builtin open() that are NOT inside a
with_statement.  Files opened this way may leak handles when an
exception is raised before .close() is called.

AST pattern (Python):
  assignment  OR  expression_statement
    └─ call
         └─ identifier  text="open"

The rule checks the ancestor chain: if none of the ancestors of the
call node is a "with_statement", the call is flagged.
"""

from typing import Iterator, List

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
        return "high"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        # Build a child→parent map so we can walk upward
        parent_map: dict = {}
        self._build_parent_map(ast, parent_map)

        for node in self._walk(ast):
            if node["type"] != "call":
                continue

            children = node.get("children", [])
            if not children:
                continue

            # The function being called must be the bare identifier "open"
            func_node = children[0]
            if func_node["type"] != "identifier":
                continue
            if func_node.get("text", "") != "open":
                continue

            # Walk ancestors — safe if any is a with_statement
            if self._inside_with(node, parent_map):
                continue

            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    "open() called outside a `with` statement.  "
                    "Use `with open(...) as f:` to guarantee the file is "
                    "closed even when an exception occurs."
                ),
                evidence={"call_text": node.get("text", "open(...)")},
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_parent_map(self, node: dict, mapping: dict) -> None:
        for child in node.get("children", []):
            mapping[id(child)] = node
            self._build_parent_map(child, mapping)

    def _inside_with(self, node: dict, parent_map: dict) -> bool:
        current = node
        while id(current) in parent_map:
            current = parent_map[id(current)]
            if current["type"] == "with_statement":
                return True
        return False

"""
PY_RES_001 — open() called outside a with-statement (Python)
-------------------------------------------------------------
Detects calls to builtin `open()` that are NOT managed by a `with` statement
and are not guaranteed to be closed or transferred.

Suppression criteria (provably safe / intentional):
- Inside `with_statement` (e.g. `with open(p) as f:`)
- Returned directly to caller (`return open(p)`)
- Assigned to variable `f` and explicitly closed in scope (`f.close()`) or `finally`
- Returned variable (`return f`)

Confidence calibration:
- HIGH: Resource assigned to local variable, manipulated, and scope exits without close/return.
- MEDIUM: Resource passed into external consumer function where ownership is ambiguous.
- LOW: Ambiguous one-line usage in test/fixture context.
"""

from typing import Iterator, List, Optional, Set

from ..base_rule import BaseRule
from ..models import CandidateIssue


def _find_enclosing_scope(node: dict, parent_map: dict) -> Optional[dict]:
    curr = node
    while id(curr) in parent_map:
        curr = parent_map[id(curr)]
        if curr.get("type") in ("function_definition", "async_function_definition", "module"):
            return curr
    return None


def _is_returned_or_closed(
    scope_node: dict,
    var_name: str,
) -> str:
    """
    Scans scope AST for lifecycle actions on var_name:
    Returns 'CLOSED', 'RETURNED', 'TRANSFERRED', or 'UNCLOSED'.
    """
    if not var_name or not scope_node:
        return "UNCLOSED"

    import re

    is_closed = False
    is_returned = False
    is_transferred = False

    def _walk_scope(curr: dict):
        nonlocal is_closed, is_returned, is_transferred
        ntype = curr.get("type", "")
        text = (curr.get("text") or "").strip()

        # Check f.close() call
        if ntype == "call":
            if text.startswith(f"{var_name}.close(") or f"{var_name}.close()" in text:
                is_closed = True
            elif re.search(rf'\(\s*{re.escape(var_name)}\s*\)|,\s*{re.escape(var_name)}|{re.escape(var_name)}\s*,', text):
                is_transferred = True

        # Check return f (must return the resource itself, NOT f.read())
        if ntype == "return_statement":
            # Strip 'return'
            ret_expr = text[6:].strip() if text.startswith("return") else text
            # Ensure it is returning the resource identifier itself or in tuple, not f.read()
            if not ret_expr.startswith(f"{var_name}.") and re.search(rf'\b{re.escape(var_name)}\b', ret_expr):
                is_returned = True

        for child in curr.get("children", []):
            _walk_scope(child)

    _walk_scope(scope_node)

    if is_returned:
        return "RETURNED"
    if is_closed:
        return "CLOSED"
    if is_transferred:

        return "TRANSFERRED"
    return "UNCLOSED"


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
            if node.get("type") != "call":
                continue

            children = node.get("children", [])
            if not children:
                continue

            func_node = children[0]
            if func_node.get("type") != "identifier":
                continue
            if (func_node.get("text") or "") != "open":
                continue

            self.record_syntax_match()

            # 1. Inside with_statement -> suppress
            if self._inside_with(node, parent_map):
                self.record_suppression("managed_by_with_statement")
                continue

            parent = parent_map.get(id(node))
            ptype = parent.get("type", "") if parent else ""

            # 2. Direct return: return open(...) -> ownership transferred to caller
            if ptype == "return_statement":
                self.record_suppression("returned_directly_to_caller")
                continue

            # 3. Variable assignment tracking: f = open(...)
            var_name = ""
            if ptype == "assignment":
                pchildren = parent.get("children", [])
                if pchildren and pchildren[0].get("type") == "identifier":
                    var_name = (pchildren[0].get("text") or "").strip()

            scope = _find_enclosing_scope(node, parent_map)
            lifecycle = _is_returned_or_closed(scope, var_name) if scope and var_name else "UNCLOSED"

            if lifecycle == "RETURNED":
                self.record_suppression(f"variable_{var_name}_returned_to_caller")
                continue

            if lifecycle == "CLOSED":
                self.record_suppression(f"variable_{var_name}_explicitly_closed")
                continue

            confidence = "high"
            if lifecycle == "TRANSFERRED":
                confidence = "medium"
            if is_test:
                confidence = "low" if confidence == "medium" else "medium"

            snippet_node = parent if ptype in ("assignment", "expression_statement") else node
            call_text = (node.get("text") or "open(...)").strip()

            yield self._make_issue(
                node=snippet_node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"`open()` called outside `with` statement and resource `{var_name or 'file'}` "
                    f"is not guaranteed to be closed on error paths."
                ),
                evidence={
                    "call": call_text,
                    "assigned_variable": var_name or None,
                    "lifecycle_status": lifecycle,
                    "confidence": confidence,
                    "reason": f"File opened with `{call_text}` outside `with` and lifecycle status is {lifecycle}.",
                },
                confidence=confidence,
            )

    def _inside_with(self, node: dict, parent_map: dict) -> bool:
        curr = node
        while id(curr) in parent_map:
            curr = parent_map[id(curr)]
            if curr.get("type") == "with_statement":
                return True
        return False

