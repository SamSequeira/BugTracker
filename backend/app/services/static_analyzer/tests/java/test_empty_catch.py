"""
JAVA_EXC_001 — Java Empty Catch Block Unit & Boundary Tests
============================================================
Tests for completely empty catch blocks and comment suppression heuristics.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.java_empty_catch import JavaEmptyCatch
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, node, leaf, ident, java_catch_clause, call_node,
)


def run_tests() -> bool:
    rule = JavaEmptyCatch()
    r = RuleTestRunner("JAVA_EXC_001 — Unit & Boundary Tests")

    # --- 1. EMPTY CATCH BLOCKS (MUST FLAG) ---
    r.must_flag("empty catch: catch (Exception e) {}", rule, module(java_catch_clause()), "T.java")

    # Multiple empty statements: catch (Exception e) { ; ; ; }
    empty_stmts_catch = node("catch_clause", "catch (Exception e) { ;;; }", children=[
        node("catch_formal_parameter", "Exception e"),
        node("block", "{;;;}", children=[
            leaf("empty_statement", ";"), leaf("empty_statement", ";"), leaf("empty_statement", ";")
        ]),
    ])
    r.must_flag("catch with multiple empty_statements: catch(e){;;;}", rule, module(empty_stmts_catch), "T.java")

    # --- 2. NON-EMPTY CATCH BLOCKS (MUST NOT FLAG) ---
    non_empty_stmt = node("expression_statement", "log.error(e);", children=[call_node("log.error", ident("e"))])
    handled_catch = java_catch_clause("Exception e", non_empty_stmt)
    r.must_not_flag("non-empty catch: catch (Exception e) { log.error(e); }", rule, module(handled_catch), "T.java")

    rethrow_stmt = node("throw_statement", "throw e;", children=[leaf("throw", "throw"), ident("e"), leaf(";", ";")])
    rethrow_catch = java_catch_clause("Exception e", rethrow_stmt)
    r.must_not_flag("rethrowing catch: catch (Exception e) { throw e; }", rule, module(rethrow_catch), "T.java")

    # --- 3. INTENTIONAL COMMENT-ONLY CATCH (MUST NOT FLAG: INTENTIONAL SUPPRESSION) ---
    comment_catch = node("catch_clause", "catch (Exception e) { /* ignored: intentional fallback */ }", children=[
        node("catch_formal_parameter", "Exception e"),
        node("block", "/* ignored: intentional fallback */", children=[leaf("comment", "/* ignored: intentional fallback */")]),
    ])
    r.must_not_flag("intentional comment catch: catch (e) { /* ignored: intentional fallback */ }", rule, module(comment_catch), "T.java")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
"""
JAVA_EXC_001 — Java Empty Catch Block Unit & Boundary Tests
============================================================
Tests for completely empty catch blocks and comment suppression heuristics.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.java_empty_catch import JavaEmptyCatch
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, node, leaf, ident, java_catch_clause, call_node,
)


def run_tests() -> bool:
    rule = JavaEmptyCatch()
    r = RuleTestRunner("JAVA_EXC_001 — Unit & Boundary Tests")

    # --- 1. EMPTY CATCH BLOCKS (MUST FLAG) ---
    r.must_flag("empty catch: catch (Exception e) {}", rule, module(java_catch_clause()), "T.java")

    # Multiple empty statements: catch (Exception e) { ; ; ; }
    empty_stmts_catch = node("catch_clause", "catch (Exception e) { ;;; }", children=[
        node("catch_formal_parameter", "Exception e"),
        node("block", "{;;;}", children=[
            leaf("empty_statement", ";"), leaf("empty_statement", ";"), leaf("empty_statement", ";")
        ]),
    ])
    r.must_flag("catch with multiple empty_statements: catch(e){;;;}", rule, module(empty_stmts_catch), "T.java")

    # --- 2. NON-EMPTY CATCH BLOCKS (MUST NOT FLAG) ---
    non_empty_stmt = node("expression_statement", "log.error(e);", children=[call_node("log.error", ident("e"))])
    handled_catch = java_catch_clause("Exception e", non_empty_stmt)
    r.must_not_flag("non-empty catch: catch (Exception e) { log.error(e); }", rule, module(handled_catch), "T.java")

    rethrow_stmt = node("throw_statement", "throw e;", children=[leaf("throw", "throw"), ident("e"), leaf(";", ";")])
    rethrow_catch = java_catch_clause("Exception e", rethrow_stmt)
    r.must_not_flag("rethrowing catch: catch (Exception e) { throw e; }", rule, module(rethrow_catch), "T.java")

    # --- 3. COMMENT-ONLY CATCH (MUST FLAG: COMMENTS PROVIDE NO RUNTIME ACTION) ---
    comment_catch = node("catch_clause", "catch (Exception e) { /* ignored */ }", children=[
        node("catch_formal_parameter", "Exception e"),
        node("block", "/* ignored */", children=[leaf("comment", "/* ignored: intentional fallback */")]),
    ])
    r.must_flag("comment-only catch: catch (e) { /* ignored */ } (flagged: comments do not handle exception)", rule, module(comment_catch), "T.java")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
