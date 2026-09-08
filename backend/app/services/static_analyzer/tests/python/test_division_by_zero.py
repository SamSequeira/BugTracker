"""
PY_DIV_001 — Python Division by Zero Unit & Boundary Tests
===========================================================
Tests for literal zero detection, constant arithmetic folding, variable
initialization to zero, and straight-line/early-exit guard suppression.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.py_division_by_zero import PythonDivisionByZero
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, block, node, leaf, ident, integer, float_lit,
    unary, parens, binop_node, cond_expr, bool_op, call_node,
    if_stmt, assert_stmt, comparison, true_lit, false_lit,
)


def run_tests() -> bool:
    rule = PythonDivisionByZero()
    r = RuleTestRunner("PY_DIV_001 — Unit & Boundary Tests")
    x = ident("x")

    # --- 1. DEFINITE ZERO LITERALS & CONSTANTS (MUST FLAG) ---
    r.must_flag("x / 0 (integer literal)", rule, module(binop_node(x, "/", integer("0"))))
    r.must_flag("x // 0 (floor-division)", rule, module(binop_node(x, "//", integer("0"))))
    r.must_flag("x / 0.0 (float literal)", rule, module(binop_node(x, "/", float_lit("0.0"))))
    r.must_flag("x / -0 (negative zero)", rule, module(binop_node(x, "/", unary("-", integer("0")))))
    r.must_flag("x / +0 (positive zero)", rule, module(binop_node(x, "/", unary("+", integer("0")))))
    r.must_flag("x / -0.0 (negative float zero)", rule, module(binop_node(x, "/", unary("-", float_lit("0.0")))))
    r.must_flag("x / False (boolean false)", rule, module(binop_node(x, "/", false_lit())))
    r.must_flag("x / 0x0 (hexadecimal zero)", rule, module(binop_node(x, "/", integer("0x0"))))
    r.must_flag("x / 0b0 (binary zero)", rule, module(binop_node(x, "/", integer("0b0"))))
    r.must_flag("x / 0o0 (octal zero)", rule, module(binop_node(x, "/", integer("0o0"))))
    r.must_flag("x / (((0))) (nested parens zero)", rule, module(binop_node(x, "/", parens(parens(parens(integer("0")))))))
    r.must_flag("x / (1 - 1) (constant subtraction to zero)", rule, module(binop_node(x, "/", parens(binop_node(integer("1"), "-", integer("1"))))))
    r.must_flag("x / (0 * 5) (constant multiplication to zero)", rule, module(binop_node(x, "/", parens(binop_node(integer("0"), "*", integer("5"))))))
    r.must_flag("x / (2 - 2) (constant difference zero)", rule, module(binop_node(x, "/", parens(binop_node(integer("2"), "-", integer("2"))))))
    r.must_flag("f(x) / 0 (dividend is call, divisor is 0)", rule, module(binop_node(call_node("f", x), "/", integer("0"))))
    r.must_flag("x / (0 if c else 0) (all branches 0)", rule, module(binop_node(x, "/", parens(cond_expr(integer("0"), ident("c"), integer("0"))))))

    # --- 2. PROVABLY ZERO VARIABLES (MUST FLAG) ---
    assign_zero = node("assignment", "y = 0", children=[ident("y"), leaf("=", "="), integer("0")])
    r.must_flag("y = 0; x / y (variable initialized to zero)", rule, module(assign_zero, binop_node(x, "/", ident("y"))))

    # Variable inside `if y == 0:` branch
    if_zero_branch = if_stmt(comparison(ident("y"), "==", integer("0")), block(binop_node(x, "/", ident("y"))))
    r.must_flag("if y == 0: { x / y } (division inside zero branch)", rule, module(if_zero_branch))

    # --- 3. DYNAMIC / SAFE CODE PATTERNS (MUST NOT FLAG TO PREVENT FALSE POSITIVES) ---
    r.must_not_flag("x / y (unassigned parameter/variable)", rule, module(binop_node(x, "/", ident("y"))))
    r.must_not_flag("x / f() (function call divisor)", rule, module(binop_node(x, "/", call_node("f"))))
    r.must_not_flag("f(x) / g(y) (both dynamic expressions)", rule, module(binop_node(call_node("f", x), "/", call_node("g", ident("y")))))
    r.must_not_flag("x / obj.attr (attribute divisor)", rule, module(binop_node(x, "/", node("attribute", "obj.attr", children=[ident("obj"), leaf(".", "."), ident("attr")]))))
    r.must_not_flag("x / arr[0] (subscript divisor)", rule, module(binop_node(x, "/", node("subscript", "arr[0]", children=[ident("arr"), integer("0")]))))

    # --- 4. DEFINITELY NON-ZERO (PROVABLY SAFE) ---
    r.must_not_flag("x / 1 (positive integer)", rule, module(binop_node(x, "/", integer("1"))))
    r.must_not_flag("x / -1 (negative integer)", rule, module(binop_node(x, "/", unary("-", integer("1")))))
    r.must_not_flag("x / +1 (explicit positive integer)", rule, module(binop_node(x, "/", unary("+", integer("1")))))
    r.must_not_flag("x / 2.5 (positive float)", rule, module(binop_node(x, "/", float_lit("2.5"))))
    r.must_not_flag("x / -2.5 (negative float)", rule, module(binop_node(x, "/", unary("-", float_lit("2.5")))))
    r.must_not_flag("x / True (boolean true)", rule, module(binop_node(x, "/", true_lit())))
    r.must_not_flag("x / 0xFF (hexadecimal non-zero)", rule, module(binop_node(x, "/", integer("0xFF"))))
    r.must_not_flag("x / 0b1 (binary non-zero)", rule, module(binop_node(x, "/", integer("0b1"))))
    r.must_not_flag("x / 0o17 (octal 15)", rule, module(binop_node(x, "/", integer("0o17"))))
    r.must_not_flag("x / 0b1010 (binary 10)", rule, module(binop_node(x, "/", integer("0b1010"))))
    r.must_not_flag("x // 3 (safe floor-div)", rule, module(binop_node(x, "//", integer("3"))))
    r.must_not_flag("x / (1 + 1) (constant sum non-zero)", rule, module(binop_node(x, "/", parens(binop_node(integer("1"), "+", integer("1"))))))
    r.must_not_flag("x / (1 if c else 2) (all branches non-zero)", rule, module(binop_node(x, "/", parens(cond_expr(integer("1"), ident("c"), integer("2"))))))
    r.must_not_flag("x / (y or 1) (or with non-zero fallback)", rule, module(binop_node(x, "/", parens(bool_op(ident("y"), "or", integer("1"))))))
    r.must_not_flag("x / max(1, y) (max with non-zero bound)", rule, module(binop_node(x, "/", call_node("max", integer("1"), ident("y")))))
    r.must_not_flag("x / (d + 1) (positive offset)", rule, module(binop_node(x, "/", parens(binop_node(ident("d"), "+", integer("1"))))))
    r.must_not_flag("x / (d + 1e-8) (epsilon smoothing)", rule, module(binop_node(x, "/", parens(binop_node(ident("d"), "+", float_lit("1e-8"))))))

    # --- 5. CONTROL-FLOW & GUARD SUPPRESSION ---
    divisor = node("identifier", "divisor", 12)
    guard = if_stmt(comparison(node("identifier", "divisor", 10), "!=", integer("0", 10), 10), block(), 10)
    r.must_not_flag("if divisor != 0: guard suppresses following division", rule, module(guard, binop_node(x, "/", divisor, 12)))

    divisor2 = node("identifier", "divisor", 22)
    guard2 = if_stmt(node("identifier", "divisor", 20), block(), 20)
    r.must_not_flag("if divisor: truthy guard suppresses following division", rule, module(guard2, binop_node(x, "/", divisor2, 22)))

    divisor3 = node("identifier", "divisor", 32)
    guard3 = assert_stmt(comparison(node("identifier", "divisor", 30), "!=", integer("0", 30), 30), line=30)
    r.must_not_flag("assert divisor != 0: suppresses following division", rule, module(guard3, binop_node(x, "/", divisor3, 32)))

    divisor4 = node("identifier", "divisor", 42)
    guard4 = assert_stmt(node("identifier", "divisor", 40), line=40)
    r.must_not_flag("assert divisor: suppresses following division", rule, module(guard4, binop_node(x, "/", divisor4, 42)))

    # Early exit guards (if d == 0: return; x / d)
    early_exit_guard = if_stmt(
        comparison(ident("d"), "==", integer("0")),
        block(node("return_statement", "return")),
    )
    r.must_not_flag("if d == 0: return; x / d -> early exit protects subsequent division", rule, module(early_exit_guard, binop_node(x, "/", ident("d"))))

    # Inequality guard (if d > 0: pass; x / d)
    gt_guard = if_stmt(comparison(ident("d"), ">", integer("0")), block())
    r.must_not_flag("if d > 0: pass; x / d -> inequality guard", rule, module(gt_guard, binop_node(x, "/", ident("d"))))

    # Guard inside branch protects branch only
    inner_div_guarded = binop_node(x, "/", ident("d", 12), 12)
    guard_in_branch = if_stmt(comparison(ident("d", 11), "!=", integer("0", 11), 11), block(inner_div_guarded), line=11)
    r.must_not_flag("if d != 0: { x / d } -> protected inside then-block", rule, module(guard_in_branch))

    # Try-except block catching ZeroDivisionError
    try_catch = node("try_statement", "try ... except ZeroDivisionError", children=[
        leaf("try", "try"),
        block(binop_node(x, "/", ident("d"))),
        node("except_clause", "except ZeroDivisionError:", children=[
            leaf("except", "except"),
            ident("ZeroDivisionError"),
            block(node("pass_statement", "pass")),
        ]),
    ])
    r.must_not_flag("try: x / d except ZeroDivisionError: pass -> protected by exception handler", rule, module(try_catch))

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
