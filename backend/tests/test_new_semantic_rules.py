"""
test_new_semantic_rules.py
==========================
Comprehensive unit, edge-case, and boundary tests for the 11 new semantic rules:
- Python: PY_EVAL_001, PY_NONE_001, PY_UNREACH_001, PY_CONSTCOND_001
- JavaScript: JS_EVAL_001, JS_UNREACH_001, JS_CONSTCOND_001, JS_PROMISE_001
- Java: JAVA_NULL_001, JAVA_UNREACH_001, JAVA_CONSTCOND_001
"""

import sys
import tempfile
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ast_generator import ASTGenerator
from app.services.static_analyzer import StaticAnalyzer

gen = ASTGenerator()
analyzer = StaticAnalyzer()


def _analyze(source: str, language: str, file_path: str = "src/main/Example"):
    ext_map = {"Python": ".py", "JavaScript": ".js", "Java": ".java"}
    suffix = ext_map[language]
    path_with_ext = file_path if file_path.endswith(suffix) else file_path + suffix

    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8") as f:
        f.write(source)
        tmp_path = f.name

    try:
        ast_result = gen.generate_ast(tmp_path, language)
        assert ast_result["success"], f"AST Generation failed: {ast_result}"
        return analyzer.analyze(
            ast=ast_result["ast"],
            file_path=path_with_ext,
            language=language,
            source_code=source,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _rule_issues(res: dict, rule_id: str) -> list:
    return [i for i in res["issues"] if i["rule_id"] == rule_id]


# ===========================================================================
# 1. PY_EVAL_001: Dangerous eval/exec in Python
# ===========================================================================

class TestPythonEvalUsage:

    def test_dynamic_eval_flagged(self):
        src = "def run(user_input):\n    return eval(user_input)\n"
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_EVAL_001")
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"

    def test_dynamic_exec_flagged(self):
        src = "def execute_code(code):\n    exec(code)\n"
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_EVAL_001")
        assert len(issues) == 1

    def test_static_literal_eval_suppressed(self):
        src = 'val = eval("1 + 1")\n'
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_EVAL_001")
        assert len(issues) == 0


# ===========================================================================
# 2. PY_NONE_001: None equality comparison in Python
# ===========================================================================

class TestPythonNoneComparison:

    def test_equality_none_flagged(self):
        src = "def check(x):\n    if x == None:\n        return True\n"
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_NONE_001")
        assert len(issues) == 1
        assert issues[0]["severity"] == "low"
        assert "is None" in issues[0]["message"]

    def test_inequality_none_flagged(self):
        src = "def check(x):\n    if x != None:\n        return x\n"
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_NONE_001")
        assert len(issues) == 1
        assert "is not None" in issues[0]["message"]

    def test_identity_none_not_flagged(self):
        src = "def check(x):\n    if x is None or x is not None:\n        return True\n"
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_NONE_001")
        assert len(issues) == 0


# ===========================================================================
# 3. PY_UNREACH_001: Unreachable code in Python
# ===========================================================================

class TestPythonUnreachableCode:

    def test_unreachable_after_return_flagged(self):
        src = "def f(x):\n    return x\n    print('dead code')\n"
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_UNREACH_001")
        assert len(issues) == 1
        assert "print('dead code')" in issues[0]["code_snippet"]

    def test_unreachable_after_raise_flagged(self):
        src = "def f():\n    raise ValueError('error')\n    cleanup()\n"
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_UNREACH_001")
        assert len(issues) == 1

    def test_reachable_code_not_flagged(self):
        src = "def f(x):\n    if x:\n        return x\n    print('reachable')\n"
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_UNREACH_001")
        assert len(issues) == 0


# ===========================================================================
# 4. PY_CONSTCOND_001: Constant condition in Python
# ===========================================================================

class TestPythonConstantCondition:

    def test_constant_if_true_flagged(self):
        src = "if True:\n    do_something()\n"
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_CONSTCOND_001")
        assert len(issues) == 1

    def test_constant_arithmetic_condition_flagged(self):
        src = "if 1 == 2:\n    never_run()\n"
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_CONSTCOND_001")
        assert len(issues) == 1

    def test_constant_while_false_flagged(self):
        src = "while False:\n    never_run()\n"
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_CONSTCOND_001")
        assert len(issues) == 1

    def test_name_main_idiom_suppressed(self):
        src = 'if __name__ == "__main__":\n    main()\n'
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_CONSTCOND_001")
        assert len(issues) == 0

    def test_type_checking_idiom_suppressed(self):
        src = 'if TYPE_CHECKING:\n    from typing import Optional\n'
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_CONSTCOND_001")
        assert len(issues) == 0


# ===========================================================================
# 5. JS_EVAL_001: Dangerous eval in JavaScript
# ===========================================================================

class TestJavaScriptEvalUsage:

    def test_dynamic_eval_flagged(self):
        src = "function run(userInput) { eval(userInput); }"
        res = _analyze(src, "JavaScript")
        issues = _rule_issues(res, "JS_EVAL_001")
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"

    def test_static_eval_suppressed(self):
        src = 'const result = eval("2 + 2");'
        res = _analyze(src, "JavaScript")
        issues = _rule_issues(res, "JS_EVAL_001")
        assert len(issues) == 0


# ===========================================================================
# 6. JS_UNREACH_001: Unreachable code in JavaScript
# ===========================================================================

class TestJavaScriptUnreachableCode:

    def test_unreachable_after_return_flagged(self):
        src = """
        function compute(x) {
            return x * 2;
            console.log("unreachable");
        }
        """
        res = _analyze(src, "JavaScript")
        issues = _rule_issues(res, "JS_UNREACH_001")
        assert len(issues) == 1

    def test_unreachable_after_throw_flagged(self):
        src = """
        function validate(x) {
            throw new Error("Invalid");
            return false;
        }
        """
        res = _analyze(src, "JavaScript")
        issues = _rule_issues(res, "JS_UNREACH_001")
        assert len(issues) == 1

    def test_reachable_branch_not_flagged(self):
        src = """
        function compute(x) {
            if (x > 0) {
                return x;
            }
            console.log("reachable");
        }
        """
        res = _analyze(src, "JavaScript")
        issues = _rule_issues(res, "JS_UNREACH_001")
        assert len(issues) == 0


# ===========================================================================
# 7. JS_CONSTCOND_001: Constant conditions in JavaScript
# ===========================================================================

class TestJavaScriptConstantCondition:

    def test_if_true_flagged(self):
        src = "if (true) { doSomething(); }"
        res = _analyze(src, "JavaScript")
        issues = _rule_issues(res, "JS_CONSTCOND_001")
        assert len(issues) == 1

    def test_if_false_flagged(self):
        src = "if (false) { doSomething(); }"
        res = _analyze(src, "JavaScript")
        issues = _rule_issues(res, "JS_CONSTCOND_001")
        assert len(issues) == 1

    def test_while_false_flagged(self):
        src = "while (false) { doSomething(); }"
        res = _analyze(src, "JavaScript")
        issues = _rule_issues(res, "JS_CONSTCOND_001")
        assert len(issues) == 1

    def test_dynamic_if_not_flagged(self):
        src = "if (isValid && count > 0) { process(); }"
        res = _analyze(src, "JavaScript")
        issues = _rule_issues(res, "JS_CONSTCOND_001")
        assert len(issues) == 0


# ===========================================================================
# 8. JS_PROMISE_001: Unhandled Promise in JavaScript
# ===========================================================================

class TestJavaScriptUnhandledPromise:

    def test_unhandled_fetch_flagged(self):
        src = """
        function syncHandler() {
            fetch('/api/data');
        }
        """
        res = _analyze(src, "JavaScript")
        issues = _rule_issues(res, "JS_PROMISE_001")
        assert len(issues) == 1
        assert issues[0]["severity"] == "medium"

    def test_awaited_fetch_not_flagged(self):
        src = """
        async function handler() {
            await fetch('/api/data');
        }
        """
        res = _analyze(src, "JavaScript")
        issues = _rule_issues(res, "JS_PROMISE_001")
        assert len(issues) == 0

    def test_catch_chained_fetch_not_flagged(self):
        src = """
        function handler() {
            fetch('/api/data').catch(err => console.error(err));
        }
        """
        res = _analyze(src, "JavaScript")
        issues = _rule_issues(res, "JS_PROMISE_001")
        assert len(issues) == 0


# ===========================================================================
# 9. JAVA_NULL_001: Obvious Null Dereference in Java
# ===========================================================================

class TestJavaNullDereference:

    def test_explicit_null_method_call_flagged(self):
        src = """
        public class N {
            void test() {
                String s = null;
                s.length();
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_NULL_001")
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"

    def test_explicit_null_field_access_flagged(self):
        src = """
        public class N {
            void test() {
                MyObj obj = null;
                int x = obj.value;
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_NULL_001")
        assert len(issues) == 1

    def test_non_null_variable_not_flagged(self):
        src = """
        public class N {
            void test() {
                String s = "hello";
                s.length();
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_NULL_001")
        assert len(issues) == 0

    def test_null_guarded_dereference_not_flagged(self):
        src = """
        public class N {
            void test(String s) {
                if (s != null) {
                    s.length();
                }
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_NULL_001")
        assert len(issues) == 0

    def test_early_exit_guard_not_flagged(self):
        src = """
        public class N {
            void test(String s) {
                if (s == null) {
                    return;
                }
                s.length();
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_NULL_001")
        assert len(issues) == 0


# ===========================================================================
# 10. JAVA_UNREACH_001: Unreachable Code in Java
# ===========================================================================

class TestJavaUnreachableCode:

    def test_unreachable_after_return_flagged(self):
        src = """
        public class U {
            int calc(int x) {
                return x * 2;
                System.out.println("dead");
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_UNREACH_001")
        assert len(issues) == 1

    def test_unreachable_after_throw_flagged(self):
        src = """
        public class U {
            void check(boolean ok) {
                throw new RuntimeException();
                doCleanup();
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_UNREACH_001")
        assert len(issues) == 1

    def test_reachable_code_not_flagged(self):
        src = """
        public class U {
            int calc(int x) {
                if (x > 0) {
                    return x;
                }
                return 0;
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_UNREACH_001")
        assert len(issues) == 0


# ===========================================================================
# 11. JAVA_CONSTCOND_001: Constant Condition in Java
# ===========================================================================

class TestJavaConstantCondition:

    def test_if_true_flagged(self):
        src = """
        public class C {
            void test() {
                if (true) {
                    doAction();
                }
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_CONSTCOND_001")
        assert len(issues) == 1

    def test_if_false_flagged(self):
        src = """
        public class C {
            void test() {
                if (false) {
                    doAction();
                }
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_CONSTCOND_001")
        assert len(issues) == 1

    def test_constant_comparison_flagged(self):
        src = """
        public class C {
            void test() {
                if (1 == 2) {
                    doAction();
                }
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_CONSTCOND_001")
        assert len(issues) == 1

    def test_dynamic_condition_not_flagged(self):
        src = """
        public class C {
            void test(boolean flag) {
                if (flag) {
                    doAction();
                }
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_CONSTCOND_001")
        assert len(issues) == 0
