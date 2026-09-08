"""
Regression Suite: Lexical Scope Isolation & Closures
=====================================================
Validates FN-1, W02, W14, and Phase 5.7 scope-isolation guarantees.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.py_division_by_zero import PythonDivisionByZero
from app.services.static_analyzer.rules.py_mutable_default_arg import PythonMutableDefaultArg
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, block, node, leaf, ident, integer,
    binop_node, if_stmt, comparison, py_def, py_params, py_default_param, py_list,
)


def run_tests() -> bool:
    r = RuleTestRunner("Regression â€” Scope Isolation & Closures")
    py_div = PythonDivisionByZero()
    py_mut = PythonMutableDefaultArg()
    x = ident("x")

    # --- 1. FN-1 / W02: OUTER GUARD MUST NOT CROSS FUNCTION BOUNDARIES ---
    outer_g = if_stmt(comparison(ident("d", 10), "!=", integer("0", 10), 10), block(), 10)
    inner_div = binop_node(x, "/", ident("d", 52), 52)
    inner_fn = py_def(py_params(), block(inner_div), "inner", line=50)
    r.must_flag("FN-1 / W02: outer guard d!=0 must NOT suppress inner function's x/d", py_div, module(outer_g, inner_fn))

    # --- 2. OUTER CONSTANT ZERO CAPTURE INTO CLOSURE ---
    outer_d0 = node("assignment", "d = 0", 1, children=[ident("d", 1), leaf("=", "=", 1), integer("0", 1)])
    r.must_flag("outer d=0 captured by def inner(): return x / d (flagged as zero)", py_div, module(outer_d0, inner_fn))

    # Outer non-zero constant is conservative across function boundary
    outer_d1 = node("assignment", "d = 1", 1, children=[ident("d", 1), leaf("=", "=", 1), integer("1", 1)])
    issues_d1 = list(py_div.analyze(module(outer_d1, inner_fn), "f.py", []))
    if len(issues_d1) == 1 and issues_d1[0].evidence.get("classification") == "potentially_zero":
        r._passes += 1
        print("  OK   [conservative  ] outer d=1 in closure treated as potentially_zero")
    else:
        r._failures.append("  FAIL [conservative  ] outer d=1 in closure should be potentially_zero")

    # --- 3. LOCAL VARIABLE SHADOWING IN INNER FUNCTION ---
    inner_d1 = node("assignment", "d = 1", 4, children=[ident("d", 4), leaf("=", "=", 4), integer("1", 4)])
    inner_safe_fn = py_def(py_params(), block(inner_d1, inner_div), "inner", line=3)
    r.must_not_flag("local d=1 inside inner function shadows outer d=0 (provably safe)", py_div, module(outer_d0, inner_safe_fn))

    inner_d0 = node("assignment", "d = 0", 4, children=[ident("d", 4), leaf("=", "=", 4), integer("0", 4)])
    inner_zero_fn = py_def(py_params(), block(inner_d0, inner_div), "inner", line=3)
    r.must_flag("local d=0 inside inner function shadows outer d=1 (flagged as zero)", py_div, module(outer_d1, inner_zero_fn))

    # --- 4. FORMAL PARAMETER SHADOWING ---
    param_d = node("identifier", "d", 60)
    param_fn = py_def(py_params(param_d), block(inner_div), "inner", line=60)
    r.must_flag("parameter d shadows outer d=0 as fresh dynamic binding", py_div, module(outer_d0, param_fn))

    # --- 5. 3-LEVEL CLOSURE CAPTURE ---
    level3 = py_def(py_params(), block(inner_div), "level3", line=5)
    level2 = py_def(py_params(), block(level3), "level2", line=4)
    level1 = py_def(py_params(), block(level2), "level1", line=3)
    r.must_flag("3-level nested closure x/d correctly inherits outer zero fact", py_div, module(outer_d0, level1))

    # --- 6. CLASS METHOD BOUNDARY ---
    class_def = node("class_definition", "class A: ...", 3, children=[
        leaf("class", "class", 3), ident("A", 3), leaf(":", ":", 3),
        block(py_def(py_params(ident("self", 4)), block(inner_div), "f", line=4))
    ])
    r.must_flag("class method x/d captures outer zero fact", py_div, module(outer_d0, class_def))

    # --- 7. PY_MUT_001 SCOPE ISOLATION ---
    local_a1 = node("assignment", "a = 1", 5, children=[ident("a", 5), leaf("=", "=", 5), integer("1", 5)])
    fn_f = py_def(py_params(), block(local_a1), "f", line=4)
    a_list = node("assignment", "a = []", 1, children=[ident("a", 1), leaf("=", "=", 1), py_list(1)])
    fn_other = py_def(py_params(py_default_param("x", ident("a", 10))), block(), "other", line=10)
    r.must_flag("PY_MUT_001: local a=1 in f() does not corrupt module-level a=[] for other(x=a)", py_mut, module(a_list, fn_f, fn_other))

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)

"""
Regression Suite: Lexical Scope Isolation & Closures
=====================================================
Validates scope-isolation guarantees.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.py_division_by_zero import PythonDivisionByZero
from app.services.static_analyzer.rules.py_mutable_default_arg import PythonMutableDefaultArg
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, block, node, leaf, ident, integer,
    binop_node, if_stmt, comparison, py_def, py_params, py_default_param, py_list,
)


