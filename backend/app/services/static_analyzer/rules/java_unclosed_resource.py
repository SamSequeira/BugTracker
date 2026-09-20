"""
JAVA_RES_001 — Unclosed Resource (Java)
---------------------------------------
Detects Java I/O, Socket, or JDBC resource allocations that are not
managed by try-with-resources, explicit `.close()`, or transferred upon return.

High-confidence detection criteria:
- Known resource classes (`FileInputStream`, `BufferedReader`, `Socket`, `Connection`, etc.)
  instantiated via `new` and never closed or returned in scope.

Suppression criteria (provably safe / managed):
- Try-with-resources: `try (FileInputStream in = new FileInputStream(f)) { ... }`
- Explicit close in method: `stream.close();`
- Cleanup in finally block: `finally { stream.close(); }`
- Returned resources: `return stream;` or `return new FileInputStream(f);`
"""

from __future__ import annotations

import re
from typing import Iterator, List, Optional, Set

from ..analysis.resource_tracker import (
    JAVA_RESOURCE_CLASSES,
    ResourceLifecycleTracker,
    ResourceState,
)
from ..analysis.variable_tracker import VariableStateTracker
from ..base_rule import BaseRule
from ..models import CandidateIssue


def _extract_type_name(object_creation: dict) -> str:
    """Extracts simple class name from an object_creation_expression."""
    for child in object_creation.get("children", []):
        if child.get("type") == "type_identifier":
            return (child.get("text") or "").strip()
        if child.get("type") == "scoped_type_identifier":
            text = (child.get("text") or "").strip()
            return text.split(".")[-1]
    text = object_creation.get("text") or ""
    m = re.search(r'new\s+(?:[\w.]*\.)?(\w+)\s*\(', text)
    return m.group(1) if m else ""


class JavaUnclosedResource(BaseRule):

    LANGUAGES = ["Java"]

    @property
    def rule_id(self) -> str:
        return "JAVA_RES_001"

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
            if node.get("type") != "object_creation_expression":
                continue

            class_name = _extract_type_name(node)
            if not ResourceLifecycleTracker.is_java_resource_type(class_name):
                continue

            # 1. Check try-with-resources
            if ResourceLifecycleTracker.is_inside_java_try_with_resources(node, parent_map):
                self.record_suppression("inside_try_with_resources")
                continue

            # 2. Check parent node
            parent = parent_map.get(id(node))
            if parent:
                # Direct return: return new FileInputStream(file);
                if parent.get("type") == "return_statement":
                    self.record_suppression("returned_directly")
                    continue

                # Local variable declaration: FileInputStream fis = new FileInputStream(file);
                var_name = None
                if parent.get("type") == "variable_declarator":
                    kids = parent.get("children", [])
                    if kids and kids[0].get("type") == "identifier":
                        var_name = (kids[0].get("text") or "").strip()
                elif parent.get("type") == "assignment_expression":
                    kids = parent.get("children", [])
                    if kids and kids[0].get("type") == "identifier":
                        var_name = (kids[0].get("text") or "").strip()

                if var_name:
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
                            message=f"Resource `{var_name}` of type `{class_name}` is closed only conditionally without a `finally` block.",
                            evidence={
                                "variable": var_name,
                                "resource_type": class_name,
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
                            message=f"Resource `{var_name}` of type `{class_name}` is never closed or returned.",
                            evidence={
                                "variable": var_name,
                                "resource_type": class_name,
                                "lifecycle_status": "definitely_leaked",
                                "confidence": "high",
                            },
                            confidence="high",
                        )
                        continue

            # Bare instantiation not assigned or returned
            self.record_syntax_match()
            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=f"`{class_name}` created outside try-with-resources or without variable handle to close it.",
                evidence={
                    "resource_type": class_name,
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
            if curr.get("type") in ("method_declaration", "constructor_declaration", "class_body"):
                return curr
        return curr
