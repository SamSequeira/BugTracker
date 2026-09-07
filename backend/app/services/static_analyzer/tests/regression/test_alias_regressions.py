"""
Regression Suite: Mutable Alias Propagation & Invalidation
===========================================================
Validates W08 and Phase 5.7 alias-tracking guarantees in PY_MUT_001.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.py_mutable_default_arg import PythonMutableDefaultArg
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, block, node, leaf, ident, integer,
    py_def, py_params, py_default_param, py_list, py_dict,
)


def run_tests() -> bool:
    rule = PythonMutableDefaultArg()
    r = RuleTestRunner("Regression â€” Mutable Alias Tracking")

    # --- 1. W08: MUTABLE VARIABLE DEFAULT ASSIGNMENT ---
    a_list = node("assignment", "GLOBAL_LIST = []", 1, children=[ident("GLOBAL_LIST", 1), leaf("=", "=", 1), py_list(1)])
    fn_glob = py_def(py_params(py_default_param("x", ident("GLOBAL_LIST", 3))), block(), "f", line=3)
    r.must_flag("W08: GLOBAL_LIST = []; def f(x=GLOBAL_LIST) -> resolved mutable default", rule, module(a_list, fn_glob))

    # --- 2. ALIAS REASSIGNED TO IMMUTABLE (MUST NOT FLAG) ---
    a_init = node("assignment", "a = []", 1, children=[ident("a", 1), leaf("=", "=", 1), py_list(1)])
    b_is_a = node("assignment", "b = a", 2, children=[ident("b", 2), leaf("=", "=", 2), ident("a", 2)])
    b_is_1 = node("assignment", "b = 1", 3, children=[ident("b", 3), leaf("=", "=", 3), integer("1", 3)])
    fn_fb = py_def(py_params(py_default_param("x", ident("b", 5))), block(), "f", line=5)
    r.must_not_flag("a=[]; b=a; b=1; def f(x=b) -> b rebound to immutable int -> safe", rule, module(a_init, b_is_a, b_is_1, fn_fb))

    # --- 3. ORIGINAL REASSIGNED TO IMMUTABLE (ALIAS REMAINS MUTABLE) ---
    a_is_1 = node("assignment", "a = 1", 3, children=[ident("a", 3), leaf("=", "=", 3), integer("1", 3)])
    r.must_flag("a=[]; b=a; a=1; def f(x=b) -> b retains mutable list reference -> flagged", rule, module(a_init, b_is_a, a_is_1, fn_fb))

    # --- 4. MULTI-STEP ALIAS PROPAGATION ---
    c_is_b = node("assignment", "c = b", 3, children=[ident("c", 3), leaf("=", "=", 3), ident("b", 3)])
    fn_fc = py_def(py_params(py_default_param("x", ident("c", 5))), block(), "f", line=5)
    r.must_flag("a=[]; b=a; c=b; def f(x=c) -> 3-step alias chain resolved to mutable", rule, module(a_init, b_is_a, c_is_b, fn_fc))

    # --- 5. ALIAS TO IMMUTABLE INITIAL VALUE ---
    a_num = node("assignment", "a = 1", 1, children=[ident("a", 1), leaf("=", "=", 1), integer("1", 1)])
    r.must_not_flag("a=1; b=a; def f(x=b) -> alias to immutable int -> safe", rule, module(a_num, b_is_a, fn_fb))

    # --- 6. REBOUND TO NEW MUTABLE OBJECT ---
    b_is_dict = node("assignment", "b = {}", 3, children=[ident("b", 3), leaf("=", "=", 3), py_dict(3)])
    r.must_flag("a=[]; b=a; b={}; def f(x=b) -> rebound to new mutable dict -> flagged", rule, module(a_init, b_is_a, b_is_dict, fn_fb))

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)

"""
Regression Suite: Mutable Alias Propagation & Invalidation
===========================================================
Validates alias-tracking guarantees in PY_MUT_001.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.py_mutable_default_arg import PythonMutableDefaultArg
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, block, node, leaf, ident, integer,
    py_def, py_params, py_default_param, py_list, py_dict,
)


def run_tests() -> bool:
    rule = PythonMutableDefaultArg()
    r = RuleTestRunner("Regression — Mutable Alias Tracking")

    # --- 1. W08: MUTABLE VARIABLE DEFAULT ASSIGNMENT ---
    a_list = node("assignment", "GLOBAL_LIST = []", 1, children=[ident("GLOBAL_LIST", 1), leaf("=", "=", 1), py_list(1)])
    fn_glob = py_def(py_params(py_default_param("x", ident("GLOBAL_LIST", 3))), block(), "f", line=3)
    r.must_flag("W08: GLOBAL_LIST = []; def f(x=GLOBAL_LIST) -> resolved mutable default", rule, module(a_list, fn_glob))

    # --- 2. ALIAS REASSIGNED TO IMMUTABLE (MUST NOT FLAG) ---
    a_init = node("assignment", "a = []", 1, children=[ident("a", 1), leaf("=", "=", 1), py_list(1)])
    b_is_a = node("assignment", "b = a", 2, children=[ident("b", 2), leaf("=", "=", 2), ident("a", 2)])
    b_is_1 = node("assignment", "b = 1", 3, children=[ident("b", 3), leaf("=", "=", 3), integer("1", 3)])
    fn_fb = py_def(py_params(py_default_param("x", ident("b", 5))), block(), "f", line=5)
    r.must_not_flag("a=[]; b=a; b=1; def f(x=b) -> b rebound to immutable int -> safe", rule, module(a_init, b_is_a, b_is_1, fn_fb))

    # --- 3. ORIGINAL REASSIGNED TO IMMUTABLE (ALIAS REMAINS MUTABLE) ---
    a_is_1 = node("assignment", "a = 1", 3, children=[ident("a", 3), leaf("=", "=", 3), integer("1", 3)])
    r.must_flag("a=[]; b=a; a=1; def f(x=b) -> b retains mutable list reference -> flagged", rule, module(a_init, b_is_a, a_is_1, fn_fb))

    # --- 4. MULTI-STEP ALIAS PROPAGATION ---
    c_is_b = node("assignment", "c = b", 3, children=[ident("c", 3), leaf("=", "=", 3), ident("b", 3)])
    fn_fc = py_def(py_params(py_default_param("x", ident("c", 5))), block(), "f", line=5)
    r.must_flag("a=[]; b=a; c=b; def f(x=c) -> 3-step alias chain resolved to mutable", rule, module(a_init, b_is_a, c_is_b, fn_fc))

    # --- 5. ALIAS TO IMMUTABLE INITIAL VALUE ---
    a_num = node("assignment", "a = 1", 1, children=[ident("a", 1), leaf("=", "=", 1), integer("1", 1)])
    r.must_not_flag("a=1; b=a; def f(x=b) -> alias to immutable int -> safe", rule, module(a_num, b_is_a, fn_fb))

    # --- 6. REBOUND TO NEW MUTABLE OBJECT ---
    b_is_dict = node("assignment", "b = {}", 3, children=[ident("b", 3), leaf("=", "=", 3), py_dict(3)])
    r.must_flag("a=[]; b=a; b={}; def f(x=b) -> rebound to new mutable dict -> flagged", rule, module(a_init, b_is_a, b_is_dict, fn_fb))

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
