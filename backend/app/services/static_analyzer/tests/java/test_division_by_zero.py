"""
JAVA_DIV_001 — Java Division by Zero Unit & Boundary Tests
===========================================================
Tests for literal zeros, constant numeric folding, casts, and variable divisors.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.java_division_by_zero import JavaDivisionByZero
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, ident, node, leaf,
    java_binop, java_decimal_int, java_decimal_float, java_hex_int,
)


def run_tests() -> bool:
    rule = JavaDivisionByZero()
    r = RuleTestRunner("JAVA_DIV_001 — Unit & Boundary Tests")
    x = ident("x")

    # --- 1. DEFINITE ZERO LITERALS (MUST FLAG) ---
    r.must_flag("x / 0 (decimal int zero)", rule, module(java_binop(x, "/", java_decimal_int("0"))), "T.java")
    r.must_flag("x / 0.0 (decimal float zero)", rule, module(java_binop(x, "/", java_decimal_float("0.0"))), "T.java")
    r.must_flag("x / 0.0f (float literal zero)", rule, module(java_binop(x, "/", java_decimal_float("0.0f"))), "T.java")
    r.must_flag("x / 0L (long zero)", rule, module(java_binop(x, "/", java_decimal_int("0L"))), "T.java")
    r.must_flag("x / 0_0 (zero with separator)", rule, module(java_binop(x, "/", java_decimal_int("0_0"))), "T.java")
    r.must_flag("x / 0x0 (hexadecimal zero)", rule, module(java_binop(x, "/", java_hex_int("0x0"))), "T.java")
    r.must_flag("x / 0x00 (multi-digit hex zero)", rule, module(java_binop(x, "/", java_hex_int("0x00"))), "T.java")
    r.must_flag("x / 00 (octal zero literal)", rule, module(java_binop(x, "/", java_decimal_int("00"))), "T.java")

    # --- 2. ZERO VARIABLE (MUST FLAG) ---
    assign_zero = node("local_variable_declaration", "int divisor = 0;", 1, children=[
        node("integral_type", "int", 1),
        node("variable_declarator", "divisor = 0", 1, children=[ident("divisor", 1), leaf("=", "=", 1), java_decimal_int("0", 1)])
    ])
    r.must_flag("int divisor = 0; x / divisor", rule, module(assign_zero, java_binop(x, "/", ident("divisor", 2), 2)), "T.java")

    # --- 3. DYNAMIC / UNKNOWN DIVISORS (MUST NOT FLAG) ---
    r.must_not_flag("x / y (unknown variable divisor)", rule, module(java_binop(x, "/", ident("y"))), "T.java")

    cast_expr = node("cast_expression", "(int) b", children=[
        leaf("(", "("), node("integral_type", "int"), leaf(")", ")"), ident("b")
    ])
    r.must_not_flag("x / (int)b (unknown cast expression)", rule, module(java_binop(x, "/", cast_expr)), "T.java")

    # --- 3. DEFINITELY NON-ZERO LITERALS (MUST NOT FLAG) ---
    r.must_not_flag("x / 1 (decimal int 1)", rule, module(java_binop(x, "/", java_decimal_int("1"))), "T.java")
    r.must_not_flag("x / 1.5 (decimal float 1.5)", rule, module(java_binop(x, "/", java_decimal_float("1.5"))), "T.java")
    r.must_not_flag("x / 10L (long 10)", rule, module(java_binop(x, "/", java_decimal_int("10L"))), "T.java")
    r.must_not_flag("x / 1_000 (int with separator)", rule, module(java_binop(x, "/", java_decimal_int("1_000"))), "T.java")
    r.must_not_flag("x / 0xFF (hex 255)", rule, module(java_binop(x, "/", java_hex_int("0xFF"))), "T.java")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
"""
JAVA_DIV_001 — Java Division by Zero Unit & Boundary Tests
===========================================================
Tests for literal zeros, constant numeric folding, casts, and variable divisors.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.java_division_by_zero import JavaDivisionByZero
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, ident, node, leaf,
    java_binop, java_decimal_int, java_decimal_float, java_hex_int,
)


def run_tests() -> bool:
    rule = JavaDivisionByZero()
    r = RuleTestRunner("JAVA_DIV_001 — Unit & Boundary Tests")
    x = ident("x")

    # --- 1. DEFINITE ZERO LITERALS (MUST FLAG) ---
    r.must_flag("x / 0 (decimal int zero)", rule, module(java_binop(x, "/", java_decimal_int("0"))), "T.java")
    r.must_flag("x / 0.0 (decimal float zero)", rule, module(java_binop(x, "/", java_decimal_float("0.0"))), "T.java")
    r.must_flag("x / 0.0f (float literal zero)", rule, module(java_binop(x, "/", java_decimal_float("0.0f"))), "T.java")
    r.must_flag("x / 0L (long zero)", rule, module(java_binop(x, "/", java_decimal_int("0L"))), "T.java")
    r.must_flag("x / 0_0 (zero with separator)", rule, module(java_binop(x, "/", java_decimal_int("0_0"))), "T.java")
    r.must_flag("x / 0x0 (hexadecimal zero)", rule, module(java_binop(x, "/", java_hex_int("0x0"))), "T.java")
    r.must_flag("x / 0x00 (multi-digit hex zero)", rule, module(java_binop(x, "/", java_hex_int("0x00"))), "T.java")
    r.must_flag("x / 00 (octal zero literal)", rule, module(java_binop(x, "/", java_decimal_int("00"))), "T.java")

    # --- 2. DYNAMIC / UNKNOWN DIVISORS (MUST FLAG) ---
    r.must_flag("x / y (variable divisor)", rule, module(java_binop(x, "/", ident("y"))), "T.java")

    cast_expr = node("cast_expression", "(int) b", children=[
        leaf("(", "("), node("integral_type", "int"), leaf(")", ")"), ident("b")
    ])
    r.must_flag("x / (int)b (cast expression)", rule, module(java_binop(x, "/", cast_expr)), "T.java")

    # --- 3. DEFINITELY NON-ZERO LITERALS (MUST NOT FLAG) ---
    r.must_not_flag("x / 1 (decimal int 1)", rule, module(java_binop(x, "/", java_decimal_int("1"))), "T.java")
    r.must_not_flag("x / 1.5 (decimal float 1.5)", rule, module(java_binop(x, "/", java_decimal_float("1.5"))), "T.java")
    r.must_not_flag("x / 10L (long 10)", rule, module(java_binop(x, "/", java_decimal_int("10L"))), "T.java")
    r.must_not_flag("x / 1_000 (int with separator)", rule, module(java_binop(x, "/", java_decimal_int("1_000"))), "T.java")
    r.must_not_flag("x / 0xFF (hex 255)", rule, module(java_binop(x, "/", java_hex_int("0xFF"))), "T.java")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
