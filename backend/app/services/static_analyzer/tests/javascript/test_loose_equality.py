"""
JS_EQ_001 — JavaScript Loose Equality Unit & Boundary Tests
============================================================
Tests for loose == and != operators and typeof comparison exemptions.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.js_triple_equals import JavaScriptTripleEquals
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, node, leaf, ident, js_binop, js_unary,
)


def run_tests() -> bool:
    rule = JavaScriptTripleEquals()
    r = RuleTestRunner("JS_EQ_001 — Unit & Boundary Tests")
    x = ident("x")
    y = ident("y")

    # --- 1. LOOSE EQUALITY (MUST FLAG) ---
    r.must_flag("x == y (loose equality variables)", rule, module(js_binop(x, "==", y)), "f.js")
    r.must_flag("x != y (loose inequality variables)", rule, module(js_binop(x, "!=", y)), "f.js")
    r.must_flag("x == 'a==b' (string literal operand)", rule, module(js_binop(x, "==", leaf("string_fragment", "'a==b'"))), "f.js")
    r.must_flag("x == /pattern/ (regex literal operand)", rule, module(js_binop(x, "==", node("regex", "/pattern/"))), "f.js")
    r.must_flag("!x == y (negation operand)", rule, module(js_binop(js_unary("!", x), "==", y)), "f.js")
    r.must_flag("NaN == NaN (NaN comparison)", rule, module(js_binop(ident("NaN"), "==", ident("NaN"))), "f.js")
    r.must_flag("x == 'undefined' (string 'undefined' is not typeof)", rule, module(js_binop(x, "==", leaf("string_fragment", "'undefined'"))), "f.js")

    # --- 2. EXEMPTIONS: NULL IDIOM & TYPEOF (MUST NOT FLAG) ---
    r.must_not_flag("x == null (idiomatic null check catches null & undefined)", rule, module(js_binop(x, "==", leaf("null", "null"))), "f.js")
    r.must_not_flag("null != x (reversed null check)", rule, module(js_binop(leaf("null", "null"), "!=", x)), "f.js")
    typeof_expr = node("unary_expression", "typeof x", children=[leaf("typeof", "typeof"), ident("x")])
    r.must_not_flag("typeof x == 'string' (typeof exemption)", rule, module(js_binop(typeof_expr, "==", leaf("string_fragment", "'string'"))), "f.js")
    r.must_not_flag("typeof x != 'undefined' (typeof inequality exemption)", rule, module(js_binop(typeof_expr, "!=", leaf("string_fragment", "'undefined'"))), "f.js")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
