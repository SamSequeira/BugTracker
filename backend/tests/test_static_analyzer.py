"""
test_static_analyzer.py
-----------------------
Tests for the static analysis engine and every individual rule.

Run from backend/:
    python tests/test_static_analyzer.py
    python -m pytest tests/test_static_analyzer.py -v
"""

import sys
import json
import textwrap
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ast_generator import ASTGenerator
from app.services.static_analyzer import StaticAnalyzer, CandidateIssue
from app.services.static_analyzer.rules import ALL_RULES

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

gen = ASTGenerator()
analyzer = StaticAnalyzer()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ast(source: str, language: str) -> dict:
    """Parse source string into a normalized AST dict."""
    suffix = {"Python": ".py", "JavaScript": ".js", "Java": ".java"}[language]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    ) as f:
        f.write(source)
        path = f.name
    result = gen.generate_ast(path, language)
    Path(path).unlink(missing_ok=True)
    assert result["success"], f"AST generation failed: {result}"
    return result


def _issues(source: str, language: str) -> list:
    """Parse source and run the full analyzer. Returns list of issue dicts."""
    result = _ast(source, language)
    analysis = analyzer.analyze(
        ast=result["ast"],
        language=language,
        file_path=result["file"],
        source_code=source,
    )
    return analysis["issues"]


def _rule_ids(source: str, language: str) -> list:
    return [i["rule_id"] for i in _issues(source, language)]


def save(data: dict, filename: str) -> Path:
    out = OUTPUT_DIR / filename
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return out


# ===========================================================================
# PY_DIV_001 — Division by potentially zero value (Python)
# ===========================================================================

def test_py_div_variable_divisor_flagged():
    src = "def f(a):\n    b = 0\n    return a / b\n"
    ids = _rule_ids(src, "Python")
    assert "PY_DIV_001" in ids, f"Expected PY_DIV_001 in {ids}"
    print("  ✓ PY_DIV_001: variable assigned zero divisor flagged")


def test_py_div_unknown_divisor_not_flagged():
    src = "def f(a, b):\n    return a / b\n"
    ids = _rule_ids(src, "Python")
    assert "PY_DIV_001" not in ids, "Unknown divisor should not be flagged"
    print("  ✓ PY_DIV_001: unknown divisor not flagged")


def test_py_div_literal_divisor_not_flagged():
    src = "def f(a):\n    return a / 2\n"
    ids = _rule_ids(src, "Python")
    assert "PY_DIV_001" not in ids, "Literal divisor should not be flagged"
    print("  ✓ PY_DIV_001: literal divisor not flagged")


def test_py_div_floor_division_flagged():
    src = "def f(a):\n    b = 0\n    return a // b\n"
    ids = _rule_ids(src, "Python")
    assert "PY_DIV_001" in ids
    print("  ✓ PY_DIV_001: floor division by zero flagged")


# ===========================================================================
# PY_RES_001 — open() outside with-statement (Python)
# ===========================================================================

def test_py_res_bare_open_flagged():
    src = textwrap.dedent("""\
        def read(path):
            f = open(path, "r")
            return f.read()
    """)
    ids = _rule_ids(src, "Python")
    assert "PY_RES_001" in ids, f"Expected PY_RES_001 in {ids}"
    print("  ✓ PY_RES_001: bare open() flagged")


def test_py_res_with_open_not_flagged():
    src = textwrap.dedent("""\
        def read(path):
            with open(path, "r") as f:
                return f.read()
    """)
    ids = _rule_ids(src, "Python")
    assert "PY_RES_001" not in ids, "open() inside with should not be flagged"
    print("  ✓ PY_RES_001: open() inside with not flagged")


# ===========================================================================
# PY_EXC_001 — Bare except clause (Python)
# ===========================================================================

def test_py_exc_bare_except_flagged():
    src = textwrap.dedent("""\
        try:
            x = int("abc")
        except:
            pass
    """)
    ids = _rule_ids(src, "Python")
    assert "PY_EXC_001" in ids, f"Expected PY_EXC_001 in {ids}"
    print("  ✓ PY_EXC_001: bare except flagged")


def test_py_exc_typed_except_not_flagged():
    src = textwrap.dedent("""\
        try:
            x = int("abc")
        except ValueError:
            pass
    """)
    ids = _rule_ids(src, "Python")
    assert "PY_EXC_001" not in ids, "Typed except should not be flagged"
    print("  ✓ PY_EXC_001: typed except not flagged")


# ===========================================================================
# PY_ASS_001 — assert in production code (Python)
# ===========================================================================

def test_py_assert_production_flagged():
    src = textwrap.dedent("""\
        def process(data):
            assert data is not None
            return data
    """)
    issues = _issues(src, "Python")
    ids = [i["rule_id"] for i in issues]
    assert "PY_ASS_001" in ids, f"Expected PY_ASS_001 in {ids}"
    print("  ✓ PY_ASS_001: assert in production code flagged")


def test_py_assert_test_file_skipped():
    src = textwrap.dedent("""\
        def test_something():
            assert 1 + 1 == 2
    """)
    result = _ast(src, "Python")
    # Simulate a test file path
    analysis = analyzer.analyze(
        ast=result["ast"],
        language="Python",
        file_path="/project/tests/test_utils.py",
        source_code=src,
    )
    ids = [i["rule_id"] for i in analysis["issues"]]
    assert "PY_ASS_001" not in ids, "assert in test file should be skipped"
    print("  ✓ PY_ASS_001: assert in test file not flagged")


# ===========================================================================
# PY_MUT_001 — Mutable default argument (Python)
# ===========================================================================

def test_py_mut_list_default_flagged():
    src = textwrap.dedent("""\
        def append_to(element, to=[]):
            to.append(element)
            return to
    """)
    ids = _rule_ids(src, "Python")
    assert "PY_MUT_001" in ids, f"Expected PY_MUT_001 in {ids}"
    print("  ✓ PY_MUT_001: list default flagged")


