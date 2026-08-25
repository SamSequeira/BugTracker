"""
JAVA_LOOP_001 — Java Infinite Loop Unit & Boundary Tests
=========================================================
Tests for while(true), for(;;), do-while(true) and reachability of loop exit statements.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.java_infinite_loop import JavaInfiniteLoop
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, block, node, leaf, ident,
    java_while_true, break_stmt, return_stmt, throw_stmt, parens, true_lit,
)


def run_tests() -> bool:
    rule = JavaInfiniteLoop()
    r = RuleTestRunner("JAVA_LOOP_001 — Unit & Boundary Tests")

    # --- 1. INFINITE LOOPS WITHOUT EXIT (MUST FLAG) ---
    r.must_flag("empty while(true) {}", rule, module(java_while_true()), "T.java")

    # for(;;)
    for_ever = node("for_statement", "for(;;){}", children=[
        leaf("for", "for"), leaf("(", "("), leaf(";", ";"), leaf(";", ";"), leaf(")", ")"), block()
    ])
    r.must_flag("empty for(;;) {}", rule, module(for_ever), "T.java")

    # for(int i=0;;i++)
    for_with_clauses = node("for_statement", "for(int i=0;;i++)", children=[
        leaf("for", "for"), leaf("(", "("),
        node("local_variable_declaration", "int i=0"),
        leaf(";", ";"), leaf(";", ";"),
        node("update_expression", "i++"),
        leaf(")", ")"),
        block(),
    ])
    r.must_flag("for(int i=0;;i++) with no condition", rule, module(for_with_clauses), "T.java")

    # W05: do { } while(true);
    do_while_true = node("do_statement", "do {} while(true);", children=[
        leaf("do", "do"),
        block(),
        leaf("while", "while"),
        parens(true_lit()),
        leaf(";", ";"),
    ])
    r.must_flag("do {} while(true); with no exit", rule, module(do_while_true), "T.java")

    # --- 2. REACHABLE EXITS (MUST NOT FLAG) ---
    r.must_not_flag("while(true) { break; } (unlabeled break)", rule, module(java_while_true(break_stmt())), "T.java")
    r.must_not_flag("while(true) { return; } (return statement)", rule, module(java_while_true(return_stmt())), "T.java")
    r.must_not_flag("while(true) { throw e; } (throw statement)", rule, module(java_while_true(throw_stmt())), "T.java")

    # System.exit(0)
    sys_exit = node("expression_statement", "System.exit(0);", children=[
        leaf("method_invocation", "System.exit(0)")
    ])
    r.must_not_flag("while(true) { System.exit(0); }", rule, module(java_while_true(sys_exit)), "T.java")

    # Try-catch that throws
    try_catch = node("try_statement", "try {} catch(Exception e){ throw e; }", children=[
        leaf("try", "try"), block(),
        node("catch_clause", "catch(e){throw e;}", children=[
            node("catch_formal_parameter", "Exception e"),
            block(throw_stmt())
        ])
    ])
    r.must_not_flag("while(true) with try-catch that throws", rule, module(java_while_true(try_catch)), "T.java")

    # --- 3. DYNAMIC / TERMINATING LOOPS (MUST NOT FLAG) ---
    while_dyn = node("while_statement", "while(x > 0) {}", children=[
        leaf("while", "while"),
        parens(node("binary_expression", "x > 0", children=[ident("x"), leaf(">", ">"), leaf("0", "0")])),
        block()
    ])
    r.must_not_flag("while(x > 0) {} (dynamic condition)", rule, module(while_dyn), "T.java")

    for_bounded = node("for_statement", "for(int i=0; i<10; i++) {}", children=[
        leaf("for", "for"), leaf("(", "("),
        node("local_variable_declaration", "int i=0"),
        leaf(";", ";"),
        node("binary_expression", "i<10"),
        leaf(";", ";"),
        node("update_expression", "i++"),
        leaf(")", ")"),
        block(),
    ])
    r.must_not_flag("for(int i=0; i<10; i++) (bounded loop)", rule, module(for_bounded), "T.java")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
