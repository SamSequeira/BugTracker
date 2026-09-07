"""
JS_AWA_001 — JavaScript Await in Loop Unit & Boundary Tests
============================================================
Tests for await expressions inside loops vs nested function boundaries,
`for await` streaming, browser automation, db transactions, locks, and
dependent iteration suppression.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.js_no_await_in_loop import JavaScriptNoAwaitInLoop
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, block, node, leaf, ident,
)


def run_tests() -> bool:
    rule = JavaScriptNoAwaitInLoop()
    r = RuleTestRunner("JS_AWA_001 — Unit & Boundary Tests")

    await_expr = node("await_expression", "await fetch()", children=[
        leaf("await", "await"), node("call_expression", "fetch()")
    ])

    # --- 1. AWAIT DIRECTLY IN LOOPS (MUST FLAG) ---
    for_loop = node("for_statement", "for (let i = 0; i < items.length; i++) { await fetch(); }", children=[
        leaf("for", "for"), block(node("expression_statement", "await fetch();", children=[await_expr]))
    ])
    r.must_flag("await inside for loop", rule, module(for_loop), "src/app.js")

    while_loop = node("while_statement", "while (c) { await fetch(); }", children=[
        leaf("while", "while"), ident("c"), block(node("expression_statement", "await fetch();", children=[await_expr]))
    ])
    r.must_flag("await inside while loop", rule, module(while_loop), "src/app.js")

    for_of_loop = node("for_in_statement", "for (const x of items) { await fetch(); }", children=[
        leaf("for", "for"), block(node("expression_statement", "await fetch();", children=[await_expr]))
    ])
    r.must_flag("await inside for..of / for..in loop", rule, module(for_of_loop), "src/app.js")

    while_cond_await = node("while_statement", "while (await fetch()) {}", children=[
        leaf("while", "while"), await_expr, block()
    ])
    r.must_flag("await in while condition", rule, module(while_cond_await), "src/app.js")

    # --- 2. BOUNDARIES & INTENTIONAL PATTERNS (MUST NOT FLAG) ---
    # `for await` streaming consumption
    for_await = node("for_in_statement", "for await (const chunk of stream) { await process(chunk); }", children=[
        leaf("for", "for"), leaf("await", "await"), block(node("expression_statement", "await process();", children=[await_expr]))
    ])
    r.must_not_flag("for await (const chunk of stream) -> streaming consumption", rule, module(for_await), "src/app.js")

    # Deliberate delay / sleep / polling
    await_sleep = node("await_expression", "await sleep(100)", children=[
        leaf("await", "await"), node("call_expression", "sleep(100)")
    ])
    for_sleep = node("for_statement", "for (...) { await sleep(100); }", children=[
        leaf("for", "for"), block(node("expression_statement", "await sleep(100);", children=[await_sleep]))
    ])
    r.must_not_flag("await sleep(...) in loop -> intentional delay", rule, module(for_sleep), "src/app.js")

    # Browser automation / Playwright / Puppeteer
    await_page = node("await_expression", "await page.click('#submit')", children=[
        leaf("await", "await"), node("call_expression", "page.click('#submit')")
    ])
    for_page = node("for_statement", "for (...) { await page.click('#submit'); }", children=[
        leaf("for", "for"), block(node("expression_statement", "await page.click('#submit');", children=[await_page]))
    ])
    r.must_not_flag("await page.click(...) -> browser automation step", rule, module(for_page), "src/app.js")

    # Database transaction / query
    await_tx = node("await_expression", "await tx.query('INSERT INTO items VALUES ($1)', [x])", children=[
        leaf("await", "await"), node("call_expression", "tx.query(...)")
    ])
    for_tx = node("for_statement", "for (...) { await tx.query(...); }", children=[
        leaf("for", "for"), block(node("expression_statement", "await tx.query(...);", children=[await_tx]))
    ])
    r.must_not_flag("await tx.query(...) -> database transaction", rule, module(for_tx), "src/app.js")

    # Mutex / Lock
    await_lock = node("await_expression", "await lock.acquire()", children=[
        leaf("await", "await"), node("call_expression", "lock.acquire()")
    ])
    for_lock = node("for_statement", "for (...) { await lock.acquire(); }", children=[
        leaf("for", "for"), block(node("expression_statement", "await lock.acquire();", children=[await_lock]))
    ])
    r.must_not_flag("await lock.acquire() -> mutex lock", rule, module(for_lock), "src/app.js")

    # Stream reader
    await_reader = node("await_expression", "await reader.read()", children=[
        leaf("await", "await"), node("call_expression", "reader.read()")
    ])
    for_reader = node("while_statement", "while (true) { await reader.read(); }", children=[
        leaf("while", "while"), block(node("expression_statement", "await reader.read();", children=[await_reader]))
    ])
    r.must_not_flag("await reader.read() -> stream read", rule, module(for_reader), "src/app.js")

    # Dependent assignment / pagination cursor
    cursor_assign = node("assignment_expression", "cursor = await fetchCursor()", children=[
        ident("cursor"), leaf("=", "="), await_expr
    ])
    while_cursor = node("while_statement", "while (cursor) { cursor = await fetchCursor(); }", children=[
        leaf("while", "while"), block(node("expression_statement", "cursor = await fetchCursor();", children=[cursor_assign]))
    ])
    r.must_not_flag("cursor = await fetchCursor() -> dependent pagination iteration", rule, module(while_cursor), "src/app.js")

    # Retry loop
    while_retry = node("while_statement", "while (retries > 0) { await fetch(); }", children=[
        leaf("while", "while"), block(node("expression_statement", "await fetch();", children=[await_expr]))
    ])
    r.must_not_flag("while (retries > 0) -> retry loop", rule, module(while_retry), "src/app.js")

    # Test file suppression
    r.must_not_flag("await in test file (*.test.js)", rule, module(for_loop), "src/__tests__/app.test.js")

    # Await in async arrow function / IIFE inside loop
    arrow_fn = node("arrow_function", "async () => { await fetch(); }", children=[
        leaf("async", "async"), block(node("expression_statement", "await fetch();", children=[await_expr]))
    ])
    for_with_arrow = node("for_statement", "for (...) { async () => { await fetch(); } }", children=[
        leaf("for", "for"), block(arrow_fn)
    ])
    r.must_not_flag("await inside nested arrow function in loop (boundary)", rule, module(for_with_arrow), "src/app.js")

    # Await inside generator function in loop
    gen_fn = node("generator_function_declaration", "function* g() { await fetch(); }", children=[
        block(node("expression_statement", "await fetch();", children=[await_expr]))
    ])
    for_with_gen = node("for_statement", "for (...) { function* g() {} }", children=[
        leaf("for", "for"), block(gen_fn)
    ])
    r.must_not_flag("await inside generator function in loop (boundary)", rule, module(for_with_gen), "src/app.js")

    # Await outside loop (in try or standard function body)
    try_stmt = node("try_statement", "try { await fetch(); }", children=[
        leaf("try", "try"), block(node("expression_statement", "await fetch();", children=[await_expr]))
    ])
    r.must_not_flag("await in try block outside loop", rule, module(try_stmt), "src/app.js")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