def test_py_mut_dict_default_flagged():
    src = textwrap.dedent("""\
        def update(key, val, store={}):
            store[key] = val
            return store
    """)
    ids = _rule_ids(src, "Python")
    assert "PY_MUT_001" in ids
    print("  ✓ PY_MUT_001: dict default flagged")


def test_py_mut_none_default_not_flagged():
    src = textwrap.dedent("""\
        def append_to(element, to=None):
            if to is None:
                to = []
            to.append(element)
            return to
    """)
    ids = _rule_ids(src, "Python")
    assert "PY_MUT_001" not in ids, "None default should not be flagged"
    print("  ✓ PY_MUT_001: None default not flagged")


# ===========================================================================
# JS_DIV_001 — Division by potentially zero value (JavaScript)
# ===========================================================================

def test_js_div_variable_divisor_flagged():
    src = textwrap.dedent("""\
        function f(a) {
            let b = 0;
            return a / b;
        }
    """)
    ids = _rule_ids(src, "JavaScript")
    assert "JS_DIV_001" in ids, f"Expected JS_DIV_001 in {ids}"
    print("  ✓ JS_DIV_001: variable assigned zero divisor flagged")


def test_js_div_literal_divisor_not_flagged():
    src = textwrap.dedent("""\
        function f(a) {
            return a / 2;
        }
    """)
    ids = _rule_ids(src, "JavaScript")
    assert "JS_DIV_001" not in ids, "Literal divisor should not be flagged"
    print("  ✓ JS_DIV_001: literal divisor not flagged")


def test_js_div_modulo_variable_flagged():
    src = textwrap.dedent("""\
        function f(a) {
            let n = 0;
            return a % n;
        }
    """)
    ids = _rule_ids(src, "JavaScript")
    assert "JS_DIV_001" in ids
    print("  ✓ JS_DIV_001: modulo by variable assigned zero flagged")


# ===========================================================================
# JS_EQ_001 — Loose equality (JavaScript)
# ===========================================================================

def test_js_eq_double_equals_flagged():
    src = textwrap.dedent("""\
        function check(a, b) {
            return a == b;
        }
    """)
    ids = _rule_ids(src, "JavaScript")
    assert "JS_EQ_001" in ids, f"Expected JS_EQ_001 in {ids}"
    print("  ✓ JS_EQ_001: == flagged")


def test_js_eq_not_equals_flagged():
    src = textwrap.dedent("""\
        function check(a, b) {
            return a != b;
        }
    """)
    ids = _rule_ids(src, "JavaScript")
    assert "JS_EQ_001" in ids
    print("  ✓ JS_EQ_001: != flagged")


def test_js_eq_triple_equals_not_flagged():
    src = textwrap.dedent("""\
        function check(a, b) {
            return a === b;
        }
    """)
    ids = _rule_ids(src, "JavaScript")
    assert "JS_EQ_001" not in ids, "=== should not be flagged"
    print("  ✓ JS_EQ_001: === not flagged")


# ===========================================================================
# JS_AWA_001 — await inside loop (JavaScript)
# ===========================================================================

def test_js_await_in_for_loop_flagged():
    src = textwrap.dedent("""\
        async function f(items) {
            for (let i = 0; i < items.length; i++) {
                const result = await fetchItem(items[i]);
                console.log(result);
            }
        }
    """)
    ids = _rule_ids(src, "JavaScript")
    assert "JS_AWA_001" in ids, f"Expected JS_AWA_001 in {ids}"
    print("  ✓ JS_AWA_001: await in for loop flagged")


def test_js_await_in_while_loop_flagged():
    src = textwrap.dedent("""\
        async function f(queue) {
            while (queue.length > 0) {
                await process(queue.pop());
            }
        }
    """)
    ids = _rule_ids(src, "JavaScript")
    assert "JS_AWA_001" in ids
    print("  ✓ JS_AWA_001: await in while loop flagged")


def test_js_await_outside_loop_not_flagged():
    src = textwrap.dedent("""\
        async function f(item) {
            const result = await fetchItem(item);
            return result;
        }
    """)
    ids = _rule_ids(src, "JavaScript")
    assert "JS_AWA_001" not in ids, "await outside loop should not be flagged"
    print("  ✓ JS_AWA_001: await outside loop not flagged")


# ===========================================================================
# JAVA_DIV_001 — Division by potentially zero value (Java)
# ===========================================================================

def test_java_div_variable_divisor_flagged():
    src = "public class T { int f(int a) { int b = 0; return a / b; } }"
    ids = _rule_ids(src, "Java")
    assert "JAVA_DIV_001" in ids, f"Expected JAVA_DIV_001 in {ids}"
    print("  ✓ JAVA_DIV_001: variable assigned zero divisor flagged")


def test_java_div_literal_divisor_not_flagged():
    src = "public class T { int f(int a) { return a / 2; } }"
    ids = _rule_ids(src, "Java")
    assert "JAVA_DIV_001" not in ids, "Literal divisor should not be flagged"
    print("  ✓ JAVA_DIV_001: literal divisor not flagged")


def test_java_div_modulo_variable_flagged():
    src = "public class T { int f(int a) { int n = 0; return a % n; } }"
    ids = _rule_ids(src, "Java")
    assert "JAVA_DIV_001" in ids
    print("  ✓ JAVA_DIV_001: modulo by variable assigned zero flagged")


# ===========================================================================
# JAVA_EXC_001 — Empty catch block (Java)
# ===========================================================================

