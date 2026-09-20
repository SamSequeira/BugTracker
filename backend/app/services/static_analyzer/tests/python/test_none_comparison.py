"""
PY_NONE_001 — Python Equality Comparison with None Unit & Boundary Tests
========================================================================
Tests for == None and != None anti-patterns vs identity checks (is None / is not None).
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.py_none_comparison import PythonNoneComparison
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, comparison, ident, leaf,
)


def run_tests() -> bool:
    rule = PythonNoneComparison()
    r = RuleTestRunner("PY_NONE_001 — Unit & Boundary Tests")
    none_node = leaf("none", "None")

    # --- 1. EQUALITY WITH NONE (MUST FLAG) ---
    r.must_flag("x == None (equality comparison with None)", rule, module(comparison(ident("x"), "==", none_node)))
    r.must_flag("None == x (reversed equality comparison with None)", rule, module(comparison(none_node, "==", ident("x"))))
    r.must_flag("x != None (inequality comparison with None)", rule, module(comparison(ident("x"), "!=", none_node)))
    r.must_flag("None != x (reversed inequality comparison with None)", rule, module(comparison(none_node, "!=", ident("x"))))

    # --- 2. IDENTITY CHECKS WITH NONE (MUST NOT FLAG) ---
    r.must_not_flag("x is None (idiomatic identity check)", rule, module(comparison(ident("x"), "is", none_node)))
    r.must_not_flag("x is not None (idiomatic negated identity check)", rule, module(comparison(ident("x"), "is not", none_node)))
    r.must_not_flag("x == 0 (equality with non-None)", rule, module(comparison(ident("x"), "==", leaf("integer", "0"))))

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
