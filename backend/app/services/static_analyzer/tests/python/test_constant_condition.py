"""
PY_CONSTCOND_001 — Python Constant Branch/Loop Condition Unit & Boundary Tests
==============================================================================
Tests for invariant constant conditions in if/while constructs (excluding standard idioms).
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.py_constant_condition import PythonConstantCondition
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, block, if_stmt, while_loop, ident, integer, comparison,
    true_lit, false_lit, leaf, node,
)


def run_tests() -> bool:
    rule = PythonConstantCondition()
    r = RuleTestRunner("PY_CONSTCOND_001 — Unit & Boundary Tests")

    # --- 1. CONSTANT IF CONDITIONS (MUST FLAG) ---
    r.must_flag("if True: pass (constant literal True condition)", rule, module(if_stmt(true_lit(), block())))
    r.must_flag("if False: pass (constant literal False condition)", rule, module(if_stmt(false_lit(), block())))
    r.must_flag("if 1 == 1: pass (constant evaluated equality)", rule, module(if_stmt(comparison(integer("1"), "==", integer("1")), block())))
    r.must_flag("while False: pass (while False dead loop)", rule, module(while_loop(false_lit(), block())))

    # --- 2. IDIOMATIC & DYNAMIC CONDITIONS (MUST NOT FLAG) ---
    r.must_not_flag("while True: pass (canonical infinite loop idiom)", rule, module(while_loop(true_lit(), block())))
    name_main = comparison(ident("__name__"), "==", leaf("string_literal", "'__main__'"))
    r.must_not_flag("if __name__ == '__main__': pass (standard entrypoint idiom)", rule, module(if_stmt(name_main, block())))
    type_checking = ident("TYPE_CHECKING")
    r.must_not_flag("if TYPE_CHECKING: pass (standard type checking guard)", rule, module(if_stmt(type_checking, block())))
    r.must_not_flag("if x > 10: pass (dynamic condition)", rule, module(if_stmt(comparison(ident("x"), ">", integer("10")), block())))

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