def run_tests() -> bool:
    r = RuleTestRunner("Regression — Scope Isolation & Closures")
    py_div = PythonDivisionByZero()
    py_mut = PythonMutableDefaultArg()
    x = ident("x")

    # --- 1. FN-1 / W02: OUTER GUARD MUST NOT CROSS FUNCTION BOUNDARIES ---
    outer_g = if_stmt(comparison(ident("d", 10), "!=", integer("0", 10), 10), block(), 10)
    inner_div = binop_node(x, "/", ident("d", 52), 52)
    inner_fn = py_def(py_params(), block(inner_div), "inner", line=50)
    r.must_flag("FN-1 / W02: outer guard d!=0 must NOT suppress inner function's x/d", py_div, module(outer_g, inner_fn))

    # --- 2. OUTER CONSTANT ZERO CAPTURE INTO CLOSURE ---
    outer_d0 = node("assignment", "d = 0", 1, children=[ident("d", 1), leaf("=", "=", 1), integer("0", 1)])
    r.must_flag("outer d=0 captured by def inner(): return x / d (flagged as zero)", py_div, module(outer_d0, inner_fn))

    # Outer non-zero constant is conservative across function boundary
    outer_d1 = node("assignment", "d = 1", 1, children=[ident("d", 1), leaf("=", "=", 1), integer("1", 1)])
    issues_d1 = list(py_div.analyze(module(outer_d1, inner_fn), "f.py", []))
    if len(issues_d1) == 1 and issues_d1[0].evidence.get("classification") == "potentially_zero":
        r._passes += 1
        print("  OK   [conservative  ] outer d=1 in closure treated as potentially_zero")
    else:
        r._failures.append("  FAIL [conservative  ] outer d=1 in closure should be potentially_zero")

    # --- 3. LOCAL VARIABLE SHADOWING IN INNER FUNCTION ---
    inner_d1 = node("assignment", "d = 1", 4, children=[ident("d", 4), leaf("=", "=", 4), integer("1", 4)])
    inner_safe_fn = py_def(py_params(), block(inner_d1, inner_div), "inner", line=3)
    r.must_not_flag("local d=1 inside inner function shadows outer d=0 (provably safe)", py_div, module(outer_d0, inner_safe_fn))

    inner_d0 = node("assignment", "d = 0", 4, children=[ident("d", 4), leaf("=", "=", 4), integer("0", 4)])
    inner_zero_fn = py_def(py_params(), block(inner_d0, inner_div), "inner", line=3)
    r.must_flag("local d=0 inside inner function shadows outer d=1 (flagged as zero)", py_div, module(outer_d1, inner_zero_fn))

    # --- 4. FORMAL PARAMETER SHADOWING ---
    param_d = node("identifier", "d", 60)
    param_fn = py_def(py_params(param_d), block(inner_div), "inner", line=60)
    r.must_flag("parameter d shadows outer d=0 as fresh dynamic binding", py_div, module(outer_d0, param_fn))

    # --- 5. 3-LEVEL CLOSURE CAPTURE ---
    level3 = py_def(py_params(), block(inner_div), "level3", line=5)
    level2 = py_def(py_params(), block(level3), "level2", line=4)
    level1 = py_def(py_params(), block(level2), "level1", line=3)
    r.must_flag("3-level nested closure x/d correctly inherits outer zero fact", py_div, module(outer_d0, level1))

    # --- 6. CLASS METHOD BOUNDARY ---
    class_def = node("class_definition", "class A: ...", 3, children=[
        leaf("class", "class", 3), ident("A", 3), leaf(":", ":", 3),
        block(py_def(py_params(ident("self", 4)), block(inner_div), "f", line=4))
    ])
    r.must_flag("class method x/d captures outer zero fact", py_div, module(outer_d0, class_def))

    # --- 7. PY_MUT_001 SCOPE ISOLATION ---
    local_a1 = node("assignment", "a = 1", 5, children=[ident("a", 5), leaf("=", "=", 5), integer("1", 5)])
    fn_f = py_def(py_params(), block(local_a1), "f", line=4)
    a_list = node("assignment", "a = []", 1, children=[ident("a", 1), leaf("=", "=", 1), py_list(1)])
    fn_other = py_def(py_params(py_default_param("x", ident("a", 10))), block(), "other", line=10)
    r.must_flag("PY_MUT_001: local a=1 in f() does not corrupt module-level a=[] for other(x=a)", py_mut, module(a_list, fn_f, fn_other))

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
