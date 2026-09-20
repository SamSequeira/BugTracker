"""
JS_PROMISE_001 — Suspicious / Unhandled Promise (JavaScript)
------------------------------------------------------------
Detects known Promise-returning operations (e.g. `fetch(...)`, `Promise.all(...)`,
`axios.get(...)`, `fs.promises.*`) executed as bare expression statements without
`await`, `return`, variable assignment, or `.catch()` error handling.
Unhandled promises often cause silent background network/IO failures and unhandled rejection crashes.
"""

from __future__ import annotations

import re
from typing import Iterator, List, Optional

from ..base_rule import BaseRule
from ..models import CandidateIssue

_KNOWN_PROMISE_CALLEES = re.compile(
    r'^(?:fetch|Promise\.(?:all|race|allSettled|any)|axios\.(?:get|post|put|delete|patch|head|options)|fs\.promises\.\w+)$',
)


class JavaScriptUnhandledPromise(BaseRule):

    LANGUAGES = ["JavaScript"]

    @property
    def rule_id(self) -> str:
        return "JS_PROMISE_001"

    @property
    def issue_type(self) -> str:
        return "unhandled_promise"

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
            # Target expression_statement wrapping a call_expression
            if node.get("type") != "expression_statement":
                continue

            children = node.get("children", [])
            if not children:
                continue

            inner_expr = children[0]
            if inner_expr.get("type") not in ("call_expression", "call"):
                continue

            # Extract the actual callee expression of the outer call
            call_kids = inner_expr.get("children", [])
            if not call_kids:
                continue

            callee_node = call_kids[0]
            callee_text = (callee_node.get("text") or "").strip()

            # Check if outer callee is chained with .catch() or .then()
            if callee_text.endswith(".catch") or callee_text.endswith(".then"):
                self.record_suppression("chained_with_then_or_catch")
                continue

            # Check if outer callee matches known Promise-returning APIs
            if not _KNOWN_PROMISE_CALLEES.match(callee_text):
                continue

            # Check if wrapped in await
            parent = parent_map.get(id(inner_expr))
            if parent and parent.get("type") == "await_expression":
                self.record_suppression("awaited")
                continue

            snippet = self._snippet(node, source_lines)
            self.record_syntax_match()
            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"Promise-returning operation `{snippet}` is not awaited, returned, "
                    f"or handled with `.catch()`. Unhandled rejections may cause crashes."
                ),
                evidence={
                    "expression": snippet,
                    "callee": callee_text,
                    "reason": "unhandled_promise_in_statement_position",
                    "confidence": "high",
                },
                confidence="high",
            )
