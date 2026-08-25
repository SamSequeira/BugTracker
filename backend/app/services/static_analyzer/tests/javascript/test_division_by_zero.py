"""
JS_DIV_001 — JavaScript Division by Zero Unit & Boundary Tests
===============================================================
Tests for literal zeros, -0, scientific notation, BigInt, undefined, and variables.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.js_division_by_zero import JavaScriptDivisionByZero
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, node, leaf, ident, number_lit, js_binop, js_unary,
)


def run_tests() -> bool:
    rule = JavaScriptDivisionByZero()
    r = RuleTestRunner("JS_DIV_001 — Unit & Boundary Tests")
    x = ident("x")

    # --- 1. DEFINITE ZERO LITERALS (MUST FLAG) ---
    r.must_flag("x / 0 (number literal)", rule, module(js_binop(x, "/", number_lit("0"))), "f.js")
    r.must_flag("x / 0.0 (float zero)", rule, module(js_binop(x, "/", number_lit("0.0"))), "f.js")
    r.must_flag("x / -0 (negative zero)", rule, module(js_binop(x, "/", js_unary("-", number_lit("0")))), "f.js")
    r.must_flag("x / 0e5 (scientific zero)", rule, module(js_binop(x, "/", number_lit("0e5"))), "f.js")
    r.must_flag("x / 00 (legacy octal zero)", rule, module(js_binop(x, "/", number_lit("00"))), "f.js")
    r.must_flag("x / undefined (coerces to NaN/0)", rule, module(js_binop(x, "/", node("undefined", "undefined"))), "f.js")

    # --- 2. DYNAMIC / VARIABLE DIVISORS (MUST FLAG) ---
    r.must_flag("x / y (variable divisor)", rule, module(js_binop(x, "/", ident("y"))), "f.js")

    # --- 3. DEFINITELY NON-ZERO LITERALS (MUST NOT FLAG) ---
    r.must_not_flag("x / 1 (integer 1)", rule, module(js_binop(x, "/", number_lit("1"))), "f.js")
    r.must_not_flag("x / 1.5 (float 1.5)", rule, module(js_binop(x, "/", number_lit("1.5"))), "f.js")
    r.must_not_flag("x / 1e0 (scientific 1)", rule, module(js_binop(x, "/", number_lit("1e0"))), "f.js")
    r.must_not_flag("x / 5n (BigInt non-zero)", rule, module(js_binop(x, "/", number_lit("5n"))), "f.js")
    r.must_not_flag("x / 0xFF (hex 255)", rule, module(js_binop(x, "/", number_lit("0xFF"))), "f.js")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
