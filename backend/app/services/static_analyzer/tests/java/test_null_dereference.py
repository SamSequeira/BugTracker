"""
JAVA_NULL_001 — Java Null Pointer Dereference Unit & Boundary Tests
==================================================================
Tests for explicit null dereference on methods and fields without null guard.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.java_null_dereference import JavaNullDereference
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, block, node, leaf, ident, null_lit, java_binop, parens,
)


def run_tests() -> bool:
    rule = JavaNullDereference()
    r = RuleTestRunner("JAVA_NULL_001 — Unit & Boundary Tests")

    # --- 1. EXPLICIT NULL DEREFERENCE (MUST FLAG) ---
    null_assign = node("local_variable_declaration", "String s = null;", children=[
        ident("String"), node("variable_declarator", "s = null", children=[ident("s"), leaf("=", "="), null_lit()])
    ])
    method_call = node("method_invocation", "s.length()", children=[
        ident("s"), leaf(".", "."), ident("length"), node("argument_list", "()")
    ])
    null_scope = module(block(null_assign, node("expression_statement", "s.length();", children=[method_call])))
    r.must_flag("String s = null; s.length(); (guaranteed null method call)", rule, null_scope, file_path="App.java")

    field_access = node("field_access", "s.value", children=[ident("s"), leaf(".", "."), ident("value")])
    null_field = module(block(null_assign, node("expression_statement", "s.value;", children=[field_access])))
    r.must_flag("String s = null; s.value; (guaranteed null field access)", rule, null_field, file_path="App.java")

    # --- 2. NULL-GUARDED USAGE (MUST NOT FLAG) ---
    guard_cond = parens(java_binop(ident("s"), "!=", null_lit()))
    guarded_block = node("if_statement", "if (s != null) { s.length(); }", children=[
        leaf("if", "if"), guard_cond, block(node("expression_statement", "s.length();", children=[method_call]))
    ])
    safe_scope = module(block(null_assign, guarded_block))
    r.must_not_flag("if (s != null) s.length(); (null guarded dereference)", rule, safe_scope, file_path="App.java")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
