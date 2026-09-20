"""
test_false_positive_regressions.py
==================================
Targeted regression suite specifically validating that previously observed false positive
patterns are eliminated and never regress.

Covers:
1. Division / Path / Normal arithmetic confusion
2. Exception handling with logging / re-raising / recovery
3. Managed resources (with, try-with-resources, close in scope, finally, return)
4. Loops with reachable exits and counter progression
5. Async operations (sleep, database transactions, for-await-of)
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
# 1. Division False-Positive Regressions
# ===========================================================================

class TestDivisionFalsePositives:

    def test_python_path_strings_not_flagged(self):
        src = """
        path = "C:/Users/Sam/Documents/project/file.py"
        url = "https://example.com/api/v1/resource"
        comment = "ratio of a / b in calculation"
        """
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_DIV_001")
        assert len(issues) == 0

    def test_python_unknown_variable_divisor_not_flagged(self):
        src = """
        def compute(a, b):
            return a / b

        def process(x):
            y = get_value()
            return x / y
        """
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_DIV_001")
        assert len(issues) == 0

    def test_python_guarded_division_not_flagged(self):
        src = """
        def div1(a, b):
            if b != 0:
                return a / b
            return 0

        def div2(a, b):
            if b == 0:
                return 0
            return a / b

        def div3(a, b):
            assert b != 0
            return a / b
        """
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_DIV_001")
        assert len(issues) == 0

    def test_javascript_path_strings_not_flagged(self):
        src = """
        const path = "C:/Users/Sam/project/a/b";
        const url = "https://api.domain.com/v1/items";
        """
        res = _analyze(src, "JavaScript")
        issues = _rule_issues(res, "JS_DIV_001")
        assert len(issues) == 0

    def test_javascript_unknown_divisor_not_flagged(self):
        src = """
        function calculate(total, count) {
            return total / count;
        }
        """
        res = _analyze(src, "JavaScript")
        issues = _rule_issues(res, "JS_DIV_001")
        assert len(issues) == 0

    def test_java_hex_literal_not_flagged(self):
        src = """
        public class D {
            int calc(int x) {
                return x / 0xFF;
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_DIV_001")
        assert len(issues) == 0

    def test_java_unknown_divisor_not_flagged(self):
        src = """
        public class D {
            int divide(int a, int b) {
                return a / b;
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_DIV_001")
        assert len(issues) == 0


# ===========================================================================
# 2. Exception Handling False-Positive Regressions
# ===========================================================================

class TestExceptionHandlingFalsePositives:

    def test_python_specific_exception_not_flagged(self):
        src = """
        try:
            val = int("123")
        except ValueError:
            val = 0
        """
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_EXC_001")
        assert len(issues) == 0

    def test_python_logged_exception_not_flagged(self):
        src = """
        import logging
        logger = logging.getLogger(__name__)

        try:
            risky_operation()
        except Exception as e:
            logger.error("Failed operation: %s", e)
        """
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_EXC_001")
        assert len(issues) == 0

    def test_python_reraised_exception_not_flagged(self):
        src = """
        try:
            risky_operation()
        except Exception:
            cleanup()
            raise
        """
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_EXC_001")
        assert len(issues) == 0

    def test_java_rethrowing_catch_not_flagged(self):
        src = """
        public class E {
            void run() throws Exception {
                try {
                    doWork();
                } catch (Exception e) {
                    cleanup();
                    throw e;
                }
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_EXC_001")
        assert len(issues) == 0

    def test_java_logged_catch_not_flagged(self):
        src = """
        public class E {
            void run() {
                try {
                    doWork();
                } catch (Exception e) {
                    log.error("Operation failed", e);
                }
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_EXC_001")
        assert len(issues) == 0

    def test_java_intentional_comment_catch_not_flagged(self):
        src = """
        public class E {
            void run() {
                try {
                    doWork();
                } catch (Exception ignored) {
                    // expected in test
                }
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_EXC_001")
        assert len(issues) == 0


# ===========================================================================
# 3. Resource Management False-Positive Regressions
# ===========================================================================

class TestResourceManagementFalsePositives:

    def test_python_with_statement_not_flagged(self):
        src = """
        with open("file.txt", "r") as f:
            data = f.read()
        """
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_RES_001")
        assert len(issues) == 0

    def test_python_explicit_close_not_flagged(self):
        src = """
        def read_file(path):
            f = open(path, "r")
            data = f.read()
            f.close()
            return data
        """
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_RES_001")
        assert len(issues) == 0

    def test_python_returned_file_not_flagged(self):
        src = """
        def get_stream(path):
            return open(path, "r")
        """
        res = _analyze(src, "Python")
        issues = _rule_issues(res, "PY_RES_001")
        assert len(issues) == 0

    def test_java_try_with_resources_not_flagged(self):
        src = """
        import java.io.*;
        public class R {
            void read(File f) throws Exception {
                try (FileInputStream stream = new FileInputStream(f)) {
                    stream.read();
                }
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_RES_001")
        assert len(issues) == 0

    def test_java_explicit_close_not_flagged(self):
        src = """
        import java.io.*;
        public class R {
            void read(File f) throws Exception {
                FileInputStream stream = new FileInputStream(f);
                stream.read();
                stream.close();
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_RES_001")
        assert len(issues) == 0


# ===========================================================================
# 4. Infinite Loop False-Positive Regressions
# ===========================================================================

class TestInfiniteLoopFalsePositives:

    def test_java_while_true_with_direct_break_not_flagged(self):
        src = """
        public class L {
            void run() {
                while (true) {
                    break;
                }
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_LOOP_001")
        assert len(issues) == 0

    def test_java_while_true_with_progressing_counter_not_flagged(self):
        src = """
        public class L {
            void run() {
                int x = 0;
                while (true) {
                    if (x >= 10) {
                        break;
                    }
                    x++;
                }
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_LOOP_001")
        assert len(issues) == 0

    def test_java_while_true_with_dynamic_break_not_flagged(self):
        src = """
        public class L {
            void run(boolean hasMore) {
                while (true) {
                    if (!hasMore) {
                        break;
                    }
                    processNext();
                }
            }
        }
        """
        res = _analyze(src, "Java")
        issues = _rule_issues(res, "JAVA_LOOP_001")
        assert len(issues) == 0


# ===========================================================================
# 5. Async / Await False-Positive Regressions
# ===========================================================================

class TestAsyncFalsePositives:

    def test_js_sleep_in_loop_not_flagged(self):
        src = """
        async function retryLoop() {
            for (let i = 0; i < 5; i++) {
                await sleep(1000);
            }
        }
        """
        res = _analyze(src, "JavaScript")
        issues = _rule_issues(res, "JS_AWA_001")
        assert len(issues) == 0

    def test_js_browser_automation_in_loop_not_flagged(self):
        src = """
        async function fillForm(inputs) {
            for (const input of inputs) {
                await page.click(input.selector);
            }
        }
        """
        res = _analyze(src, "JavaScript")
        issues = _rule_issues(res, "JS_AWA_001")
        assert len(issues) == 0
