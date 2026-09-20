"""
PY_UNREACH_001 — Python Unreachable Code Unit & Boundary Tests
==============================================================
Tests for code following unconditional termination statements (return, raise, break, continue, try/finally).
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.py_unreachable_code import PythonUnreachableCode
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, block, py_def, py_params, ident, integer,
    return_stmt, leaf, node,
)


def run_tests() -> bool:
    rule = PythonUnreachableCode()
    r = RuleTestRunner("PY_UNREACH_001 — Unit & Boundary Tests")

    # --- 1. CODE AFTER RETURN / RAISE (MUST FLAG) ---
    ret_stmt = node("return_statement", "return 1", children=[leaf("return", "return"), integer("1")])
    after_stmt = node("expression_statement", "x = 2", children=[node("assignment", "x = 2", children=[ident("x"), leaf("=", "="), integer("2")])])
    fn_body = block(ret_stmt, after_stmt)
    fn_ast = module(py_def(py_params(), fn_body, "f"))
    r.must_flag("def f(): return 1; x = 2 (unreachable after return)", rule, fn_ast)

    raise_stmt = node("raise_statement", "raise ValueError()", children=[leaf("raise", "raise"), ident("ValueError")])
    fn_raise = module(py_def(py_params(), block(raise_stmt, after_stmt), "g"))
    r.must_flag("def g(): raise ValueError(); x = 2 (unreachable after raise)", rule, fn_raise)

    # --- 2. TRY/FINALLY UNREACHABLE CODE (MUST FLAG) ---
    try_stmt = node("try_statement", "try: return 1\nfinally: cleanup()", children=[
        leaf("try", "try"),
        leaf(":", ":"),
        block(ret_stmt),
        node("finally_clause", "finally: cleanup()", children=[
            leaf("finally", "finally"),
            leaf(":", ":"),
            block(node("expression_statement", "cleanup()")),
        ]),
    ])
    try_fn = module(py_def(py_params(), block(try_stmt, after_stmt), "h"))
    r.must_flag("try: return 1 finally: cleanup(); x = 2 (unreachable after try-finally)", rule, try_fn)

    # --- 3. REACHABLE CODE (MUST NOT FLAG) ---
    reachable_fn = module(py_def(py_params(), block(after_stmt, ret_stmt), "ok_fn"))
    r.must_not_flag("def ok_fn(): x = 2; return 1 (reachable statement before return)", rule, reachable_fn)

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
