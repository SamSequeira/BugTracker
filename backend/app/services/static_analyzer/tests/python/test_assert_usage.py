"""
PY_ASS_001 — Python Assert in Production Code Unit & Path Tests
================================================================
Tests for assert statements in production code vs test file exclusion.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.py_assert_in_code import PythonAssertInCode
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, ident, integer, comparison, assert_stmt,
)


def run_tests() -> bool:
    rule = PythonAssertInCode()
    r = RuleTestRunner("PY_ASS_001 — Unit & Path Boundary Tests")
    ast = module(assert_stmt(comparison(ident("x"), ">", integer("0"))))

    # --- 1. PRODUCTION FILES (MUST FLAG) ---
    r.must_flag("assert in production file: 'app.py'", rule, ast, "app.py")
    r.must_flag("assert in production file: 'service.py'", rule, ast, "service.py")
    r.must_flag("assert in production file: 'context.py'", rule, ast, "context.py")
    r.must_flag("assert in 'mytest.py' (mid-word test without underscore)", rule, ast, "mytest.py")
    r.must_flag("assert in 'TestHelper.py' (uppercase Test without underscore)", rule, ast, "TestHelper.py")
    r.must_flag("assert in 'test.py' (bare test.py without underscore marker)", rule, ast, "test.py")
    r.must_flag("assert in 'testing.py' (testing without underscore marker)", rule, ast, "testing.py")

    # --- 2. TEST FILES (MUST NOT FLAG / SKIPPED) ---
    r.must_not_flag("assert in test file: 'test_foo.py' (test_ prefix)", rule, ast, "test_foo.py")
    r.must_not_flag("assert in test file: 'foo_test.py' (_test suffix)", rule, ast, "foo_test.py")
    r.must_not_flag("assert in test file: 'spec_foo.py' (spec_ prefix)", rule, ast, "spec_foo.py")
    r.must_not_flag("assert in test file: 'foo_spec.py' (_spec suffix)", rule, ast, "foo_spec.py")
    r.must_not_flag("assert in test file: '/src/test_api.py' (absolute path test_)", rule, ast, "/src/test_api.py")
    r.must_not_flag("assert in test file: 'a/b/c/test_x.py' (nested test_)", rule, ast, "a/b/c/test_x.py")
    r.must_not_flag("assert in test file: 'test__double.py' (double underscore test_)", rule, ast, "test__double.py")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
