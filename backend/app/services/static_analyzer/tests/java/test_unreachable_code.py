"""
JAVA_UNREACH_001 — Java Unreachable Code Unit & Boundary Tests
==============================================================
Tests for code following unconditional termination statements (return, throw, break, continue, try/finally).
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.java_unreachable_code import JavaUnreachableCode
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, block, node, leaf, ident, java_decimal_int,
    return_stmt, throw_stmt,
)


def run_tests() -> bool:
    rule = JavaUnreachableCode()
    r = RuleTestRunner("JAVA_UNREACH_001 — Unit & Boundary Tests")

    # --- 1. UNREACHABLE AFTER RETURN / THROW (MUST FLAG) ---
    ret_stmt = node("return_statement", "return 1;", children=[leaf("return", "return"), java_decimal_int("1")])
    after_stmt = node("expression_statement", "int x = 2;", children=[node("local_variable_declaration", "int x = 2;")])
    method_body = block(ret_stmt, after_stmt)
    r.must_flag("return 1; int x = 2; (unreachable after return)", rule, module(method_body), file_path="App.java")

    thr_stmt = node("throw_statement", "throw new RuntimeException();", children=[leaf("throw", "throw"), ident("RuntimeException")])
    throw_body = block(thr_stmt, after_stmt)
    r.must_flag("throw new Exception(); int x = 2; (unreachable after throw)", rule, module(throw_body), file_path="App.java")

    # --- 2. TRY/FINALLY UNREACHABLE CODE (MUST FLAG) ---
    try_stmt = node("try_statement", "try { return 1; } finally { cleanup(); }", children=[
        leaf("try", "try"),
        block(ret_stmt),
        node("finally_clause", "finally { cleanup(); }", children=[
            leaf("finally", "finally"),
            block(node("expression_statement", "cleanup();")),
        ]),
    ])
    try_body = block(try_stmt, after_stmt)
    r.must_flag("try { return 1; } finally { cleanup(); } int x = 2; (unreachable after try-finally)", rule, module(try_body), file_path="App.java")

    # --- 3. REACHABLE CODE (MUST NOT FLAG) ---
    reachable_body = block(after_stmt, ret_stmt)
    r.must_not_flag("int x = 2; return 1; (reachable before return)", rule, module(reachable_body), file_path="App.java")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
