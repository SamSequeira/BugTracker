"""
PY_RES_001 — Python Resource Management Unit & Boundary Tests
==============================================================
Tests for open() calls outside context managers (with statements).
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.py_unclosed_resource import PythonUnclosedResource
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, block, node, leaf, ident, open_call, with_stmt, call_node,
)


def run_tests() -> bool:
    rule = PythonUnclosedResource()
    r = RuleTestRunner("PY_RES_001 — Unit & Boundary Tests")

    # --- 1. UNCLOSED RESOURCE CALLS (MUST FLAG) ---
    for var in ("f", "fh", "handle", "fp", "file", "infile"):
        r.must_flag(
            f"open() assigned to variable '{var}' outside with",
            rule,
            module(node("assignment", f"{var} = open('x')", children=[ident(var), leaf("=", "="), open_call()])),
        )

    r.must_flag(
        "open('f', 'r') with mode argument outside with",
        rule,
        module(open_call(leaf("string_literal", "'f'"), leaf("string_literal", "'r'"))),
    )

    r.must_flag(
        "read(open('f')) result passed directly to call",
        rule,
        module(call_node("read", open_call())),
    )

    try_node = node("try_statement", "try: open()", children=[
        leaf("try", "try"),
        block(open_call()),
    ])
    r.must_flag("open() inside try block but not in with", rule, module(try_node))

    # --- 2. SAFE CONTEXT MANAGERS & ATTRIBUTES (MUST NOT FLAG) ---
    r.must_not_flag("with open('f') as f: (standard with)", rule, module(with_stmt(open_call())))

    inner_with = with_stmt(open_call())
    outer_with = with_stmt(inner_with)
    r.must_not_flag("open() inside doubly-nested with", rule, module(outer_with))

    # Negative space: method call named 'open' (e.g. obj.open() or Path.open())
    r.must_not_flag(
        "obj.open() — attribute method call, not builtin open",
        rule,
        module(node("call", "obj.open()", children=[
            node("attribute", "obj.open", children=[ident("obj"), leaf(".", "."), ident("open")]),
            leaf("argument_list", "()"),
        ])),
    )

    r.must_not_flag(
        "Path.open() — attribute call on Path object",
        rule,
        module(node("call", "Path('f').open()", children=[
            node("attribute", "Path('f').open", children=[call_node("Path", leaf("string_literal", "'f'")), leaf(".", "."), ident("open")]),
            leaf("argument_list", "()"),
        ])),
    )

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
