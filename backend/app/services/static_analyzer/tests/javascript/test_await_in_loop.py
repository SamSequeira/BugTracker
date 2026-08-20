"""
JS_AWA_001 — JavaScript Await in Loop Unit & Boundary Tests
============================================================
Tests for await expressions inside loops vs nested function boundaries.
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
    for_loop = node("for_statement", "for (...) {}", children=[
        leaf("for", "for"), block(node("expression_statement", "await fetch();", children=[await_expr]))
    ])
    r.must_flag("await inside for loop", rule, module(for_loop), "f.js")

    while_loop = node("while_statement", "while (c) {}", children=[
        leaf("while", "while"), ident("c"), block(node("expression_statement", "await fetch();", children=[await_expr]))
    ])
    r.must_flag("await inside while loop", rule, module(while_loop), "f.js")

    for_of_loop = node("for_in_statement", "for (x of items) {}", children=[
        leaf("for", "for"), block(node("expression_statement", "await fetch();", children=[await_expr]))
    ])
    r.must_flag("await inside for..of / for..in loop", rule, module(for_of_loop), "f.js")

    while_cond_await = node("while_statement", "while (await fetch()) {}", children=[
        leaf("while", "while"), await_expr, block()
    ])
    r.must_flag("await in while condition", rule, module(while_cond_await), "f.js")

    # --- 2. BOUNDARIES: NESTED FUNCTIONS & NON-LOOPS (MUST NOT FLAG) ---
    # Await in async arrow function / IIFE inside loop
    arrow_fn = node("arrow_function", "async () => { await fetch(); }", children=[
        leaf("async", "async"), block(node("expression_statement", "await fetch();", children=[await_expr]))
    ])
    for_with_arrow = node("for_statement", "for (...) { async () => { await fetch(); } }", children=[
        leaf("for", "for"), block(arrow_fn)
    ])
    r.must_not_flag("await inside nested arrow function in loop (boundary)", rule, module(for_with_arrow), "f.js")

    # Await inside generator function in loop
    gen_fn = node("generator_function_declaration", "function* g() { await fetch(); }", children=[
        block(node("expression_statement", "await fetch();", children=[await_expr]))
    ])
    for_with_gen = node("for_statement", "for (...) { function* g() {} }", children=[
        leaf("for", "for"), block(gen_fn)
    ])
    r.must_not_flag("await inside generator function in loop (boundary)", rule, module(for_with_gen), "f.js")

    # Await outside loop (in try or standard function body)
    try_stmt = node("try_statement", "try { await fetch(); }", children=[
        leaf("try", "try"), block(node("expression_statement", "await fetch();", children=[await_expr]))
    ])
    r.must_not_flag("await in try block outside loop", rule, module(try_stmt), "f.js")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
