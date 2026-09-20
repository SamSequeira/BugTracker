"""
Regression Suite: Control Flow, Branches, Loops & Break Targeting
==================================================================
Validates control-flow analysis, guard tracking, and break targeting.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.py_division_by_zero import PythonDivisionByZero
from app.services.static_analyzer.rules.java_infinite_loop import JavaInfiniteLoop
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, block, node, leaf, ident, integer,
    binop_node, java_binop, java_while_true, break_stmt, if_stmt, comparison, parens,
    true_lit, false_lit, call_node,
)


def run_tests() -> bool:
    r = RuleTestRunner("Regression - Control Flow & Break Resolution")
    py_div = PythonDivisionByZero()
    jv_loop = JavaInfiniteLoop()
    x = ident("x")
    div_d = binop_node(x, "/", ident("d", 30), 30)

    # --- 1. REASSIGNMENT INVALIDATES PRIOR GUARD ---
    guard_d = if_stmt(comparison(ident("d", 1), "!=", integer("0", 1), 1), block(), 1)
    kill_d0 = node("assignment", "d = 0", 3, children=[ident("d", 3), leaf("=", "=", 3), integer("0", 3)])
    r.must_flag("d=0 after guard invalidates guard -> must flag definitely_zero", py_div, module(guard_d, kill_d0, div_d))

    kill_d1 = node("assignment", "d = 1", 3, children=[ident("d", 3), leaf("=", "=", 3), integer("1", 3)])
    r.must_not_flag("safe reassignment: d=0 then d=1 then x/d -> safe", py_div, module(kill_d0, kill_d1, div_d))

    # --- 2. BRANCH FACT MERGING (IF / ELSE) ---
    # Divergent branches: if c: d=0 else: d=1; x / d -> NOT FLAGGED under high precision (divisor not definitely zero)
    if_divergent = node("if_statement", "if c: d=0 else: d=1", 10, children=[
        leaf("if", "if", 10), ident("c", 10), leaf(":", ":", 10),
        block(node("assignment", "d=0", 11, children=[ident("d", 11), leaf("=", "=", 11), integer("0", 11)])),
        node("else_clause", "else: d=1", 12, children=[
            leaf("else", "else", 12), leaf(":", ":", 12),
            block(node("assignment", "d=1", 13, children=[ident("d", 13), leaf("=", "=", 13), integer("1", 13)]))
        ])
    ])
    r.must_not_flag("if c: d=0 else: d=1 then x/d -> conservative safe (not definitely zero)", py_div, module(if_divergent, div_d))

    # Both branches safe: if c: d=1 else: d=2; x / d -> NOT FLAGGED
    if_both_safe = node("if_statement", "if c: d=1 else: d=2", 10, children=[
        leaf("if", "if", 10), ident("c", 10), leaf(":", ":", 10),
        block(node("assignment", "d=1", 11, children=[ident("d", 11), leaf("=", "=", 11), integer("1", 11)])),
        node("else_clause", "else: d=2", 12, children=[
            leaf("else", "else", 12), leaf(":", ":", 12),
            block(node("assignment", "d=2", 13, children=[ident("d", 13), leaf("=", "=", 13), integer("2", 13)]))
        ])
    ])
    r.must_not_flag("if c: d=1 else: d=2 then x/d -> provably safe", py_div, module(if_both_safe, div_d))

    # Both branches zero: if c: d=0 else: d=0; x / d -> definitely_zero
    if_both_zero = node("if_statement", "if c: d=0 else: d=0", 10, children=[
        leaf("if", "if", 10), ident("c", 10), leaf(":", ":", 10),
        block(node("assignment", "d=0", 11, children=[ident("d", 11), leaf("=", "=", 11), integer("0", 11)])),
        node("else_clause", "else: d=0", 12, children=[
            leaf("else", "else", 12), leaf(":", ":", 12),
            block(node("assignment", "d=0", 13, children=[ident("d", 13), leaf("=", "=", 13), integer("0", 13)]))
        ])
    ])
    r.must_flag("if c: d=0 else: d=0 then x/d -> definitely_zero", py_div, module(if_both_zero, div_d))

    # --- 3. LOOP STATES & AUGMENTED ASSIGNMENTS ---
    while_stmt = node("while_statement", "while c: d=0", 10, children=[
        leaf("while", "while", 10), ident("c", 10), leaf(":", ":", 10),
        block(node("assignment", "d=0", 11, children=[ident("d", 11), leaf("=", "=", 11), integer("0", 11)]))
    ])
    r.must_not_flag("d=1; while c: d=0 then x/d -> loop body not guaranteed executed (safe)", py_div, module(kill_d1, while_stmt, div_d))

    # --- 4. CONSTANT BOOLEAN CONDITIONS IN LOOPS ---
    if_false = node("if_statement", "if(false) break;", 5, children=[
        leaf("if", "if", 5), parens(false_lit(5)), block(break_stmt(5))
    ])
    r.must_flag("while(true) + if(false) break -> unreachable break -> infinite loop", jv_loop, module(java_while_true(if_false)), "T.java")

    if_not_true = node("if_statement", "if(!true) break;", 5, children=[
        leaf("if", "if", 5),
        parens(node("unary_expression", "!true", 5, children=[leaf("!", "!", 5), true_lit(5)])),
        block(break_stmt(5))
    ])
    r.must_flag("while(true) + if(!true) break -> unreachable -> infinite loop", jv_loop, module(java_while_true(if_not_true)), "T.java")

    if_sc_false = node("if_statement", "if(false && unknown()) break;", 5, children=[
        leaf("if", "if", 5),
        parens(node("binary_expression", "false && unknown()", 5, children=[false_lit(5), leaf("&&", "&&", 5), call_node("unknown", line=5)])),
        block(break_stmt(5))
    ])
    r.must_flag("while(true) + if(false && unknown()) break -> short-circuits false -> infinite", jv_loop, module(java_while_true(if_sc_false)), "T.java")

    # --- 5. NESTED & LABELED BREAK TARGET RESOLUTION ---
    inner_loop = java_while_true(break_stmt())
    outer_loop = java_while_true(inner_loop)
    r.must_flag("while(true) { while(true) { break; } } -> outer loop is infinite", jv_loop, module(outer_loop), "T.java")

    break_outer = leaf("break_statement", "break outer;", 5)
    inner_with_outer_break = java_while_true(break_outer)
    outer_labeled = node("labeled_statement", "outer: while(true){...}", 1, children=[
        ident("outer", 1), leaf(":", ":", 1), java_while_true(inner_with_outer_break)
    ])
    r.must_not_flag("labeled break: outer: while(true) { while(true) { break outer; } } -> exits outer", jv_loop, module(outer_labeled), "T.java")

    # Switch statement unlabeled break boundary
    switch_break = node("switch_statement", "switch(x){case 1: break;}", 5, children=[
        leaf("switch", "switch", 5), ident("x", 5),
        node("switch_block", "{case 1: break;}", 5, children=[
            node("switch_rule", "case 1: break;", 5, children=[
                leaf("case", "case", 5), integer("1", 5), leaf(":", ":", 5), break_stmt(5)
            ])
        ])
    ])
    r.must_flag("while(true) { switch(x){case 1: break;} } -> break exits switch only -> loop is infinite", jv_loop, module(java_while_true(switch_break)), "T.java")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
