"""
JS_AWA_001 — await inside a loop body (JavaScript)
---------------------------------------------------
Detects await_expression nodes that are direct descendants of a loop
body (for_statement, while_statement, for_in_statement, for_of_statement).
Sequential awaits inside loops process items one-at-a-time instead of
concurrently, causing unnecessary latency.

AST pattern (JavaScript):
  for_statement | while_statement | for_in_statement | for_of_statement
    └─ statement_block
         └─ ... (any depth)
              └─ await_expression   ← flagged
"""

from typing import Iterator, List, Set

from ..base_rule import BaseRule
from ..models import CandidateIssue

_LOOP_TYPES: Set[str] = {
    "for_statement",
    "while_statement",
    "do_statement",
    "for_in_statement",
    "for_of_statement",
}


class JavaScriptNoAwaitInLoop(BaseRule):

    LANGUAGES = ["JavaScript"]

    @property
    def rule_id(self) -> str:
        return "JS_AWA_001"

    @property
    def issue_type(self) -> str:
        return "await_in_loop"

    @property
    def severity(self) -> str:
        return "medium"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        # Build child→parent map for upward traversal
        parent_map: dict = {}
        self._build_parent_map(ast, parent_map)

        for node in self._walk(ast):
            if node["type"] != "await_expression":
                continue

            if not self._inside_loop(node, parent_map):
                continue

            # Don't flag if already inside an async function defined inside
            # the loop — that is intentional nesting, not sequential awaiting
            awaited_text = node.get("text", "await ...")
            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"`await` found inside a loop body.  "
                    f"This processes items sequentially.  "
                    f"Consider collecting promises and using Promise.all() instead."
                ),
                evidence={
                    "await_expression": awaited_text,
                },
            )

    # ------------------------------------------------------------------
    def _build_parent_map(self, node: dict, mapping: dict) -> None:
        for child in node.get("children", []):
            mapping[id(child)] = node
            self._build_parent_map(child, mapping)

    def _inside_loop(self, node: dict, parent_map: dict) -> bool:
        current = node
        while id(current) in parent_map:
            current = parent_map[id(current)]
            if current["type"] in _LOOP_TYPES:
                return True
            # Stop at function/method boundaries — await in a nested async
            # function or class method is its own concern, not sequential
            # awaiting in the outer loop.
            if current["type"] in (
                "function_declaration",
                "function_expression",
                "arrow_function",
                "method_definition",     # F-20 fix: class methods are boundaries
                "generator_function",
                "generator_function_declaration",
            ):
                return False
        return False

"""
JS_AWA_001 — await inside a loop body (JavaScript)
---------------------------------------------------
Detects `await_expression` nodes inside loop bodies (for, while, do-while,
for-of, for-in) where independent async tasks could be executed concurrently
using `Promise.all()`.

Suppression criteria (provably safe / intentional):
- Deliberate delay/sleep/polling loops: `await sleep(...)`, `await delay(...)`,
  `await timeout(...)`, `await wait(...)`, `await poll(...)`, `await tick(...)`
- Dependent iterations (e.g. cursor pagination: `page = await getPage(page.nextCursor)`)
- Nested async callbacks inside the loop

Confidence calibration:
- HIGH: Independent items in for-of or for-loop (e.g. `for (const id of ids) { await process(id); }`) in production code.
- MEDIUM: General await inside loop with uncertain dependency.
- LOW: Test file sequential test executions or retry loops.
"""

import re
from typing import Iterator, List, Optional, Set

from ..base_rule import BaseRule
from ..models import CandidateIssue

_LOOP_TYPES: Set[str] = {
    "for_statement",
    "while_statement",
    "do_statement",
    "for_in_statement",
    "for_of_statement",
}

_DELAY_FUNCTION_RE = re.compile(
    r'\b(?:sleep|delay|wait|timeout|settimeout|settimeoutasync|poll|tick|nexttick|retry|backoff)\b',
    re.IGNORECASE,
)


def _is_intentional_delay_or_poll(awaited_text: str) -> bool:
    return bool(_DELAY_FUNCTION_RE.search(awaited_text))


def _has_dependent_assignment(node: dict, parent_map: dict) -> bool:
    """Check if result of await is assigned to a variable controlling the loop."""
    parent = parent_map.get(id(node))
    if parent and parent.get("type") in ("assignment_expression", "variable_declarator"):
        pchildren = parent.get("children", [])
        if pchildren and pchildren[0].get("type") == "identifier":
            var_name = (pchildren[0].get("text") or "").strip().lower()
            if any(k in var_name for k in ("cursor", "next", "page", "token", "offset", "chunk", "buffer")):
                return True
    return False


class JavaScriptNoAwaitInLoop(BaseRule):

    LANGUAGES = ["JavaScript"]

    @property
    def rule_id(self) -> str:
        return "JS_AWA_001"

    @property
    def issue_type(self) -> str:
        return "await_in_loop"

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
        is_test = self._is_test_file(file_path)

        for node in self._walk(ast):
            if node.get("type") != "await_expression":
                continue

            loop_node = self._find_enclosing_loop(node, parent_map)
            if not loop_node:
                continue

            self.record_syntax_match()

            awaited_text = (node.get("text") or "await ...").strip()

            # 1. Deliberate delay, sleep, timeout, or polling loop -> suppress
            if _is_intentional_delay_or_poll(awaited_text):
                self.record_suppression("intentional_delay_or_polling_loop")
                continue

            # 2. Dependent pagination / cursor loop -> suppress
            if _has_dependent_assignment(node, parent_map):
                self.record_suppression("dependent_loop_iteration_pagination")
                continue

            confidence = "low" if is_test else "medium"

            # Check if loop is a for / for-of / for-in loop over independent collection in production code
            if loop_node.get("type") in ("for_of_statement", "for_in_statement", "for_statement") and not is_test:
                confidence = "high"


            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"Sequential `await` in loop body processes items one by one. "
                    f"If iterations are independent, use `Promise.all()` for concurrent execution."
                ),
                evidence={
                    "await_expression": awaited_text,
                    "loop_type": loop_node.get("type", "unknown_loop"),
                    "confidence": confidence,
                    "reason": f"Sequential `await` ({awaited_text}) inside `{loop_node.get('type')}`.",
                },
                confidence=confidence,
            )

    def _find_enclosing_loop(self, node: dict, parent_map: dict) -> Optional[dict]:
        curr = node
        while id(curr) in parent_map:
            curr = parent_map[id(curr)]
            if curr.get("type") in _LOOP_TYPES:
                return curr
            if curr.get("type") in (
                "function_declaration", "function_expression", "arrow_function",
                "method_definition", "generator_function", "generator_function_declaration",
            ):
                return None
        return None