def test_java_empty_catch_flagged():
    src = textwrap.dedent("""\
        public class T {
            void f() {
                try { int x = 1; } catch (Exception e) {}
            }
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_EXC_001" in ids, f"Expected JAVA_EXC_001 in {ids}"
    print("  ✓ JAVA_EXC_001: empty catch flagged")


def test_java_catch_with_log_not_flagged():
    src = textwrap.dedent("""\
        public class T {
            void f() {
                try { int x = 1; }
                catch (Exception e) { System.err.println(e.getMessage()); }
            }
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_EXC_001" not in ids, "Non-empty catch should not be flagged"
    print("  ✓ JAVA_EXC_001: catch with statement not flagged")


# ===========================================================================
# JAVA_EQ_001 — String reference equality (Java)
# ===========================================================================

def test_java_string_eq_flagged():
    # Use uppercase-starting variable names — Java convention for object references
    src = textwrap.dedent("""\
        public class T {
            boolean f(String Name, String Other) { return Name == Other; }
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_EQ_001" in ids, f"Expected JAVA_EQ_001 in {ids}"
    print("  ✓ JAVA_EQ_001: String == flagged")


def test_java_null_check_not_flagged():
    src = textwrap.dedent("""\
        public class T {
            boolean f(String s) { return s == null; }
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_EQ_001" not in ids, "null check should not be flagged"
    print("  ✓ JAVA_EQ_001: null check not flagged")


def test_java_primitive_eq_not_flagged():
    src = textwrap.dedent("""\
        public class T {
            boolean f(int a, int b) { return a == b; }
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_EQ_001" not in ids, "primitive == should not be flagged"
    print("  ✓ JAVA_EQ_001: primitive == not flagged")


# ===========================================================================
# JAVA_RES_001 — Unclosed resource (Java)
# ===========================================================================

def test_java_unclosed_filereader_flagged():
    src = textwrap.dedent("""\
        public class T {
            void f(String p) throws Exception {
                java.io.FileReader r = new java.io.FileReader(p);
                r.read();
            }
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_RES_001" in ids, f"Expected JAVA_RES_001 in {ids}"
    print("  ✓ JAVA_RES_001: FileReader outside try-with-resources flagged")


def test_java_try_with_resources_not_flagged():
    src = textwrap.dedent("""\
        public class T {
            void f(String p) throws Exception {
                try (java.io.FileReader r = new java.io.FileReader(p)) {
                    r.read();
                }
            }
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_RES_001" not in ids, "try-with-resources should not be flagged"
    print("  ✓ JAVA_RES_001: try-with-resources not flagged")


# ===========================================================================
# JAVA_LOOP_001 — while(true) without exit (Java)
# ===========================================================================

def test_java_infinite_loop_flagged():
    src = textwrap.dedent("""\
        public class T {
            void f() { while (true) { System.out.println(1); } }
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_LOOP_001" in ids, f"Expected JAVA_LOOP_001 in {ids}"
    print("  ✓ JAVA_LOOP_001: while(true) without exit flagged")


def test_java_while_true_with_break_not_flagged():
    src = textwrap.dedent("""\
        public class T {
            void f() {
                while (true) {
                    if (done()) break;
                    work();
                }
            }
            boolean done() { return false; }
            void work() {}
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_LOOP_001" not in ids, "while(true) with break should not be flagged"
    print("  ✓ JAVA_LOOP_001: while(true) with break not flagged")


def test_java_while_condition_not_flagged():
    src = textwrap.dedent("""\
        public class T {
            void f(int n) { while (n > 0) { n--; } }
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_LOOP_001" not in ids, "while with condition should not be flagged"
    print("  ✓ JAVA_LOOP_001: while with real condition not flagged")

def test_candidate_issue_fields_present():
    src = "def f(a):\n    return a / 0\n"
    issues = _issues(src, "Python")
    assert len(issues) > 0, "Expected at least one issue"
    issue = issues[0]
    required = {
        "rule_id", "issue_type", "message", "file_path",
        "line_number", "column", "code_snippet", "evidence", "severity"
    }
    missing = required - issue.keys()
    assert not missing, f"CandidateIssue missing fields: {missing}"
    assert isinstance(issue["line_number"], int) and issue["line_number"] >= 1
    assert isinstance(issue["column"], int)
    assert isinstance(issue["evidence"], dict)
    assert issue["severity"] in ("high", "medium", "low")
    print("  ✓ CandidateIssue: all required fields present and typed correctly")


# ===========================================================================
# Rule registry
# ===========================================================================

def test_all_rules_have_unique_ids():
    ids = [r.rule_id for r in ALL_RULES]
    assert len(ids) == len(set(ids)), f"Duplicate rule IDs: {ids}"
    print(f"  ✓ Rule registry: {len(ids)} rules, all IDs unique")


def test_all_rules_declare_languages():
    for rule in ALL_RULES:
        assert rule.LANGUAGES, f"{rule.rule_id} has no LANGUAGES declared"
    print("  ✓ Rule registry: all rules declare at least one language")


# ===========================================================================
# End-to-end: analyze the full python_ast.json from the test output
# ===========================================================================

def test_full_python_ast_analysis():
    """Run the analyzer against the real AST from tests/output/python_ast.json
    and save the result to tests/output/python_static_analysis.json."""
    ast_path = OUTPUT_DIR / "python_ast.json"
    if not ast_path.exists():
        print("  ⚠ python_ast.json not found — skipping E2E test (run test_ast.py first)")
        return

    import json as _json
    with open(ast_path, encoding="utf-8") as f:
        ast_result = _json.load(f)

    analysis = analyzer.analyze(
        ast=ast_result["ast"],
        language=ast_result["language"],
        file_path=ast_result["file"],
    )

    assert analysis["issue_count"] >= 1, \
        f"Expected ≥1 issues from known-buggy Python sample, got {analysis['issue_count']}"

    out = save(analysis, "python_static_analysis.json")
    print(f"  ✓ E2E Python analysis: {analysis['issue_count']} issues → {out}")
    for issue in analysis["issues"]:
        print(f"      [{issue['rule_id']}] line {issue['line_number']}: {issue['message'][:70]}")


def test_full_javascript_ast_analysis():
    """Run the analyzer against javascript_ast.json."""
    ast_path = OUTPUT_DIR / "javascript_ast.json"
    if not ast_path.exists():
        print("  ⚠ javascript_ast.json not found — skipping")
        return

    import json as _json
    with open(ast_path, encoding="utf-8") as f:
        ast_result = _json.load(f)

    analysis = analyzer.analyze(
        ast=ast_result["ast"],
        language=ast_result["language"],
        file_path=ast_result["file"],
    )

    assert analysis["issue_count"] >= 1, \
        f"Expected ≥1 issues from known-buggy JS sample, got {analysis['issue_count']}"

    out = save(analysis, "javascript_static_analysis.json")
    print(f"  ✓ E2E JavaScript analysis: {analysis['issue_count']} issues → {out}")
    for issue in analysis["issues"]:
        print(f"      [{issue['rule_id']}] line {issue['line_number']}: {issue['message'][:70]}")


def test_full_java_ast_analysis():
    """Run the analyzer against java_ast.json."""
    ast_path = OUTPUT_DIR / "java_ast.json"
    if not ast_path.exists():
        print("  ⚠ java_ast.json not found — skipping")
        return

    import json as _json
    with open(ast_path, encoding="utf-8") as f:
        ast_result = _json.load(f)

    analysis = analyzer.analyze(
        ast=ast_result["ast"],
        language=ast_result["language"],
        file_path=ast_result["file"],
    )

    assert analysis["issue_count"] >= 1, \
        f"Expected ≥1 issues from known-buggy Java sample, got {analysis['issue_count']}"

    out = save(analysis, "java_static_analysis.json")
    print(f"  ✓ E2E Java analysis: {analysis['issue_count']} issues → {out}")
    for issue in analysis["issues"]:
        print(f"      [{issue['rule_id']}] line {issue['line_number']}: {issue['message'][:70]}")


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    tests = [
        # PY_DIV_001
        ("PY_DIV_001: variable divisor flagged",    test_py_div_variable_divisor_flagged),
        ("PY_DIV_001: literal divisor not flagged", test_py_div_literal_divisor_not_flagged),
        ("PY_DIV_001: floor division flagged",      test_py_div_floor_division_flagged),
        # PY_RES_001
        ("PY_RES_001: bare open() flagged",         test_py_res_bare_open_flagged),
        ("PY_RES_001: open() in with not flagged",  test_py_res_with_open_not_flagged),
        # PY_EXC_001
        ("PY_EXC_001: bare except flagged",         test_py_exc_bare_except_flagged),
        ("PY_EXC_001: typed except not flagged",    test_py_exc_typed_except_not_flagged),
        # PY_ASS_001
        ("PY_ASS_001: assert in prod flagged",      test_py_assert_production_flagged),
        ("PY_ASS_001: assert in test skipped",      test_py_assert_test_file_skipped),
        # PY_MUT_001
        ("PY_MUT_001: list default flagged",        test_py_mut_list_default_flagged),
        ("PY_MUT_001: dict default flagged",        test_py_mut_dict_default_flagged),
        ("PY_MUT_001: None default not flagged",    test_py_mut_none_default_not_flagged),
        # JS_DIV_001
        ("JS_DIV_001: variable divisor flagged",    test_js_div_variable_divisor_flagged),
        ("JS_DIV_001: literal divisor not flagged", test_js_div_literal_divisor_not_flagged),
        ("JS_DIV_001: modulo by variable flagged",  test_js_div_modulo_variable_flagged),
        # JS_EQ_001
        ("JS_EQ_001: == flagged",                   test_js_eq_double_equals_flagged),
        ("JS_EQ_001: != flagged",                   test_js_eq_not_equals_flagged),
        ("JS_EQ_001: === not flagged",              test_js_eq_triple_equals_not_flagged),
        # JS_AWA_001
        ("JS_AWA_001: await in for loop flagged",   test_js_await_in_for_loop_flagged),
        ("JS_AWA_001: await in while loop flagged", test_js_await_in_while_loop_flagged),
        ("JS_AWA_001: await outside loop safe",     test_js_await_outside_loop_not_flagged),
        # JAVA_DIV_001
        ("JAVA_DIV_001: variable divisor flagged",    test_java_div_variable_divisor_flagged),
        ("JAVA_DIV_001: literal divisor not flagged", test_java_div_literal_divisor_not_flagged),
        ("JAVA_DIV_001: modulo by variable flagged",  test_java_div_modulo_variable_flagged),
        # JAVA_EXC_001
        ("JAVA_EXC_001: empty catch flagged",         test_java_empty_catch_flagged),
        ("JAVA_EXC_001: catch with log not flagged",  test_java_catch_with_log_not_flagged),
        # JAVA_EQ_001
        ("JAVA_EQ_001: String == flagged",            test_java_string_eq_flagged),
        ("JAVA_EQ_001: null check not flagged",       test_java_null_check_not_flagged),
        ("JAVA_EQ_001: primitive == not flagged",     test_java_primitive_eq_not_flagged),
        # JAVA_RES_001
        ("JAVA_RES_001: FileReader flagged",          test_java_unclosed_filereader_flagged),
        ("JAVA_RES_001: try-with-resources safe",     test_java_try_with_resources_not_flagged),
        # JAVA_LOOP_001
        ("JAVA_LOOP_001: while(true) flagged",        test_java_infinite_loop_flagged),
        ("JAVA_LOOP_001: with break not flagged",     test_java_while_true_with_break_not_flagged),
        ("JAVA_LOOP_001: real condition not flagged", test_java_while_condition_not_flagged),
        # Structure & registry
        ("CandidateIssue: all fields present",      test_candidate_issue_fields_present),
        ("Registry: unique rule IDs",               test_all_rules_have_unique_ids),
        ("Registry: languages declared",            test_all_rules_declare_languages),
        # E2E
        ("E2E: full Python AST analysis",           test_full_python_ast_analysis),
        ("E2E: full JavaScript AST analysis",       test_full_javascript_ast_analysis),
        ("E2E: full Java AST analysis",             test_full_java_ast_analysis),
    ]

    passed = failed = 0
    print(f"\n{'='*60}")
    print("  Static Analyzer Test Suite")
    print(f"{'='*60}\n")

    for name, fn in tests:
        try:
            print(f"[RUN] {name}")
            fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"  Results: {passed} passed, {failed} failed")
    print(f"{'='*60}\n")

    sys.exit(0 if failed == 0 else 1)
"""
test_static_analyzer.py
-----------------------
Tests for the static analysis engine and every individual rule.

Run from backend/:
    python tests/test_static_analyzer.py
    python -m pytest tests/test_static_analyzer.py -v
"""

import sys
import json
import textwrap
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ast_generator import ASTGenerator
from app.services.static_analyzer import StaticAnalyzer, CandidateIssue
from app.services.static_analyzer.rules import ALL_RULES

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

gen = ASTGenerator()
analyzer = StaticAnalyzer()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ast(source: str, language: str) -> dict:
    """Parse source string into a normalized AST dict."""
    suffix = {"Python": ".py", "JavaScript": ".js", "Java": ".java"}[language]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    ) as f:
        f.write(source)
        path = f.name
    result = gen.generate_ast(path, language)
    Path(path).unlink(missing_ok=True)
    assert result["success"], f"AST generation failed: {result}"
    return result


def _issues(source: str, language: str) -> list:
    """Parse source and run the full analyzer. Returns list of issue dicts."""
    result = _ast(source, language)
    analysis = analyzer.analyze(
        ast=result["ast"],
        language=language,
        file_path=result["file"],
        source_code=source,
    )
    return analysis["issues"]


def _rule_ids(source: str, language: str) -> list:
    return [i["rule_id"] for i in _issues(source, language)]


def save(data: dict, filename: str) -> Path:
    out = OUTPUT_DIR / filename
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return out


# ===========================================================================
# PY_DIV_001 — Division by potentially zero value (Python)
# ===========================================================================

def test_py_div_variable_divisor_flagged():
    src = "def f(a, b):\n    return a / b\n"
    ids = _rule_ids(src, "Python")
    assert "PY_DIV_001" in ids, f"Expected PY_DIV_001 in {ids}"
    print("  ✓ PY_DIV_001: variable divisor flagged")


def test_py_div_literal_divisor_not_flagged():
    src = "def f(a):\n    return a / 2\n"
    ids = _rule_ids(src, "Python")
    assert "PY_DIV_001" not in ids, "Literal divisor should not be flagged"
    print("  ✓ PY_DIV_001: literal divisor not flagged")


def test_py_div_floor_division_flagged():
    src = "def f(a, b):\n    return a // b\n"
    ids = _rule_ids(src, "Python")
    assert "PY_DIV_001" in ids
    print("  ✓ PY_DIV_001: floor division flagged")


# ===========================================================================
# PY_RES_001 — open() outside with-statement (Python)
# ===========================================================================

def test_py_res_bare_open_flagged():
    src = textwrap.dedent("""\
        def read(path):
            f = open(path, "r")
            return f.read()
    """)
    ids = _rule_ids(src, "Python")
    assert "PY_RES_001" in ids, f"Expected PY_RES_001 in {ids}"
    print("  ✓ PY_RES_001: bare open() flagged")


def test_py_res_with_open_not_flagged():
    src = textwrap.dedent("""\
        def read(path):
            with open(path, "r") as f:
                return f.read()
    """)
    ids = _rule_ids(src, "Python")
    assert "PY_RES_001" not in ids, "open() inside with should not be flagged"
    print("  ✓ PY_RES_001: open() inside with not flagged")


# ===========================================================================
# PY_EXC_001 — Bare except clause (Python)
# ===========================================================================

def test_py_exc_bare_except_flagged():
    src = textwrap.dedent("""\
        try:
            x = int("abc")
        except:
            pass
    """)
    ids = _rule_ids(src, "Python")
    assert "PY_EXC_001" in ids, f"Expected PY_EXC_001 in {ids}"
    print("  ✓ PY_EXC_001: bare except flagged")


def test_py_exc_typed_except_not_flagged():
    src = textwrap.dedent("""\
        try:
            x = int("abc")
        except ValueError:
            pass
    """)
    ids = _rule_ids(src, "Python")
    assert "PY_EXC_001" not in ids, "Typed except should not be flagged"
    print("  ✓ PY_EXC_001: typed except not flagged")


# ===========================================================================
# PY_ASS_001 — assert in production code (Python)
# ===========================================================================

def test_py_assert_production_flagged():
    src = textwrap.dedent("""\
        def process(data):
            assert data is not None
            return data
    """)
    issues = _issues(src, "Python")
    ids = [i["rule_id"] for i in issues]
    assert "PY_ASS_001" in ids, f"Expected PY_ASS_001 in {ids}"
    print("  ✓ PY_ASS_001: assert in production code flagged")


def test_py_assert_test_file_skipped():
    src = textwrap.dedent("""\
        def test_something():
            assert 1 + 1 == 2
    """)
    result = _ast(src, "Python")
    # Simulate a test file path
    analysis = analyzer.analyze(
        ast=result["ast"],
        language="Python",
        file_path="/project/tests/test_utils.py",
        source_code=src,
    )
    ids = [i["rule_id"] for i in analysis["issues"]]
    assert "PY_ASS_001" not in ids, "assert in test file should be skipped"
    print("  ✓ PY_ASS_001: assert in test file not flagged")


# ===========================================================================
# PY_MUT_001 — Mutable default argument (Python)
# ===========================================================================

def test_py_mut_list_default_flagged():
    src = textwrap.dedent("""\
        def append_to(element, to=[]):
            to.append(element)
            return to
    """)
    ids = _rule_ids(src, "Python")
    assert "PY_MUT_001" in ids, f"Expected PY_MUT_001 in {ids}"
    print("  ✓ PY_MUT_001: list default flagged")


def test_py_mut_dict_default_flagged():
    src = textwrap.dedent("""\
        def update(key, val, store={}):
            store[key] = val
            return store
    """)
    ids = _rule_ids(src, "Python")
    assert "PY_MUT_001" in ids
    print("  ✓ PY_MUT_001: dict default flagged")


def test_py_mut_none_default_not_flagged():
    src = textwrap.dedent("""\
        def append_to(element, to=None):
            if to is None:
                to = []
            to.append(element)
            return to
    """)
    ids = _rule_ids(src, "Python")
    assert "PY_MUT_001" not in ids, "None default should not be flagged"
    print("  ✓ PY_MUT_001: None default not flagged")


# ===========================================================================
# JS_DIV_001 — Division by potentially zero value (JavaScript)
# ===========================================================================

def test_js_div_variable_divisor_flagged():
    src = textwrap.dedent("""\
        function f(a, b) {
            return a / b;
        }
    """)
    ids = _rule_ids(src, "JavaScript")
    assert "JS_DIV_001" in ids, f"Expected JS_DIV_001 in {ids}"
    print("  ✓ JS_DIV_001: variable divisor flagged")


def test_js_div_literal_divisor_not_flagged():
    src = textwrap.dedent("""\
        function f(a) {
            return a / 2;
        }
    """)
    ids = _rule_ids(src, "JavaScript")
    assert "JS_DIV_001" not in ids, "Literal divisor should not be flagged"
    print("  ✓ JS_DIV_001: literal divisor not flagged")


def test_js_div_modulo_variable_flagged():
    src = textwrap.dedent("""\
        function f(a, n) {
            return a % n;
        }
    """)
    ids = _rule_ids(src, "JavaScript")
    assert "JS_DIV_001" in ids
    print("  ✓ JS_DIV_001: modulo by variable flagged")


# ===========================================================================
# JS_EQ_001 — Loose equality (JavaScript)
# ===========================================================================

def test_js_eq_double_equals_flagged():
    src = textwrap.dedent("""\
        function check(a, b) {
            return a == b;
        }
    """)
    ids = _rule_ids(src, "JavaScript")
    assert "JS_EQ_001" in ids, f"Expected JS_EQ_001 in {ids}"
    print("  ✓ JS_EQ_001: == flagged")


def test_js_eq_not_equals_flagged():
    src = textwrap.dedent("""\
        function check(a, b) {
            return a != b;
        }
    """)
    ids = _rule_ids(src, "JavaScript")
    assert "JS_EQ_001" in ids
    print("  ✓ JS_EQ_001: != flagged")


def test_js_eq_triple_equals_not_flagged():
    src = textwrap.dedent("""\
        function check(a, b) {
            return a === b;
        }
    """)
    ids = _rule_ids(src, "JavaScript")
    assert "JS_EQ_001" not in ids, "=== should not be flagged"
    print("  ✓ JS_EQ_001: === not flagged")


# ===========================================================================
# JS_AWA_001 — await inside loop (JavaScript)
# ===========================================================================

def test_js_await_in_for_loop_flagged():
    src = textwrap.dedent("""\
        async function f(items) {
            for (let i = 0; i < items.length; i++) {
                const result = await fetchItem(items[i]);
                console.log(result);
            }
        }
    """)
    ids = _rule_ids(src, "JavaScript")
    assert "JS_AWA_001" in ids, f"Expected JS_AWA_001 in {ids}"
    print("  ✓ JS_AWA_001: await in for loop flagged")


def test_js_await_in_while_loop_flagged():
    src = textwrap.dedent("""\
        async function f(queue) {
            while (queue.length > 0) {
                await process(queue.pop());
            }
        }
    """)
    ids = _rule_ids(src, "JavaScript")
    assert "JS_AWA_001" in ids
    print("  ✓ JS_AWA_001: await in while loop flagged")


def test_js_await_outside_loop_not_flagged():
    src = textwrap.dedent("""\
        async function f(item) {
            const result = await fetchItem(item);
            return result;
        }
    """)
    ids = _rule_ids(src, "JavaScript")
    assert "JS_AWA_001" not in ids, "await outside loop should not be flagged"
    print("  ✓ JS_AWA_001: await outside loop not flagged")


# ===========================================================================
# JAVA_DIV_001 — Division by potentially zero value (Java)
# ===========================================================================

def test_java_div_variable_divisor_flagged():
    src = "public class T { int f(int a, int b) { return a / b; } }"
    ids = _rule_ids(src, "Java")
    assert "JAVA_DIV_001" in ids, f"Expected JAVA_DIV_001 in {ids}"
    print("  ✓ JAVA_DIV_001: variable divisor flagged")


def test_java_div_literal_divisor_not_flagged():
    src = "public class T { int f(int a) { return a / 2; } }"
    ids = _rule_ids(src, "Java")
    assert "JAVA_DIV_001" not in ids, "Literal divisor should not be flagged"
    print("  ✓ JAVA_DIV_001: literal divisor not flagged")


def test_java_div_modulo_variable_flagged():
    src = "public class T { int f(int a, int n) { return a % n; } }"
    ids = _rule_ids(src, "Java")
    assert "JAVA_DIV_001" in ids
    print("  ✓ JAVA_DIV_001: modulo by variable flagged")


# ===========================================================================
# JAVA_EXC_001 — Empty catch block (Java)
# ===========================================================================

def test_java_empty_catch_flagged():
    src = textwrap.dedent("""\
        public class T {
            void f() {
                try { int x = 1; } catch (Exception e) {}
            }
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_EXC_001" in ids, f"Expected JAVA_EXC_001 in {ids}"
    print("  ✓ JAVA_EXC_001: empty catch flagged")


def test_java_catch_with_log_not_flagged():
    src = textwrap.dedent("""\
        public class T {
            void f() {
                try { int x = 1; }
                catch (Exception e) { System.err.println(e.getMessage()); }
            }
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_EXC_001" not in ids, "Non-empty catch should not be flagged"
    print("  ✓ JAVA_EXC_001: catch with statement not flagged")


# ===========================================================================
# JAVA_EQ_001 — String reference equality (Java)
# ===========================================================================

def test_java_string_eq_flagged():
    # Use uppercase-starting variable names — Java convention for object references
    src = textwrap.dedent("""\
        public class T {
            boolean f(String Name, String Other) { return Name == Other; }
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_EQ_001" in ids, f"Expected JAVA_EQ_001 in {ids}"
    print("  ✓ JAVA_EQ_001: String == flagged")


def test_java_null_check_not_flagged():
    src = textwrap.dedent("""\
        public class T {
            boolean f(String s) { return s == null; }
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_EQ_001" not in ids, "null check should not be flagged"
    print("  ✓ JAVA_EQ_001: null check not flagged")


def test_java_primitive_eq_not_flagged():
    src = textwrap.dedent("""\
        public class T {
            boolean f(int a, int b) { return a == b; }
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_EQ_001" not in ids, "primitive == should not be flagged"
    print("  ✓ JAVA_EQ_001: primitive == not flagged")


# ===========================================================================
# JAVA_RES_001 — Unclosed resource (Java)
# ===========================================================================

def test_java_unclosed_filereader_flagged():
    src = textwrap.dedent("""\
        public class T {
            void f(String p) throws Exception {
                java.io.FileReader r = new java.io.FileReader(p);
                r.read();
            }
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_RES_001" in ids, f"Expected JAVA_RES_001 in {ids}"
    print("  ✓ JAVA_RES_001: FileReader outside try-with-resources flagged")


def test_java_try_with_resources_not_flagged():
    src = textwrap.dedent("""\
        public class T {
            void f(String p) throws Exception {
                try (java.io.FileReader r = new java.io.FileReader(p)) {
                    r.read();
                }
            }
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_RES_001" not in ids, "try-with-resources should not be flagged"
    print("  ✓ JAVA_RES_001: try-with-resources not flagged")


# ===========================================================================
# JAVA_LOOP_001 — while(true) without exit (Java)
# ===========================================================================

def test_java_infinite_loop_flagged():
    src = textwrap.dedent("""\
        public class T {
            void f() { while (true) { System.out.println(1); } }
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_LOOP_001" in ids, f"Expected JAVA_LOOP_001 in {ids}"
    print("  ✓ JAVA_LOOP_001: while(true) without exit flagged")


def test_java_while_true_with_break_not_flagged():
    src = textwrap.dedent("""\
        public class T {
            void f() {
                while (true) {
                    if (done()) break;
                    work();
                }
            }
            boolean done() { return false; }
            void work() {}
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_LOOP_001" not in ids, "while(true) with break should not be flagged"
    print("  ✓ JAVA_LOOP_001: while(true) with break not flagged")


def test_java_while_condition_not_flagged():
    src = textwrap.dedent("""\
        public class T {
            void f(int n) { while (n > 0) { n--; } }
        }
    """)
    ids = _rule_ids(src, "Java")
    assert "JAVA_LOOP_001" not in ids, "while with condition should not be flagged"
    print("  ✓ JAVA_LOOP_001: while with real condition not flagged")

def test_candidate_issue_fields_present():
    src = "def f(a, b):\n    return a / b\n"
    issues = _issues(src, "Python")
    assert len(issues) > 0, "Expected at least one issue"
    issue = issues[0]
    required = {
        "rule_id", "issue_type", "message", "file_path",
        "line_number", "column", "code_snippet", "evidence", "severity"
    }
    missing = required - issue.keys()
    assert not missing, f"CandidateIssue missing fields: {missing}"
    assert isinstance(issue["line_number"], int) and issue["line_number"] >= 1
    assert isinstance(issue["column"], int)
    assert isinstance(issue["evidence"], dict)
    assert issue["severity"] in ("high", "medium", "low")
    print("  ✓ CandidateIssue: all required fields present and typed correctly")


# ===========================================================================
# Rule registry
# ===========================================================================

def test_all_rules_have_unique_ids():
    ids = [r.rule_id for r in ALL_RULES]
    assert len(ids) == len(set(ids)), f"Duplicate rule IDs: {ids}"
    print(f"  ✓ Rule registry: {len(ids)} rules, all IDs unique")


def test_all_rules_declare_languages():
    for rule in ALL_RULES:
        assert rule.LANGUAGES, f"{rule.rule_id} has no LANGUAGES declared"
    print("  ✓ Rule registry: all rules declare at least one language")


# ===========================================================================
# End-to-end: analyze the full python_ast.json from the test output
# ===========================================================================

def test_full_python_ast_analysis():
    """Run the analyzer against the real AST from tests/output/python_ast.json
    and save the result to tests/output/python_static_analysis.json."""
    ast_path = OUTPUT_DIR / "python_ast.json"
    if not ast_path.exists():
        print("  ⚠ python_ast.json not found — skipping E2E test (run test_ast.py first)")
        return

    import json as _json
    with open(ast_path, encoding="utf-8") as f:
        ast_result = _json.load(f)

    analysis = analyzer.analyze(
        ast=ast_result["ast"],
        language=ast_result["language"],
        file_path=ast_result["file"],
    )

    assert analysis["issue_count"] >= 2, \
        f"Expected ≥2 issues from known-buggy Python sample, got {analysis['issue_count']}"

    out = save(analysis, "python_static_analysis.json")
    print(f"  ✓ E2E Python analysis: {analysis['issue_count']} issues → {out}")
    for issue in analysis["issues"]:
        print(f"      [{issue['rule_id']}] line {issue['line_number']}: {issue['message'][:70]}")


def test_full_javascript_ast_analysis():
    """Run the analyzer against javascript_ast.json."""
    ast_path = OUTPUT_DIR / "javascript_ast.json"
    if not ast_path.exists():
        print("  ⚠ javascript_ast.json not found — skipping")
        return

    import json as _json
    with open(ast_path, encoding="utf-8") as f:
        ast_result = _json.load(f)

    analysis = analyzer.analyze(
        ast=ast_result["ast"],
        language=ast_result["language"],
        file_path=ast_result["file"],
    )

    assert analysis["issue_count"] >= 1, \
        f"Expected ≥1 issues from known-buggy JS sample, got {analysis['issue_count']}"

    out = save(analysis, "javascript_static_analysis.json")
    print(f"  ✓ E2E JavaScript analysis: {analysis['issue_count']} issues → {out}")
    for issue in analysis["issues"]:
        print(f"      [{issue['rule_id']}] line {issue['line_number']}: {issue['message'][:70]}")


def test_full_java_ast_analysis():
    """Run the analyzer against java_ast.json."""
    ast_path = OUTPUT_DIR / "java_ast.json"
    if not ast_path.exists():
        print("  ⚠ java_ast.json not found — skipping")
        return

    import json as _json
    with open(ast_path, encoding="utf-8") as f:
        ast_result = _json.load(f)

    analysis = analyzer.analyze(
        ast=ast_result["ast"],
        language=ast_result["language"],
        file_path=ast_result["file"],
    )

    assert analysis["issue_count"] >= 1, \
        f"Expected ≥1 issues from known-buggy Java sample, got {analysis['issue_count']}"

    out = save(analysis, "java_static_analysis.json")
    print(f"  ✓ E2E Java analysis: {analysis['issue_count']} issues → {out}")
    for issue in analysis["issues"]:
        print(f"      [{issue['rule_id']}] line {issue['line_number']}: {issue['message'][:70]}")


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    tests = [
        # PY_DIV_001
        ("PY_DIV_001: variable divisor flagged",    test_py_div_variable_divisor_flagged),
        ("PY_DIV_001: literal divisor not flagged", test_py_div_literal_divisor_not_flagged),
        ("PY_DIV_001: floor division flagged",      test_py_div_floor_division_flagged),
        # PY_RES_001
        ("PY_RES_001: bare open() flagged",         test_py_res_bare_open_flagged),
        ("PY_RES_001: open() in with not flagged",  test_py_res_with_open_not_flagged),
        # PY_EXC_001
        ("PY_EXC_001: bare except flagged",         test_py_exc_bare_except_flagged),
        ("PY_EXC_001: typed except not flagged",    test_py_exc_typed_except_not_flagged),
        # PY_ASS_001
        ("PY_ASS_001: assert in prod flagged",      test_py_assert_production_flagged),
        ("PY_ASS_001: assert in test skipped",      test_py_assert_test_file_skipped),
        # PY_MUT_001
        ("PY_MUT_001: list default flagged",        test_py_mut_list_default_flagged),
        ("PY_MUT_001: dict default flagged",        test_py_mut_dict_default_flagged),
        ("PY_MUT_001: None default not flagged",    test_py_mut_none_default_not_flagged),
        # JS_DIV_001
        ("JS_DIV_001: variable divisor flagged",    test_js_div_variable_divisor_flagged),
        ("JS_DIV_001: literal divisor not flagged", test_js_div_literal_divisor_not_flagged),
        ("JS_DIV_001: modulo by variable flagged",  test_js_div_modulo_variable_flagged),
        # JS_EQ_001
        ("JS_EQ_001: == flagged",                   test_js_eq_double_equals_flagged),
        ("JS_EQ_001: != flagged",                   test_js_eq_not_equals_flagged),
        ("JS_EQ_001: === not flagged",              test_js_eq_triple_equals_not_flagged),
        # JS_AWA_001
        ("JS_AWA_001: await in for loop flagged",   test_js_await_in_for_loop_flagged),
        ("JS_AWA_001: await in while loop flagged", test_js_await_in_while_loop_flagged),
        ("JS_AWA_001: await outside loop safe",     test_js_await_outside_loop_not_flagged),
        # JAVA_DIV_001
        ("JAVA_DIV_001: variable divisor flagged",    test_java_div_variable_divisor_flagged),
        ("JAVA_DIV_001: literal divisor not flagged", test_java_div_literal_divisor_not_flagged),
        ("JAVA_DIV_001: modulo by variable flagged",  test_java_div_modulo_variable_flagged),
        # JAVA_EXC_001
        ("JAVA_EXC_001: empty catch flagged",         test_java_empty_catch_flagged),
        ("JAVA_EXC_001: catch with log not flagged",  test_java_catch_with_log_not_flagged),
        # JAVA_EQ_001
        ("JAVA_EQ_001: String == flagged",            test_java_string_eq_flagged),
        ("JAVA_EQ_001: null check not flagged",       test_java_null_check_not_flagged),
        ("JAVA_EQ_001: primitive == not flagged",     test_java_primitive_eq_not_flagged),
        # JAVA_RES_001
        ("JAVA_RES_001: FileReader flagged",          test_java_unclosed_filereader_flagged),
        ("JAVA_RES_001: try-with-resources safe",     test_java_try_with_resources_not_flagged),
        # JAVA_LOOP_001
        ("JAVA_LOOP_001: while(true) flagged",        test_java_infinite_loop_flagged),
        ("JAVA_LOOP_001: with break not flagged",     test_java_while_true_with_break_not_flagged),
        ("JAVA_LOOP_001: real condition not flagged", test_java_while_condition_not_flagged),
        # Structure & registry
        ("CandidateIssue: all fields present",      test_candidate_issue_fields_present),
        ("Registry: unique rule IDs",               test_all_rules_have_unique_ids),
        ("Registry: languages declared",            test_all_rules_declare_languages),
        # E2E
        ("E2E: full Python AST analysis",           test_full_python_ast_analysis),
        ("E2E: full JavaScript AST analysis",       test_full_javascript_ast_analysis),
        ("E2E: full Java AST analysis",             test_full_java_ast_analysis),
    ]

    passed = failed = 0
    print(f"\n{'='*60}")
    print("  Static Analyzer Test Suite")
    print(f"{'='*60}\n")

    for name, fn in tests:
        try:
            print(f"[RUN] {name}")
            fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"  Results: {passed} passed, {failed} failed")
    print(f"{'='*60}\n")

    sys.exit(0 if failed == 0 else 1)
