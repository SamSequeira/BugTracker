"""
JS_AWA_001 — await inside a loop body (JavaScript)
---------------------------------------------------
Detects `await_expression` nodes inside loop bodies (for, while, do-while,
for-of, for-in) where independent async tasks could be executed concurrently
using `Promise.all()`.

Suppression criteria (provably safe / intentional sequential execution):
1. `for await (... of ...)` streaming consumption loops.
2. Deliberate delays, sleep, timeouts, polling, and retry loops:
   `await sleep(...)`, `await delay(...)`, `await wait(...)`, `await retry(...)`.
3. Browser automation & UI orchestration: `await page.click(...)`, `await locator.waitFor(...)`.
4. Database transactions & mutations: `await tx.query(...)`, `await client.commit(...)`.
5. I/O streams & cursors: `await reader.read()`, `await cursor.next()`.
6. Interactive CLI prompts & User input: `await prompt(...)`, `await rl.question(...)`.
7. Dependent pagination / accumulator loops: `cursor = await fetchNextPage(cursor)` in `while (cursor)`.
"""

from __future__ import annotations

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

# 1. Delay / Sleep / Polling / Mutex Call
_DELAY_RE = re.compile(
    r'^\s*(?:await\s+)?(?:(?:window\.)?(?:sleep|delay|wait|setTimeout|setInterval|nextTick)|(?:\w+\.)?(?:acquire|lock|unlock|release))\s*\(',
    re.IGNORECASE,
)

# 2. Browser Automation
_BROWSER_AUTOMATION_RE = re.compile(
    r'\b(?:page|element|locator|browser|driver|frame)\.'
    r'(?:click|type|fill|press|hover|waitFor|waitForSelector|waitForTimeout|goto|'
    r'screenshot|evaluate|selectOption|focus|check|uncheck)\s*\(',
    re.IGNORECASE,
)

# 3. Database Transactions
_DB_TRANSACTION_RE = re.compile(
    r'\b(?:tx|transaction|client|session|entityManager)\.'
    r'(?:query|execute|commit|rollback|insert|update|delete|save|transaction|raw)\s*\(',
    re.IGNORECASE,
)

# 4. Streams & Cursors
_STREAM_IO_RE = re.compile(
    r'\b(?:reader|writer|stream|ws|socket|cursor|channel)\.'
    r'(?:read|write|send|close|pipe|next|fetchNext|readChunk)\s*\(',
    re.IGNORECASE,
)

# 5. Prompts
_PROMPT_RE = re.compile(
    r'^\s*(?:await\s+)?(?:prompt|inquirer\.\w+|rl\.question|confirm)\s*\(',
    re.IGNORECASE,
)

_FUNCTION_BARRIER_TYPES: Set[str] = {
    "function_declaration",
    "function_expression",
    "arrow_function",
    "generator_function_declaration",
    "generator_function",
}


def _is_intentional_sequential_call(awaited_text: str) -> bool:
    if _DELAY_RE.search(awaited_text):
        return True
    if _BROWSER_AUTOMATION_RE.search(awaited_text):
        return True
    if _DB_TRANSACTION_RE.search(awaited_text):
        return True
    if _STREAM_IO_RE.search(awaited_text):
        return True
    if _PROMPT_RE.search(awaited_text):
        return True
    return False


def _is_for_await_loop(loop_node: dict) -> bool:
    """Detects specifically `for await (const x of iterable)` loops."""
    if loop_node.get("type") == "for_await_of_statement":
        return True
    text = (loop_node.get("text") or "").lstrip()
    return text.startswith("for await") or text.startswith("for (await")


def _walk_tree(root: dict):
    yield root
    for child in root.get("children", []):
        yield from _walk_tree(child)


def _extract_cond_vars(enclosing_loop: dict) -> set[str]:
    children = enclosing_loop.get("children", [])
    for c in children:
        if c.get("type") in ("parenthesized_expression", "binary_expression", "identifier"):
            cond_text = c.get("text") or ""
            vars_found = set(re.findall(r'\b[a-zA-Z_$][a-zA-Z0-9_$]*\b', cond_text))
            vars_found -= {"true", "false", "null", "undefined"}
            if vars_found:
                return vars_found
    text = enclosing_loop.get("text") or ""
    m = re.search(r'while\s*\((.*?)\)', text)
    if m:
        vars_found = set(re.findall(r'\b[a-zA-Z_$][a-zA-Z0-9_$]*\b', m.group(1)))
        vars_found -= {"true", "false", "null", "undefined"}
        return vars_found
    return set()


def _is_pagination_or_accumulator(node: dict, enclosing_loop: dict, parent_map: dict) -> bool:
    """
    Check if the await result updates the loop condition variable (pagination/accumulator)
    such as `while (cursor) { cursor = await fetchNext(cursor); }` or `while (page < total) { page = await ... }`
    or if the loop condition is updated in the loop body (e.g. retry loops with decrements).
    """
    loop_type = enclosing_loop.get("type", "")
    if loop_type not in ("while_statement", "do_statement"):
        return False

    cond_vars = _extract_cond_vars(enclosing_loop)
    if not cond_vars:
        return False

    curr = node
    for _ in range(5):
        p = parent_map.get(id(curr))
        if not p:
            break
        if p.get("type") in ("assignment_expression", "assignment", "variable_declarator"):
            kids = p.get("children", [])
            if kids:
                var_name = (kids[0].get("text") or "").strip()
                if var_name in cond_vars:
                    return True
        curr = p

    for n in _walk_tree(enclosing_loop):
        if n.get("type") in ("update_expression", "augmented_assignment_expression"):
            t = n.get("text") or ""
            for cv in cond_vars:
                if cv in t:
                    return True
        if n.get("type") in ("assignment_expression", "assignment"):
            kids = n.get("children", [])
            if kids:
                var_name = (kids[0].get("text") or "").strip()
                if var_name in cond_vars:
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
        if self._is_test_file(file_path):
            return

        parent_map: dict = {}
        self._build_parent_map(ast, parent_map)

        for node in self._walk(ast):
            if node.get("type") != "await_expression":
                continue

            # Find enclosing loop
            enclosing_loop = self._find_enclosing_loop(node, parent_map)
            if not enclosing_loop:
                continue

            # Exclude for-await-of loops
            if _is_for_await_loop(enclosing_loop):
                self.record_suppression("for_await_loop")
                continue

            # Check pagination / accumulator loops / retry loops
            if _is_pagination_or_accumulator(node, enclosing_loop, parent_map):
                self.record_suppression("pagination_accumulator_loop")
                continue

            # Check awaited text
            snippet = self._snippet(node, source_lines)
            if _is_intentional_sequential_call(snippet):
                self.record_suppression("intentional_sequential_operation")
                continue

            loop_type = enclosing_loop.get("type", "")
            conf = "high" if loop_type in ("for_of_statement", "for_in_statement", "for_statement") else "medium"

            self.record_syntax_match()
            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    "`await` used inside a loop causes sequential execution. "
                    "Consider using `Promise.all()` if iterations are independent."
                ),
                evidence={
                    "awaited_expression": snippet,
                    "loop_type": loop_type,
                    "confidence": conf,
                },
                confidence=conf,
            )

    @staticmethod
    def _find_enclosing_loop(node: dict, parent_map: dict) -> Optional[dict]:
        curr = node
        while id(curr) in parent_map:
            curr = parent_map[id(curr)]
            if curr.get("type") in _FUNCTION_BARRIER_TYPES:
                return None
            if curr.get("type") in _LOOP_TYPES:
                return curr
        return None
