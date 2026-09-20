"""
JS_EVAL_001 — JavaScript Dynamic Eval Usage Unit & Boundary Tests
================================================================
Tests for dangerous eval() execution with dynamic or non-literal arguments.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.js_eval_usage import JavaScriptEvalUsage
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, call_node, ident, string_lit, node, leaf,
)


def run_tests() -> bool:
    rule = JavaScriptEvalUsage()
    r = RuleTestRunner("JS_EVAL_001 — Unit & Boundary Tests")

    # --- 1. DYNAMIC EVAL (MUST FLAG) ---
    r.must_flag("eval(userInput) (dynamic variable input)", rule, module(call_node("eval", ident("userInput"))), file_path="app.js")
    r.must_flag("eval('result_' + id) (string concatenation in eval)", rule,
                module(call_node("eval", node("binary_expression", "'result_' + id", children=[
                    string_lit("'result_'"), leaf("+", "+"), ident("id")
                ]))), file_path="app.js")

    # --- 2. SAFE STATIC EVAL / CUSTOM FUNCTIONS (MUST NOT FLAG) ---
    r.must_not_flag("eval('42') (static constant string literal)", rule, module(call_node("eval", string_lit("'42'"))), file_path="app.js")
    r.must_not_flag("customEval(userInput) (non-global eval call)", rule, module(call_node("customEval", ident("userInput"))), file_path="app.js")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
