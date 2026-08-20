"""
JAVA_RES_001 — Java Resource Management Unit & Boundary Tests
==============================================================
Tests for unclosed AutoCloseable resources instantiated outside try-with-resources.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.java_unclosed_resource import JavaUnclosedResource
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, block, node, leaf, ident,
    java_object_creation, try_with_resources,
)


def run_tests() -> bool:
    rule = JavaUnclosedResource()
    r = RuleTestRunner("JAVA_RES_001 — Unit & Boundary Tests")

    # --- 1. UNCLOSED RESOURCE INSTANTIATIONS (MUST FLAG) ---
    r.must_flag("new FileReader() outside TWR", rule, module(java_object_creation("FileReader")), "T.java")
    r.must_flag("new FileWriter() outside TWR", rule, module(java_object_creation("FileWriter")), "T.java")
    r.must_flag("new FileInputStream() outside TWR", rule, module(java_object_creation("FileInputStream")), "T.java")
    r.must_flag("new FileOutputStream() outside TWR", rule, module(java_object_creation("FileOutputStream")), "T.java")
    r.must_flag("new Connection() outside TWR", rule, module(java_object_creation("Connection")), "T.java")
    scoped_file_reader = node("object_creation_expression", "new java.io.FileReader()", children=[
        leaf("new", "new"),
        node("scoped_type_identifier", "java.io.FileReader", children=[ident("java"), leaf(".", "."), ident("io"), ident("FileReader")]),
        leaf("(", "("), leaf(")", ")")
    ])
    r.must_flag("scoped type: new java.io.FileReader()", rule, module(scoped_file_reader), "T.java")

    # In conditional / catch block without try-with-resources
    if_resource = node("if_statement", "if(c){new FileReader();}", children=[
        leaf("if", "if"), ident("c"), block(java_object_creation("FileReader"))
    ])
    r.must_flag("new FileReader() inside if block", rule, module(if_resource), "T.java")

    # --- 2. SAFE TRY-WITH-RESOURCES & NON-RESOURCES (MUST NOT FLAG) ---
    r.must_not_flag("BufferedReader inside try-with-resources", rule, module(try_with_resources(java_object_creation("BufferedReader"))), "T.java")
    r.must_not_flag("new StringBuilder() (not a resource)", rule, module(java_object_creation("StringBuilder")), "T.java")
    r.must_not_flag("new Thread() (not a resource)", rule, module(java_object_creation("Thread")), "T.java")
    r.must_not_flag("new ArrayList() (not a resource)", rule, module(java_object_creation("ArrayList")), "T.java")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
