"""
JS_AWA_001 — await inside a loop body (JavaScript)
---------------------------------------------------
Detects `await_expression` nodes inside loop bodies (for, while, do-while,
for-of, for-in) where independent async tasks could be executed concurrently
using `Promise.all()`.

Suppression criteria (provably safe / intentional sequential execution):
1. `for await (... of ...)` streaming consumption loops.
2. Deliberate delays, sleep, timeouts, polling, and retry loops:
   `await sleep(...)`, `await delay(...)`, `await wait(...)`, `await poll(...)`, `await retry(...)`.
3. Browser automation & UI orchestration (Puppeteer, Playwright, Selenium):
   `await page.click(...)`, `await page.goto(...)`, `await element.type(...)`, `await locator.waitFor(...)`.
4. Database transactions, mutations & locks:
   `await tx.query(...)`, `await db.insert(...)`, `await client.commit(...)`, `await lock.acquire(...)`.
5. I/O streams, cursors & socket writes:
   `await reader.read()`, `await stream.write()`, `await cursor.next()`, `await ws.send()`.
6. Interactive CLI prompts & User input:
   `await prompt(...)`, `await inquirer.prompt(...)`, `await rl.question(...)`.
7. Dependent iterations & Accumulators:
   `acc = await step(acc)`, `page = await getPage(page.nextCursor)`, `token = await fetchToken(token)`.
8. Test files (*.test.js, *.spec.js, __tests__) where sequential assertions are standard.
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

# 1. Delay / Sleep / Polling / Backoff
_DELAY_RE = re.compile(
    r'\b(?:sleep|delay|wait|timeout|settimeout|settimeoutasync|poll|tick|nexttick|retry|backoff|throttle|cooldown)\b',
    re.IGNORECASE,
)

# 2. Browser Automation (Puppeteer / Playwright / Selenium / Cypress)
_BROWSER_AUTOMATION_RE = re.compile(
    r'\b(?:page|element|locator|browser|driver|frame|cdpsession|frameLocator)\.'
    r'(?:click|type|fill|press|hover|waitFor|waitForSelector|waitForTimeout|goto|'
    r'screenshot|evaluate|selectOption|focus|check|uncheck|setInputFiles|dblclick)\b',
    re.IGNORECASE,
)

# 3. Database Transactions, Mutations & Locks
_DB_TRANSACTION_RE = re.compile(
    r'\b(?:tx|transaction|client|db|connection|pool|session|entityManager|repo|repository|knex|prisma|sequelize)\.'
    r'(?:query|execute|commit|rollback|insert|update|delete|save|findOne|find|select|transaction|raw)\b',
    re.IGNORECASE,
)

# 4. Mutexes, Locks, Semaphores, Queues
_LOCK_MUTEX_RE = re.compile(
    r'\b(?:lock|mutex|semaphore|queue|limiter|rateLimiter)\.'
    r'(?:acquire|release|runExclusive|take|pop|enqueue|dequeue|schedule)\b',
    re.IGNORECASE,
)

# 5. Streams, Readers, Sockets, Files, Cursors
_STREAM_IO_RE = re.compile(
    r'\b(?:reader|writer|stream|file|ws|socket|cursor|channel|pipe)\.'
    r'(?:read|write|send|close|pipe|next|fetchNext|readChunk)\b',
    re.IGNORECASE,
)

# 6. Interactive Prompts / User Input
_PROMPT_RE = re.compile(
    r'\b(?:prompt|inquirer|question|rl\.question|confirm|input|cli)\b',
    re.IGNORECASE,
)

# 7. Dependent state variable names in loop assignments
_DEPENDENT_VARS = (
    "cursor", "next", "page", "token", "offset", "chunk", "buffer",
    "acc", "accumulator", "state", "prev", "previous", "res",
    "response", "result", "item", "row", "current", "last",
)


def _is_intentional_sequential_call(awaited_text: str) -> bool:
    if _DELAY_RE.search(awaited_text):
        return True
    if _BROWSER_AUTOMATION_RE.search(awaited_text):
        return True
    if _DB_TRANSACTION_RE.search(awaited_text):
        return True
    if _LOCK_MUTEX_RE.search(awaited_text):
        return True
    if _STREAM_IO_RE.search(awaited_text):
        return True
    if _PROMPT_RE.search(awaited_text):
        return True
    return False


def _has_dependent_assignment(node: dict, parent_map: dict) -> bool:
    """Check if result of await is assigned to an accumulator or state variable."""
    curr = node
    for _ in range(3):
        parent = parent_map.get(id(curr))
        if not parent:
            break
        ptype = parent.get("type", "")
        if ptype in ("assignment_expression", "variable_declarator", "augmented_assignment_expression"):
            pchildren = parent.get("children", [])
            if pchildren:
                var_text = (pchildren[0].get("text") or "").strip().lower()
                if any(k in var_text for k in _DEPENDENT_VARS):
                    return True
        curr = parent
    return False


def _is_for_await_loop(loop_node: dict) -> bool:
    """Detect `for await (const x of stream)` async iterable loops."""
    loop_type = loop_node.get("type", "")
    if loop_type == "for_await_of_statement":
        return True
    text = (loop_node.get("text") or "").lstrip()
    if text.startswith("for await") or text.startswith("for (await"):
        return True
    for child in loop_node.get("children", []):
        if child.get("type") == "await" or child.get("text") == "await":
            return True
    return False


def _is_retry_loop(loop_node: dict) -> bool:
    """Detect retry loops like `while (retries > 0)` or `while (attempt < maxAttempts)`."""
    text = (loop_node.get("text") or "").lower()
    head = text[:min(len(text), 80)]
    return any(k in head for k in ("retry", "retries", "attempt", "attempts", "tries", "maxattempts"))


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

        # Test files: sequential async assertions in test blocks are intentional
        if self._is_test_file(file_path):
            return

        parent_map: dict = {}
        self._build_parent_map(ast, parent_map)

        for node in self._walk(ast):
            if node.get("type") != "await_expression":
                continue

            loop_node = self._find_enclosing_loop(node, parent_map)
            if not loop_node:
                continue

            # 1. `for await (... of ...)` streaming loop -> Suppress
            if _is_for_await_loop(loop_node):
                continue

            # 2. Retry / Backoff loops -> Suppress
            if _is_retry_loop(loop_node):
                continue

            awaited_text = (node.get("text") or "await ...").strip()

            # 3. Intentional sequential domain (delays, browser automation, db transactions, locks, streams, CLI)
            if _is_intentional_sequential_call(awaited_text):
                continue

            # 4. Dependent pagination / accumulator / cursor loop -> Suppress
            if _has_dependent_assignment(node, parent_map):
                continue

            self.record_syntax_match()

            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"Sequential `await` in loop body processes items one by one. "
                    f"If iterations are independent, consider collecting promises and using `Promise.all()`."
                ),
                evidence={
                    "await_expression": awaited_text,
                    "loop_type": loop_node.get("type", "unknown_loop"),
                    "confidence": "high",
                    "reason": f"Sequential `await` ({awaited_text}) inside `{loop_node.get('type')}`.",
                },
                confidence="high",
            )

    # ------------------------------------------------------------------
    def _build_parent_map(self, node: dict, mapping: dict) -> None:
        for child in node.get("children", []):
            mapping[id(child)] = node
            self._build_parent_map(child, mapping)

    def _find_enclosing_loop(self, node: dict, parent_map: dict) -> Optional[dict]:
        curr = node
        while id(curr) in parent_map:
            curr = parent_map[id(curr)]
            if curr.get("type") in _LOOP_TYPES:
                return curr
            # Stop at nested function / method boundaries
            if curr.get("type") in (
                "function_declaration",
                "function_expression",
                "arrow_function",
                "method_definition",
                "generator_function",
                "generator_function_declaration",
            ):
                return None
        return None
