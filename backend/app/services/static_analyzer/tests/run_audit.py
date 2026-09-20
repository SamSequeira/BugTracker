"""
run_audit.py — Master test suite runner for the static analyzer.
================================================================
Consolidated execution of all permanent unit, boundary, regression,
and integration test suites across all 24 static analyzer rules.

Run from backend/: python -m app.services.static_analyzer.tests.run_audit
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.resolve()))

# Python rule suites (9 rules)
from app.services.static_analyzer.tests.python.test_division_by_zero import run_tests as test_py_div
from app.services.static_analyzer.tests.python.test_resource_management import run_tests as test_py_res
from app.services.static_analyzer.tests.python.test_exception_handling import run_tests as test_py_exc
from app.services.static_analyzer.tests.python.test_assert_usage import run_tests as test_py_ass
from app.services.static_analyzer.tests.python.test_mutable_defaults import run_tests as test_py_mut
from app.services.static_analyzer.tests.python.test_eval_usage import run_tests as test_py_eval
from app.services.static_analyzer.tests.python.test_none_comparison import run_tests as test_py_none
from app.services.static_analyzer.tests.python.test_unreachable_code import run_tests as test_py_unreach
from app.services.static_analyzer.tests.python.test_constant_condition import run_tests as test_py_constcond

# Java rule suites (8 rules)
from app.services.static_analyzer.tests.java.test_division_by_zero import run_tests as test_java_div
from app.services.static_analyzer.tests.java.test_empty_catch import run_tests as test_java_exc
from app.services.static_analyzer.tests.java.test_string_equality import run_tests as test_java_eq
from app.services.static_analyzer.tests.java.test_resource_management import run_tests as test_java_res
from app.services.static_analyzer.tests.java.test_infinite_loops import run_tests as test_java_loop
from app.services.static_analyzer.tests.java.test_null_dereference import run_tests as test_java_null
from app.services.static_analyzer.tests.java.test_unreachable_code import run_tests as test_java_unreach
from app.services.static_analyzer.tests.java.test_constant_condition import run_tests as test_java_constcond

# JavaScript rule suites (7 rules)
from app.services.static_analyzer.tests.javascript.test_division_by_zero import run_tests as test_js_div
from app.services.static_analyzer.tests.javascript.test_loose_equality import run_tests as test_js_eq
from app.services.static_analyzer.tests.javascript.test_await_in_loop import run_tests as test_js_awa
from app.services.static_analyzer.tests.javascript.test_eval_usage import run_tests as test_js_eval
from app.services.static_analyzer.tests.javascript.test_unhandled_promise import run_tests as test_js_promise
from app.services.static_analyzer.tests.javascript.test_unreachable_code import run_tests as test_js_unreach
from app.services.static_analyzer.tests.javascript.test_constant_condition import run_tests as test_js_constcond

# Regression suites (4 categories)
from app.services.static_analyzer.tests.regression.test_scope_regressions import run_tests as test_reg_scope
from app.services.static_analyzer.tests.regression.test_control_flow_regressions import run_tests as test_reg_ctrl
from app.services.static_analyzer.tests.regression.test_alias_regressions import run_tests as test_reg_alias
from app.services.static_analyzer.tests.regression.test_type_resolution_regressions import run_tests as test_reg_type

# Integration suites (2 categories)
from app.services.static_analyzer.tests.integration.test_cross_language_behavior import run_tests as test_int_cross
from app.services.static_analyzer.tests.integration.test_rule_engine_integration import run_tests as test_int_engine


def main() -> bool:
    print("\n" + "=" * 60)
    print("  STATIC ANALYZER CONSOLIDATED TEST SUITE (24 RULES)")
    print("=" * 60)

    # 1. Python rules (9/9)
    py_results = [
        ("PY_DIV_001", test_py_div()),
        ("PY_RES_001", test_py_res()),
        ("PY_EXC_001", test_py_exc()),
        ("PY_ASS_001", test_py_ass()),
        ("PY_MUT_001", test_py_mut()),
        ("PY_EVAL_001", test_py_eval()),
        ("PY_NONE_001", test_py_none()),
        ("PY_UNREACH_001", test_py_unreach()),
        ("PY_CONSTCOND_001", test_py_constcond()),
    ]
    py_all_ok = all(ok for _, ok in py_results)

    # 2. Java rules (8/8)
    java_results = [
        ("JAVA_DIV_001", test_java_div()),
        ("JAVA_EXC_001", test_java_exc()),
        ("JAVA_EQ_001", test_java_eq()),
        ("JAVA_RES_001", test_java_res()),
        ("JAVA_LOOP_001", test_java_loop()),
        ("JAVA_NULL_001", test_java_null()),
        ("JAVA_UNREACH_001", test_java_unreach()),
        ("JAVA_CONSTCOND_001", test_java_constcond()),
    ]
    java_all_ok = all(ok for _, ok in java_results)

    # 3. JavaScript rules (7/7)
    js_results = [
        ("JS_DIV_001", test_js_div()),
        ("JS_EQ_001", test_js_eq()),
        ("JS_AWA_001", test_js_awa()),
        ("JS_EVAL_001", test_js_eval()),
        ("JS_PROMISE_001", test_js_promise()),
        ("JS_UNREACH_001", test_js_unreach()),
        ("JS_CONSTCOND_001", test_js_constcond()),
    ]
    js_all_ok = all(ok for _, ok in js_results)

    # 4. Regressions
    reg_scope_ok = test_reg_scope()
    reg_ctrl_ok = test_reg_ctrl()
    reg_alias_ok = test_reg_alias()
    reg_type_ok = test_reg_type()
    reg_all_ok = reg_scope_ok and reg_ctrl_ok and reg_alias_ok and reg_type_ok

    # 5. Integration
    int_cross_ok = test_int_cross()
    int_engine_ok = test_int_engine()
    int_all_ok = int_cross_ok and int_engine_ok

    print("\n" + "=" * 60)
    print("  CONSOLIDATED SUITE EXECUTION SUMMARY")
    print("=" * 60)
    print(f"  Python Rules Suite (9 rules)       : {'PASS' if py_all_ok   else 'FAIL'}")
    print(f"  Java Rules Suite (8 rules)         : {'PASS' if java_all_ok else 'FAIL'}")
    print(f"  JavaScript Rules Suite (7 rules)   : {'PASS' if js_all_ok   else 'FAIL'}")
    print(f"  Regression Suite (4 categories)    : {'PASS' if reg_all_ok  else 'FAIL'}")
    print(f"  Integration Suite (2 categories)   : {'PASS' if int_all_ok  else 'FAIL'}")

    overall = py_all_ok and java_all_ok and js_all_ok and reg_all_ok and int_all_ok
    print(f"\n  Overall Status: {'PASS' if overall else 'FAIL'}")
    return overall


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
