"""
JS_CONSTCOND_001 — JavaScript Constant Condition Unit & Boundary Tests
======================================================================
Tests for constant literals or expressions in if/while constructs (excluding while(true)).
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.js_constant_condition import JavaScriptConstantCondition
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, stmt_block, node, leaf, ident, number_lit,
    true_lit, false_lit, parens, js_binop,
)


def run_tests() -> bool:
    rule = JavaScriptConstantCondition()
    r = RuleTestRunner("JS_CONSTCOND_001 — Unit & Boundary Tests")

    # --- 1. CONSTANT IF / WHILE CONDITIONS (MUST FLAG) ---
    if_true = node("if_statement", "if (true) {}", children=[leaf("if", "if"), parens(true_lit()), stmt_block()])
    r.must_flag("if (true) {} (constant true condition)", rule, module(if_true), file_path="app.js")

    if_false = node("if_statement", "if (false) {}", children=[leaf("if", "if"), parens(false_lit()), stmt_block()])
    r.must_flag("if (false) {} (constant false condition)", rule, module(if_false), file_path="app.js")

    while_false = node("while_statement", "while (false) {}", children=[leaf("while", "while"), parens(false_lit()), stmt_block()])
    r.must_flag("while (false) {} (dead while loop)", rule, module(while_false), file_path="app.js")

    # --- 2. ALLOWED IDIOMS & DYNAMIC CONDITIONS (MUST NOT FLAG) ---
    while_true = node("while_statement", "while (true) {}", children=[leaf("while", "while"), parens(true_lit()), stmt_block()])
    r.must_not_flag("while (true) {} (standard infinite loop idiom)", rule, module(while_true), file_path="app.js")

    dynamic_if = node("if_statement", "if (x > 10) {}", children=[
        leaf("if", "if"),
        parens(js_binop(ident("x"), ">", number_lit("10"))),
        stmt_block()
    ])
    r.must_not_flag("if (x > 10) {} (dynamic condition)", rule, module(dynamic_if), file_path="app.js")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
