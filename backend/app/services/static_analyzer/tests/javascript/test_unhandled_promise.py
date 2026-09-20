"""
JS_PROMISE_001 — JavaScript Unhandled / Unawaited Promise Unit & Boundary Tests
================================================================================
Tests for floating promise-returning API calls vs properly handled/awaited promises.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.js_unhandled_promise import JavaScriptUnhandledPromise
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, call_node, ident, string_lit, node, leaf, await_expr,
)


def run_tests() -> bool:
    rule = JavaScriptUnhandledPromise()
    r = RuleTestRunner("JS_PROMISE_001 — Unit & Boundary Tests")

    # --- 1. UNHANDLED FLOATING PROMISES (MUST FLAG) ---
    fetch_call = call_node("fetch", string_lit("'/api/data'"))
    r.must_flag("fetch('/api/data') (floating unhandled promise)", rule, module(node("expression_statement", "fetch(...)", children=[fetch_call])), file_path="app.js")

    axios_call = node("call_expression", "axios.get('/api/users')", children=[
        node("member_expression", "axios.get", children=[ident("axios"), leaf(".", "."), ident("get")]),
        node("arguments", "('/api/users')", children=[string_lit("'/api/users'")])
    ])
    r.must_flag("axios.get('/api/users') (floating axios get)", rule, module(node("expression_statement", "axios.get(...)", children=[axios_call])), file_path="app.js")

    # --- 2. PROPERLY HANDLED PROMISES (MUST NOT FLAG) ---
    awaited_fetch = await_expr(fetch_call)
    r.must_not_flag("await fetch('/api/data') (awaited promise)", rule, module(node("expression_statement", "await fetch(...)", children=[awaited_fetch])), file_path="app.js")

    then_chained = node("call_expression", "fetch().then(fn)", children=[
        node("member_expression", "fetch().then", children=[fetch_call, leaf(".", "."), ident("then")]),
        node("arguments", "(fn)", children=[ident("fn")])
    ])
    r.must_not_flag("fetch().then(...) (chained .then handler)", rule, module(node("expression_statement", "fetch().then(...)", children=[then_chained])), file_path="app.js")

    # Higher-order listener containing async fetch (MUST NOT FLAG outer listener)
    listener_call = node("call_expression", "button.addEventListener('click', async () => { await fetch(); })", children=[
        node("member_expression", "button.addEventListener", children=[ident("button"), leaf(".", "."), ident("addEventListener")]),
        node("arguments", "('click', ...)", children=[string_lit("'click'"), node("arrow_function", "async () => { await fetch(); }", children=[awaited_fetch])])
    ])
    r.must_not_flag("button.addEventListener('click', async () => { await fetch(); }) (higher-order event listener)", rule,
                    module(node("expression_statement", "button.addEventListener(...)", children=[listener_call])), file_path="app.js")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
