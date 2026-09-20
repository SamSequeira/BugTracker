"""
JS_UNREACH_001 — JavaScript Unreachable Code Unit & Boundary Tests
==================================================================
Tests for code following unconditional termination statements (return, throw, break, continue, try/finally).
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.js_unreachable_code import JavaScriptUnreachableCode
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, stmt_block, js_fn, ident, number_lit,
    return_stmt, throw_stmt, leaf, node,
)


def run_tests() -> bool:
    rule = JavaScriptUnreachableCode()
    r = RuleTestRunner("JS_UNREACH_001 — Unit & Boundary Tests")

    # --- 1. UNREACHABLE AFTER RETURN / THROW (MUST FLAG) ---
    ret_stmt = node("return_statement", "return 1;", children=[leaf("return", "return"), number_lit("1")])
    after_stmt = node("expression_statement", "let x = 2;", children=[node("variable_declaration", "let x = 2;")])
    fn_body = stmt_block(ret_stmt, after_stmt)
    fn_ast = module(js_fn(fn_body, line=1))
    r.must_flag("function f() { return 1; let x = 2; } (unreachable after return)", rule, fn_ast, file_path="app.js")

    thr_stmt = node("throw_statement", "throw new Error();", children=[leaf("throw", "throw"), ident("Error")])
    fn_throw = module(js_fn(stmt_block(thr_stmt, after_stmt), line=1))
    r.must_flag("function f() { throw new Error(); let x = 2; } (unreachable after throw)", rule, fn_throw, file_path="app.js")

    # --- 2. TRY/FINALLY UNREACHABLE CODE (MUST FLAG) ---
    try_stmt = node("try_statement", "try { return 1; } finally { cleanup(); }", children=[
        leaf("try", "try"),
        stmt_block(ret_stmt),
        node("finally_clause", "finally { cleanup(); }", children=[
            leaf("finally", "finally"),
            stmt_block(node("expression_statement", "cleanup();")),
        ]),
    ])
    try_fn = module(js_fn(stmt_block(try_stmt, after_stmt), line=1))
    r.must_flag("try { return 1; } finally { cleanup(); } let x = 2; (unreachable after try-finally)", rule, try_fn, file_path="app.js")

    # --- 3. REACHABLE STATEMENTS (MUST NOT FLAG) ---
    reachable_fn = module(js_fn(stmt_block(after_stmt, ret_stmt), line=1))
    r.must_not_flag("function f() { let x = 2; return 1; } (reachable statement before return)", rule, reachable_fn, file_path="app.js")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
