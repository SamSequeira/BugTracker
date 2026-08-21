"""
Integration Suite: Rule Engine State Isolation, Robustness & Benchmarks
========================================================================
Tests rule instance state isolation, multi-run determinism, malformed AST
robustness, and performance benchmarks.
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.py_division_by_zero import PythonDivisionByZero
from app.services.static_analyzer.rules.py_mutable_default_arg import PythonMutableDefaultArg
from app.services.static_analyzer.rules.java_string_equality import JavaStringEquality
from app.services.static_analyzer.rules.java_infinite_loop import JavaInfiniteLoop
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, ident, integer, binop_node, java_binop, node,
)


def _issues(rule, ast, path="f.py"):
    return list(rule.analyze(ast, path, []))


def _n(rule, ast, path="f.py"):
    return len(_issues(rule, ast, path))


def run_tests() -> bool:
    r = RuleTestRunner("Integration — Engine State, Robustness & Performance")
    rules = [PythonDivisionByZero(), PythonMutableDefaultArg(), JavaStringEquality(), JavaInfiniteLoop()]

    # --- 1. MALFORMED AST SURVIVAL & ROBUSTNESS ---
    empty_ast = node("module", "", 0, children=[])
    malformed_ast = node("module", "", 0, children=[node("corrupt", None, 0)])

    for rule in rules:
        try:
            _issues(rule, empty_ast, "f.py")
            _issues(rule, malformed_ast, "f.py")
            r._passes += 1
            print(f"  OK   [robustness    ] {rule.rule_id} survived empty and malformed ASTs")
        except Exception as exc:
            r._failures.append(f"  FAIL [robustness    ] {rule.rule_id} crashed on malformed AST: {exc}")

    # --- 2. STATE ISOLATION ACROSS RUNS (SAFE -> UNSAFE -> SAFE) ---
    py_div = PythonDivisionByZero()
    x = ident("x")
    safe_ast = module(binop_node(x, "/", integer("1", 1), 1))
    unsafe_ast = module(binop_node(x, "/", integer("0", 1), 1))

    n_safe1 = _n(py_div, safe_ast)
    n_unsafe = _n(py_div, unsafe_ast)
    n_safe2 = _n(py_div, safe_ast)

    if n_safe1 == 0 and n_unsafe == 1 and n_safe2 == 0:
        r._passes += 1
        print("  OK   [state-isolation] verified across safe -> unsafe -> safe sequence")
    else:
        r._failures.append(f"  FAIL [state-isolation] state contaminated: {n_safe1}, {n_unsafe}, {n_safe2}")

    # --- 3. DETERMINISM OVER REPEATED RUNS ---
    jv_eq = JavaStringEquality()
    decl = node("local_variable_declaration", "String data;", 1, children=[
        node("type_identifier", "String", 1),
        node("variable_declarator", "data", 1, children=[ident("data", 1)])
    ])
    test_ast = module(decl, java_binop(ident("data", 2), "==", ident("other", 2), 2))
    counts = [_n(jv_eq, test_ast, "T.java") for _ in range(10)]
    if all(c == 1 for c in counts):
        r._passes += 1
        print("  OK   [determinism   ] 10 repeated runs produced identical results (10/10)")
    else:
        r._failures.append(f"  FAIL [determinism   ] nondeterministic counts: {counts}")

    # --- 4. PERFORMANCE BENCHMARKS (1,000 NODE PAYLOADS < 1.0s) ---
    stmts = []
    for i in range(1000):
        stmts.append(node("assignment", f"d{i} = 1", i, children=[ident(f"d{i}", i), node("=", "="), integer("1", i)]))
        stmts.append(binop_node(x, "/", ident(f"d{i}", i), i))
    big_py_ast = module(*stmts)

    t0 = time.time()
    _issues(py_div, big_py_ast, "f.py")
    elapsed_py = time.time() - t0

    if elapsed_py < 1.0:
        r._passes += 1
        print(f"  OK   [performance   ] PY_DIV_001 (1,000 nodes): {elapsed_py:.4f}s (< 1.0s)")
    else:
        r._failures.append(f"  FAIL [performance   ] PY_DIV_001 took {elapsed_py:.4f}s")

    java_stmts = []
    for i in range(1000):
        java_stmts.append(node("local_variable_declaration", f"String s{i};", i, children=[
            node("type_identifier", "String", i),
            node("variable_declarator", f"s{i}", i, children=[ident(f"s{i}", i)])
        ]))
        java_stmts.append(java_binop(ident(f"s{i}", i), "==", ident("other", i), i))
    big_java_ast = module(*java_stmts)

    t0 = time.time()
    _issues(jv_eq, big_java_ast, "T.java")
    elapsed_java = time.time() - t0

    if elapsed_java < 1.0:
        r._passes += 1
        print(f"  OK   [performance   ] JAVA_EQ_001 (1,000 nodes): {elapsed_java:.4f}s (< 1.0s)")
    else:
        r._failures.append(f"  FAIL [performance   ] JAVA_EQ_001 took {elapsed_java:.4f}s")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
