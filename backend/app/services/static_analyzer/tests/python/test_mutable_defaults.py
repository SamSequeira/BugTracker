"""
PY_MUT_001 — Python Mutable Default Argument Unit & Boundary Tests
===================================================================
Tests for mutable default parameters in functions and lambdas.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.py_mutable_default_arg import PythonMutableDefaultArg
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, block, node, leaf, ident, integer,
    py_def, py_params, py_default_param, py_list, py_dict, py_set_call, call_node,
)


def run_tests() -> bool:
    rule = PythonMutableDefaultArg()
    r = RuleTestRunner("PY_MUT_001 — Unit & Boundary Tests")

    # --- 1. DIRECT MUTABLE LITERALS (MUST FLAG) ---
    r.must_flag("def f(x=[]): (empty list literal)", rule,
                module(py_def(py_params(py_default_param("x", py_list())), block(), "f")))

    r.must_flag("def f(x={}): (empty dict literal)", rule,
                module(py_def(py_params(py_default_param("x", py_dict())), block(), "f")))

    set_display = node("set", "{1, 2}", children=[integer("1"), integer("2")])
    r.must_flag("def f(x={1, 2}): (set literal display)", rule,
                module(py_def(py_params(py_default_param("x", set_display)), block(), "f")))

    # --- 2. MUTABLE CONSTRUCTOR CALLS (MUST FLAG) ---
    r.must_flag("def f(x=set()): (set constructor call)", rule,
                module(py_def(py_params(py_default_param("x", py_set_call())), block(), "f")))

    r.must_flag("def f(x=list()): (list constructor call)", rule,
                module(py_def(py_params(py_default_param("x", call_node("list"))), block(), "f")))

    r.must_flag("def f(x=dict()): (dict constructor call)", rule,
                module(py_def(py_params(py_default_param("x", call_node("dict"))), block(), "f")))

    r.must_flag("def f(x=bytearray()): (bytearray constructor call)", rule,
                module(py_def(py_params(py_default_param("x", call_node("bytearray"))), block(), "f")))

    # --- 3. MUTABLE IDENTIFIER DEFAULTS (MUST FLAG) ---
    a_list = node("assignment", "GLOBAL_LIST = []", 1, children=[ident("GLOBAL_LIST", 1), leaf("=", "=", 1), py_list(1)])
    fn_glob = py_def(py_params(py_default_param("x", ident("GLOBAL_LIST", 3))), block(), "f", line=3)
    r.must_flag("GLOBAL_LIST = []; def f(x=GLOBAL_LIST): (resolved mutable global)", rule, module(a_list, fn_glob))

    # --- 4. SAFE IMMUTABLE DEFAULTS (MUST NOT FLAG) ---
    r.must_not_flag("def f(x=None): (canonical safe default)", rule,
                    module(py_def(py_params(py_default_param("x", leaf("none", "None"))), block(), "f")))

    r.must_not_flag("def f(x=0): (integer default)", rule,
                    module(py_def(py_params(py_default_param("x", integer("0"))), block(), "f")))

    r.must_not_flag("def f(x='default'): (string default)", rule,
                    module(py_def(py_params(py_default_param("x", leaf("string_literal", "'default'"))), block(), "f")))

    r.must_not_flag("def f(x=()): (tuple literal default)", rule,
                    module(py_def(py_params(py_default_param("x", node("tuple", "()"))), block(), "f")))

    r.must_not_flag("def f(x=tuple()): (tuple constructor call)", rule,
                    module(py_def(py_params(py_default_param("x", call_node("tuple"))), block(), "f")))

    r.must_not_flag("def f(x=frozenset()): (frozenset constructor call)", rule,
                    module(py_def(py_params(py_default_param("x", call_node("frozenset"))), block(), "f")))

    # --- 5. CLASS METHOD WITH MUTABLE DEFAULT (MUST FLAG) ---
    class_method = node("class_definition", "class Handler: def handle(self, opts={}): pass", children=[
        leaf("class", "class"), ident("Handler"), leaf(":", ":"),
        block(py_def(py_params(ident("self"), py_default_param("opts", py_dict())), block(), "handle"))
    ])
    r.must_flag("class Handler: def handle(self, opts={}) (class method with dict default)", rule, module(class_method))

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
