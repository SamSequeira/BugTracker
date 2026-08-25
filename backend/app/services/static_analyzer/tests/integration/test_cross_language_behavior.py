"""
Integration Suite: Cross-Language Semantic Consistency
========================================================
Tests semantic equivalence and behavior consistency across Python, Java,
and JavaScript analyzer engines.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.py_division_by_zero import PythonDivisionByZero
from app.services.static_analyzer.rules.java_division_by_zero import JavaDivisionByZero
from app.services.static_analyzer.rules.js_division_by_zero import JavaScriptDivisionByZero
from app.services.static_analyzer.rules.java_string_equality import JavaStringEquality
from app.services.static_analyzer.rules.js_triple_equals import JavaScriptTripleEquals
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, ident, integer, number_lit,
    binop_node, java_binop, js_binop, java_decimal_int,
)


def run_tests() -> bool:
    r = RuleTestRunner("Integration — Cross-Language Consistency")
    py_div = PythonDivisionByZero()
    jv_div = JavaDivisionByZero()
    js_div = JavaScriptDivisionByZero()

    # --- 1. DIVISION BY ZERO CONSISTENCY (PY, JAVA, JS) ---
    py_zero = module(binop_node(ident("x"), "/", integer("0")))
    jv_zero = module(java_binop(ident("x"), "/", java_decimal_int("0")))
    js_zero = module(js_binop(ident("x"), "/", number_lit("0")))

    r.must_flag("PY_DIV_001: x / 0 flagged", py_div, py_zero, "f.py")
    r.must_flag("JAVA_DIV_001: x / 0 flagged", jv_div, jv_zero, "T.java")
    r.must_flag("JS_DIV_001: x / 0 flagged", js_div, js_zero, "f.js")

    # --- 2. DIVISION BY NON-ZERO CONSISTENCY (PY, JAVA, JS) ---
    py_one = module(binop_node(ident("x"), "/", integer("1")))
    jv_one = module(java_binop(ident("x"), "/", java_decimal_int("1")))
    js_one = module(js_binop(ident("x"), "/", number_lit("1")))

    r.must_not_flag("PY_DIV_001: x / 1 safe", py_div, py_one, "f.py")
    r.must_not_flag("JAVA_DIV_001: x / 1 safe", jv_div, jv_one, "T.java")
    r.must_not_flag("JS_DIV_001: x / 1 safe", js_div, js_one, "f.js")

    # --- 3. DYNAMIC VARIABLE DIVISOR (PY, JAVA, JS) ---
    py_var = module(binop_node(ident("x"), "/", ident("y")))
    jv_var = module(java_binop(ident("x"), "/", ident("y")))
    js_var = module(js_binop(ident("x"), "/", ident("y")))

    r.must_flag("PY_DIV_001: x / y flagged", py_div, py_var, "f.py")
    r.must_flag("JAVA_DIV_001: x / y flagged", jv_div, jv_var, "T.java")
    r.must_flag("JS_DIV_001: x / y flagged", js_div, js_var, "f.js")

    # --- 4. EQUALITY DETECTION CONSISTENCY (JAVA, JS) ---
    jv_eq = JavaStringEquality()
    js_eq = JavaScriptTripleEquals()

    jv_eq_ast = module(java_binop(ident("name"), "==", ident("other")))
    js_eq_ast = module(js_binop(ident("name"), "==", ident("other")))

    r.must_flag("JAVA_EQ_001: name == other flagged", jv_eq, jv_eq_ast, "T.java")
    r.must_flag("JS_EQ_001: name == other flagged", js_eq, js_eq_ast, "f.js")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
