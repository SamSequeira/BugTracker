"""
run_audit.py — Master test suite runner for the static analyzer.
================================================================
Consolidated execution of all permanent unit, boundary, regression,
and integration test suites.

Run from backend/: python -m app.services.static_analyzer.tests.run_audit
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.resolve()))

# Python rule suites
from app.services.static_analyzer.tests.python.test_division_by_zero import run_tests as test_py_div
from app.services.static_analyzer.tests.python.test_resource_management import run_tests as test_py_res
from app.services.static_analyzer.tests.python.test_exception_handling import run_tests as test_py_exc
from app.services.static_analyzer.tests.python.test_assert_usage import run_tests as test_py_ass
from app.services.static_analyzer.tests.python.test_mutable_defaults import run_tests as test_py_mut

# Java rule suites
from app.services.static_analyzer.tests.java.test_division_by_zero import run_tests as test_java_div
from app.services.static_analyzer.tests.java.test_empty_catch import run_tests as test_java_exc
from app.services.static_analyzer.tests.java.test_string_equality import run_tests as test_java_eq
from app.services.static_analyzer.tests.java.test_resource_management import run_tests as test_java_res
from app.services.static_analyzer.tests.java.test_infinite_loops import run_tests as test_java_loop

# JavaScript rule suites
from app.services.static_analyzer.tests.javascript.test_division_by_zero import run_tests as test_js_div
from app.services.static_analyzer.tests.javascript.test_loose_equality import run_tests as test_js_eq
from app.services.static_analyzer.tests.javascript.test_await_in_loop import run_tests as test_js_awa

# Regression suites
from app.services.static_analyzer.tests.regression.test_scope_regressions import run_tests as test_reg_scope
from app.services.static_analyzer.tests.regression.test_control_flow_regressions import run_tests as test_reg_ctrl
from app.services.static_analyzer.tests.regression.test_alias_regressions import run_tests as test_reg_alias
from app.services.static_analyzer.tests.regression.test_type_resolution_regressions import run_tests as test_reg_type

# Integration suites
from app.services.static_analyzer.tests.integration.test_cross_language_behavior import run_tests as test_int_cross
from app.services.static_analyzer.tests.integration.test_rule_engine_integration import run_tests as test_int_engine


def main() -> bool:
    print("\n" + "=" * 60)
    print("  STATIC ANALYZER CONSOLIDATED TEST SUITE")
    print("=" * 60)

    # 1. Python rules
    py_div_ok = test_py_div()
    py_res_ok = test_py_res()
    py_exc_ok = test_py_exc()
    py_ass_ok = test_py_ass()
    py_mut_ok = test_py_mut()
    py_all_ok = py_div_ok and py_res_ok and py_exc_ok and py_ass_ok and py_mut_ok

    # 2. Java rules
    java_div_ok = test_java_div()
    java_exc_ok = test_java_exc()
    java_eq_ok = test_java_eq()
    java_res_ok = test_java_res()
    java_loop_ok = test_java_loop()
    java_all_ok = java_div_ok and java_exc_ok and java_eq_ok and java_res_ok and java_loop_ok

    # 3. JavaScript rules
    js_div_ok = test_js_div()
    js_eq_ok = test_js_eq()
    js_awa_ok = test_js_awa()
    js_all_ok = js_div_ok and js_eq_ok and js_awa_ok

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
    print(f"  Python Rules Suite (5 rules)       : {'PASS' if py_all_ok   else 'FAIL'}")
    print(f"  Java Rules Suite (5 rules)         : {'PASS' if java_all_ok else 'FAIL'}")
    print(f"  JavaScript Rules Suite (3 rules)   : {'PASS' if js_all_ok   else 'FAIL'}")
    print(f"  Regression Suite (4 categories)    : {'PASS' if reg_all_ok  else 'FAIL'}")
    print(f"  Integration Suite (2 categories)   : {'PASS' if int_all_ok  else 'FAIL'}")

    overall = py_all_ok and java_all_ok and js_all_ok and reg_all_ok and int_all_ok
    print(f"\n  Overall Status: {'PASS' if overall else 'FAIL'}")
    return overall


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
