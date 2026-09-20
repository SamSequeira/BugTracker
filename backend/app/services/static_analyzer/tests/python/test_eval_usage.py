"""
PY_EVAL_001 — Python Dynamic Eval/Exec Usage Unit & Boundary Tests
==================================================================
Tests for dangerous eval/exec usage with dynamic or untrusted strings.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.py_eval_usage import PythonEvalUsage
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, call_node, ident, string_lit, leaf, node,
)


def run_tests() -> bool:
    rule = PythonEvalUsage()
    r = RuleTestRunner("PY_EVAL_001 — Unit & Boundary Tests")

    # --- 1. DYNAMIC EVAL / EXEC (MUST FLAG) ---
    r.must_flag("eval(user_input) (dynamic variable input)", rule, module(call_node("eval", ident("user_input"))))
    r.must_flag("exec(code_str) (dynamic exec input)", rule, module(call_node("exec", ident("code_str"))))
    r.must_flag("eval(f'result_{x}') (f-string expression in eval)", rule, module(call_node("eval", node("formatted_string", "f'result_{x}'"))))

    # --- 2. SAFE CONSTANT LITERALS / STATIC EVAL (MUST NOT FLAG) ---
    r.must_not_flag("eval('1 + 1') (constant static literal string)", rule, module(call_node("eval", string_lit("'1 + 1'"))))
    r.must_not_flag("ast.literal_eval(data) (safe literal_eval helper)", rule, module(call_node("ast.literal_eval", ident("data"))))
    r.must_not_flag("my_eval(code) (custom function named eval suffix)", rule, module(call_node("my_eval", ident("code"))))

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
