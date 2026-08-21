"""
JAVA_EQ_001 — Java String & Reference Equality Unit & Boundary Tests
=====================================================================
Tests for == and != comparisons on Strings, name hints, declared types,
and primitive/enum/null boundaries.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.java_string_equality import JavaStringEquality
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, node, leaf, ident, java_binop, java_decimal_int, java_call,
)


def run_tests() -> bool:
    rule = JavaStringEquality()
    r = RuleTestRunner("JAVA_EQ_001 — Unit & Boundary Tests")

    # --- 1. STRING HINT NAMES (MUST FLAG) ---
    for name in ("str", "name", "text", "msg", "message", "label", "key",
                 "value", "path", "url", "uri", "email", "token", "id",
                 "code", "description", "title", "content", "firstName",
                 "lastName", "inputText", "fileContent", "storedToken",
                 "emailAddress", "urlString", "orderId", "otherId"):
        r.must_flag(f"hint variable: {name} == other", rule, module(java_binop(ident(name), "==", ident("other"))), "T.java")

    r.must_flag("reversed hint: other == str", rule, module(java_binop(ident("other"), "==", ident("str"))), "T.java")
    r.must_flag("inequality operator: str != other", rule, module(java_binop(ident("str"), "!=", ident("other"))), "T.java")
    r.must_flag("method invocation: obj.getName() == str", rule, module(java_binop(java_call("obj.getName"), "==", ident("str"))), "T.java")
    r.must_flag("string literal: str == \"literal\"", rule, module(java_binop(ident("str"), "==", leaf("string_literal", "\"literal\""))), "T.java")

    # --- 2. DECLARED STRING VARIABLES (W04 / FN-3 REGRESSIONS) ---
    for arbitrary_name in ("data", "result", "input", "output", "response", "request", "payload", "body", "raw", "line", "word"):
        decl = node("local_variable_declaration", f"String {arbitrary_name};", children=[
            node("type_identifier", "String"),
            node("variable_declarator", arbitrary_name, children=[ident(arbitrary_name)])
        ])
        cmp_stmt = java_binop(ident(arbitrary_name), "==", ident("other"))
        r.must_flag(f"declared String: String {arbitrary_name}; {arbitrary_name} == other", rule, module(decl, cmp_stmt), "T.java")

    # --- 3. BOUNDARIES: NULL, ENUMS, PRIMITIVES, ARRAYS, GENERICS (MUST NOT FLAG) ---
    r.must_not_flag("null check: str == null", rule, module(java_binop(ident("str"), "==", leaf("null_literal", "null"))), "T.java")
    r.must_not_flag("null check reversed: null != str", rule, module(java_binop(leaf("null_literal", "null"), "!=", ident("str"))), "T.java")
    r.must_not_flag("enum comparison: STATUS == ACTIVE", rule, module(java_binop(ident("STATUS"), "==", ident("ACTIVE"))), "T.java")
    r.must_not_flag("primitive literal: str == 42", rule, module(java_binop(ident("str"), "==", java_decimal_int("42"))), "T.java")
    r.must_not_flag("character literals: 'a' == 'b'", rule, module(java_binop(leaf("character_literal", "'a'"), "==", leaf("character_literal", "'b'"))), "T.java")
    r.must_not_flag("primitive variable names: i == j", rule, module(java_binop(ident("i"), "==", ident("j"))), "T.java")
    r.must_not_flag("primitive variable names: count == limit", rule, module(java_binop(ident("count"), "==", ident("limit"))), "T.java")
    r.must_not_flag("primitive variable names: age == maxAge", rule, module(java_binop(ident("age"), "==", ident("maxAge"))), "T.java")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
