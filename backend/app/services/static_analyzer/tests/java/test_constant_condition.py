"""
JAVA_CONSTCOND_001 — Java Constant Branch Condition Unit & Boundary Tests
========================================================================
Tests for constant literals or expressions in if/while constructs (excluding while(true)).
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.java_constant_condition import JavaConstantCondition
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, block, node, leaf, ident, java_decimal_int,
    true_lit, false_lit, parens, java_binop, java_while_true,
)


def run_tests() -> bool:
    rule = JavaConstantCondition()
    r = RuleTestRunner("JAVA_CONSTCOND_001 — Unit & Boundary Tests")

    # --- 1. CONSTANT IF / WHILE CONDITIONS (MUST FLAG) ---
    if_true = node("if_statement", "if (true) {}", children=[leaf("if", "if"), parens(true_lit()), block()])
    r.must_flag("if (true) {} (constant true condition)", rule, module(if_true), file_path="App.java")

    if_false = node("if_statement", "if (false) {}", children=[leaf("if", "if"), parens(false_lit()), block()])
    r.must_flag("if (false) {} (constant false condition)", rule, module(if_false), file_path="App.java")

    while_false = node("while_statement", "while (false) {}", children=[leaf("while", "while"), parens(false_lit()), block()])
    r.must_flag("while (false) {} (dead while loop)", rule, module(while_false), file_path="App.java")

    # --- 2. ALLOWED IDIOMS & DYNAMIC CONDITIONS (MUST NOT FLAG) ---
    r.must_not_flag("while (true) {} (standard infinite loop idiom)", rule, module(java_while_true()), file_path="App.java")

    dynamic_if = node("if_statement", "if (x > 10) {}", children=[
        leaf("if", "if"),
        parens(java_binop(ident("x"), ">", java_decimal_int("10"))),
        block()
    ])
    r.must_not_flag("if (x > 10) {} (dynamic condition)", rule, module(dynamic_if), file_path="App.java")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
