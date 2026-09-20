"""
test_remediation_regressions.py
===============================
Dedicated regression tests for Phase 2 Remediation findings:
  - FP-001: JS_PROMISE_001 — Higher-order event listeners and callback promises
  - FP-002: PY_RES_001 / JAVA_RES_001 — Resource handle aliasing
  - FN-001: PY_MUT_001 — Module-level mutable defaults and alias chains
  - FN-002: PY_RES_001 / JAVA_RES_001 — Conditional resource close detection
  - FN-003: JS_AWA_001 — Variable-name independent await-in-loop detection
  - FN-004: PY_UNREACH_001 / JS_UNREACH_001 / JAVA_UNREACH_001 — try/finally reachability
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from app.services.ast_generator import ASTGenerator
from app.services.static_analyzer import StaticAnalyzer

gen = ASTGenerator()
analyzer = StaticAnalyzer()


def _analyze(source: str, language: str, file_path: str = "src/Example") -> list[dict]:
    ext_map = {"Python": ".py", "JavaScript": ".js", "Java": ".java"}
    suffix = ext_map.get(language, ".txt")
    full_path = file_path if file_path.endswith(suffix) else file_path + suffix

    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8") as f:
        f.write(source)
        tmp_path = f.name

    try:
        ast_res = gen.generate_ast(tmp_path, language)
        assert ast_res.get("success"), f"AST generation failed: {ast_res.get('error')}"
        res = analyzer.analyze(
            ast=ast_res["ast"],
            file_path=full_path,
            language=language,
            source_code=source,
        )
        return res.get("issues", [])
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ==============================================================================
# FP-001: JS_PROMISE_001 — Higher-Order Callbacks & Event Listeners
# ==============================================================================
class TestJSPromiseRegressions:
    def test_event_listener_with_async_fetch_not_flagged(self):
        code = """
        button.addEventListener("click", async () => {
            await fetch(url);
        });
        """
        issues = [i for i in _analyze(code, "JavaScript") if i["rule_id"] == "JS_PROMISE_001"]
        assert len(issues) == 0, f"Expected 0 issues for event listener, got {issues}"

    def test_timeout_with_async_fetch_not_flagged(self):
        code = """
        setTimeout(async () => {
            await fetch(url);
        }, 1000);
        """
        issues = [i for i in _analyze(code, "JavaScript") if i["rule_id"] == "JS_PROMISE_001"]
        assert len(issues) == 0, f"Expected 0 issues for setTimeout callback, got {issues}"

    def test_utility_callback_with_returned_fetch_not_flagged(self):
        code = """
        someUtility(() => {
            return fetch(url);
        });
        """
        issues = [i for i in _analyze(code, "JavaScript") if i["rule_id"] == "JS_PROMISE_001"]
        assert len(issues) == 0, f"Expected 0 issues for callback return fetch, got {issues}"

    def test_floating_fetch_flagged(self):
        code = """
        fetch(url);
        """
        issues = [i for i in _analyze(code, "JavaScript") if i["rule_id"] == "JS_PROMISE_001"]
        assert len(issues) == 1, f"Expected 1 issue for floating fetch, got {issues}"

    def test_chained_catch_not_flagged(self):
        code = """
        fetch(url).catch(handleError);
        """
        issues = [i for i in _analyze(code, "JavaScript") if i["rule_id"] == "JS_PROMISE_001"]
        assert len(issues) == 0, f"Expected 0 issues for chained catch, got {issues}"

    def test_chained_then_not_flagged(self):
        code = """
        fetch(url).then(handleSuccess);
        """
        issues = [i for i in _analyze(code, "JavaScript") if i["rule_id"] == "JS_PROMISE_001"]
        assert len(issues) == 0, f"Expected 0 issues for chained then, got {issues}"


# ==============================================================================
# FP-002 & FN-002: Resource Tracking (Python & Java)
# ==============================================================================
class TestResourceTrackingRegressions:
    def test_python_alias_close_safe(self):
        code = """
        def process():
            f = open("data.txt")
            g = f
            g.close()
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_RES_001"]
        assert len(issues) == 0, f"Expected 0 issues for aliased close, got {issues}"

    def test_python_multistep_alias_close_safe(self):
        code = """
        def process():
            f = open("data.txt")
            g = f
            h = g
            h.close()
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_RES_001"]
        assert len(issues) == 0, f"Expected 0 issues for multi-step aliased close, got {issues}"

    def test_python_reassignment_separate_resources(self):
        code = """
        def process():
            f = open("a.txt")
            g = open("b.txt")
            f.close()
            g.close()
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_RES_001"]
        assert len(issues) == 0, f"Expected 0 issues for separate closed resources, got {issues}"

    def test_python_conditional_close_flagged(self):
        code = """
        def read_file(p, flag):
            f = open(p)
            if flag:
                f.close()
            return "done"
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_RES_001"]
        assert len(issues) == 1, f"Expected 1 issue for conditional close, got {issues}"

    def test_python_try_finally_close_safe(self):
        code = """
        def read_file(p):
            f = open(p)
            try:
                use(f)
            finally:
                f.close()
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_RES_001"]
        assert len(issues) == 0, f"Expected 0 issues for try/finally close, got {issues}"

    def test_java_alias_close_safe(self):
        code = """
        import java.io.*;
        public class App {
            public void run() throws Exception {
                FileInputStream in = new FileInputStream("data.txt");
                FileInputStream alias = in;
                alias.close();
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_RES_001"]
        assert len(issues) == 0, f"Expected 0 issues for Java aliased close, got {issues}"

    def test_java_conditional_close_flagged(self):
        code = """
        import java.io.*;
        public class App {
            public void run(boolean flag) throws Exception {
                FileInputStream in = new FileInputStream("data.txt");
                if (flag) {
                    in.close();
                }
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_RES_001"]
        assert len(issues) == 1, f"Expected 1 issue for Java conditional close, got {issues}"

    def test_java_try_finally_close_safe(self):
        code = """
        import java.io.*;
        public class App {
            public void run() throws Exception {
                FileInputStream in = new FileInputStream("data.txt");
                try {
                    in.read();
                } finally {
                    in.close();
                }
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_RES_001"]
        assert len(issues) == 0, f"Expected 0 issues for Java try/finally close, got {issues}"


# ==============================================================================
# FN-001: PY_MUT_001 — Module-Level Mutable Defaults & Aliases
# ==============================================================================
class TestPythonMutableDefaultRegressions:
    def test_module_level_list_default_flagged(self):
        code = """
        DEFAULT_ITEMS = []

        def f(x=DEFAULT_ITEMS):
            pass
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_MUT_001"]
        assert len(issues) == 1, f"Expected 1 issue for module-level mutable list default, got {issues}"

    def test_module_level_dict_default_flagged(self):
        code = """
        DEFAULT_CONFIG = {}

        def configure(config=DEFAULT_CONFIG):
            pass
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_MUT_001"]
        assert len(issues) == 1, f"Expected 1 issue for module-level mutable dict default, got {issues}"

    def test_multistep_alias_chain_flagged(self):
        code = """
        a = []
        b = a
        c = b

        def f(x=c):
            pass
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_MUT_001"]
        assert len(issues) == 1, f"Expected 1 issue for 3-step alias chain default, got {issues}"

    def test_direct_defaults_flagged(self):
        code = """
        def f(x=[]): pass
        def g(x={}): pass
        def h(x=set()): pass
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_MUT_001"]
        assert len(issues) == 3, f"Expected 3 issues for direct mutable defaults, got {issues}"

    def test_immutable_default_not_flagged(self):
        code = """
        DEFAULT_VALUE = 10

        def f(x=DEFAULT_VALUE, y=None, z="hello"):
            pass
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_MUT_001"]
        assert len(issues) == 0, f"Expected 0 issues for immutable defaults, got {issues}"


# ==============================================================================
# FN-003: JS_AWA_001 — Loop Variable Names & Await in Loop
# ==============================================================================
class TestJSAwaitInLoopRegressions:
    def test_count_variable_in_for_loop_flagged(self):
        code = """
        async function processAll(items) {
            for (let count = 0; count < items.length; count++) {
                await fetchItem(items[count]);
            }
        }
        """
        issues = [i for i in _analyze(code, "JavaScript") if i["rule_id"] == "JS_AWA_001"]
        assert len(issues) == 1, f"Expected 1 issue for loop with 'count' variable, got {issues}"

    def test_retry_attempt_index_in_for_loops_flagged(self):
        code = """
        async function run(items) {
            for (let retry = 0; retry < items.length; retry++) {
                await fetch(items[retry]);
            }
            for (let attempt = 0; attempt < items.length; attempt++) {
                await fetch(items[attempt]);
            }
        }
        """
        issues = [i for i in _analyze(code, "JavaScript") if i["rule_id"] == "JS_AWA_001"]
        assert len(issues) == 2, f"Expected 2 issues for for-loops with attempt/retry names, got {issues}"

    def test_actual_pagination_progression_not_flagged(self):
        code = """
        async function paginate(totalPages) {
            let page = 0;
            while (page < totalPages) {
                const response = await fetchPage(page);
                page = response.nextPage;
            }
        }
        """
        issues = [i for i in _analyze(code, "JavaScript") if i["rule_id"] == "JS_AWA_001"]
        assert len(issues) == 0, f"Expected 0 issues for actual pagination progression, got {issues}"

    def test_actual_retry_loop_with_decrement_not_flagged(self):
        code = """
        async function retryFetch() {
            let retries = 3;
            while (retries > 0) {
                try {
                    await fetch('/api');
                    break;
                } catch (e) {
                    retries--;
                }
            }
        }
        """
        issues = [i for i in _analyze(code, "JavaScript") if i["rule_id"] == "JS_AWA_001"]
        assert len(issues) == 0, f"Expected 0 issues for retry loop with decrement, got {issues}"


# ==============================================================================
# FN-004: Reachability with try/finally (Python, JS, Java)
# ==============================================================================
class TestTryFinallyReachabilityRegressions:
    def test_python_try_finally_unreachable_after_terminating_try(self):
        code = """
        def f():
            try:
                return 1
            finally:
                cleanup()

            x = 2
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_UNREACH_001"]
        assert len(issues) == 1, f"Expected 1 issue for unreachable code after try/finally, got {issues}"

    def test_python_try_finally_raise_in_try_unreachable_after(self):
        code = """
        def f():
            try:
                raise ValueError("error")
            finally:
                cleanup()

            x = 2
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_UNREACH_001"]
        assert len(issues) == 1, f"Expected 1 issue for unreachable code after terminating try with raise, got {issues}"

    def test_javascript_try_finally_unreachable_after_terminating_try(self):
        code = """
        function f() {
            try {
                return 1;
            } finally {
                cleanup();
            }

            let x = 2;
        }
        """
        issues = [i for i in _analyze(code, "JavaScript") if i["rule_id"] == "JS_UNREACH_001"]
        assert len(issues) == 1, f"Expected 1 issue for JS unreachable code after try/finally, got {issues}"

    def test_javascript_try_finally_throw_in_try_unreachable_after(self):
        code = """
        function f() {
            try {
                throw new Error("fail");
            } finally {
                cleanup();
            }

            let x = 2;
        }
        """
        issues = [i for i in _analyze(code, "JavaScript") if i["rule_id"] == "JS_UNREACH_001"]
        assert len(issues) == 1, f"Expected 1 issue for JS unreachable code after throw in try, got {issues}"

    def test_java_try_finally_unreachable_after_terminating_try(self):
        code = """
        public class App {
            public int test() {
                try {
                    return 1;
                } finally {
                    cleanup();
                }

                int x = 2;
            }
            private void cleanup() {}
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_UNREACH_001"]
        assert len(issues) == 1, f"Expected 1 issue for Java unreachable code after try/finally, got {issues}"


# ==============================================================================
# DEFECT-P3-001: Reachability with if / elif / else (Python, JS, Java)
# ==============================================================================
class TestDefectP3001Reachability:
    def test_reproducer_elif_continues_not_unreachable(self):
        code = """
        def f(a, b):
            if a:
                return 1
            elif b:
                x = 10
            else:
                return 2

            return x + 5
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_UNREACH_001"]
        assert len(issues) == 0, f"Expected 0 issues for continuing elif, got {issues}"

    def test_multi_elif_all_terminate_unreachable(self):
        code = """
        def f(a, b, c):
            if a:
                return 1
            elif b:
                return 2
            elif c:
                raise ValueError("c")
            else:
                return 3

            return 4
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_UNREACH_001"]
        assert len(issues) == 1, f"Expected 1 issue when all branches terminate, got {issues}"

    def test_multi_elif_one_continues_not_unreachable(self):
        code = """
        def f(a, b, c):
            if a:
                return 1
            elif b:
                return 2
            elif c:
                pass
            else:
                return 3

            return 4
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_UNREACH_001"]
        assert len(issues) == 0, f"Expected 0 issues when one elif continues, got {issues}"

    def test_if_elif_no_else_not_unreachable(self):
        code = """
        def f(a, b):
            if a:
                return 1
            elif b:
                return 2

            return 3
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_UNREACH_001"]
        assert len(issues) == 0, f"Expected 0 issues when no else exists, got {issues}"

    def test_nested_if_elif_all_terminate_unreachable(self):
        code = """
        def f(a, b, c):
            if a:
                if b:
                    return 1
                else:
                    return 2
            elif c:
                return 3
            else:
                return 4

            return 5
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_UNREACH_001"]
        assert len(issues) == 1, f"Expected 1 issue for nested terminating if/elif, got {issues}"

    def test_nested_if_elif_inner_continues_not_unreachable(self):
        code = """
        def f(a, b, c):
            if a:
                if b:
                    return 1
                else:
                    x = 2
            elif c:
                return 3
            else:
                return 4

            return 5
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_UNREACH_001"]
        assert len(issues) == 0, f"Expected 0 issues when inner branch continues, got {issues}"

    def test_try_finally_in_elif_terminates(self):
        code = """
        def f(a, b):
            if a:
                return 1
            elif b:
                try:
                    return 2
                finally:
                    cleanup()
            else:
                return 3

            return 4
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_UNREACH_001"]
        assert len(issues) == 1, f"Expected 1 issue when elif has terminating try/finally, got {issues}"

    def test_js_else_if_continues_not_unreachable(self):
        code = """
        function f(a, b) {
            if (a) {
                return 1;
            } else if (b) {
                let x = 10;
            } else {
                return 2;
            }
            return 3;
        }
        """
        issues = [i for i in _analyze(code, "JavaScript") if i["rule_id"] == "JS_UNREACH_001"]
        assert len(issues) == 0, f"Expected 0 issues for JS continuing else-if, got {issues}"

    def test_js_else_if_all_terminate_unreachable(self):
        code = """
        function f(a, b) {
            if (a) {
                return 1;
            } else if (b) {
                return 2;
            } else {
                return 3;
            }
            return 4;
        }
        """
        issues = [i for i in _analyze(code, "JavaScript") if i["rule_id"] == "JS_UNREACH_001"]
        assert len(issues) == 1, f"Expected 1 issue for JS all terminating else-if, got {issues}"

    def test_java_else_if_continues_not_unreachable(self):
        code = """
        public class App {
            public int f(boolean a, boolean b) {
                if (a) {
                    return 1;
                } else if (b) {
                    int x = 10;
                } else {
                    return 2;
                }
                return 3;
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_UNREACH_001"]
        assert len(issues) == 0, f"Expected 0 issues for Java continuing else-if, got {issues}"

    def test_java_else_if_all_terminate_unreachable(self):
        code = """
        public class App {
            public int f(boolean a, boolean b) {
                if (a) {
                    return 1;
                } else if (b) {
                    return 2;
                } else {
                    return 3;
                }
                return 4;
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_UNREACH_001"]
        assert len(issues) == 1, f"Expected 1 issue for Java all terminating else-if, got {issues}"


# ==============================================================================
# DEFECT-P3-002: Java Loop Progression Counter Analysis (JAVA_LOOP_001)
# ==============================================================================
class TestDefectP3002JavaLoopProgression:
    def test_reproducer_line_comment_does_not_progress_counter(self):
        code = """
        public class App {
            public void run() {
                int x = 0;
                while (true) {
                    // x++
                    if (x > 10) break;
                }
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_LOOP_001"]
        assert len(issues) == 1, f"Expected 1 infinite loop issue for line comment, got {issues}"

    def test_block_comment_does_not_progress_counter(self):
        code = """
        public class App {
            public void run() {
                int x = 0;
                while (true) {
                    /* x++ */
                    if (x > 10) break;
                }
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_LOOP_001"]
        assert len(issues) == 1, f"Expected 1 infinite loop issue for block comment, got {issues}"

    def test_string_literal_does_not_progress_counter(self):
        code = """
        public class App {
            public void run() {
                int x = 0;
                while (true) {
                    String s = "x++";
                    if (x > 10) break;
                }
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_LOOP_001"]
        assert len(issues) == 1, f"Expected 1 infinite loop issue for string literal, got {issues}"

    def test_sibling_variable_max_does_not_progress_counter(self):
        code = """
        public class App {
            public void run() {
                int x = 0;
                while (true) {
                    int max = 0;
                    max++;
                    if (x > 10) break;
                }
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_LOOP_001"]
        assert len(issues) == 1, f"Expected 1 infinite loop issue for sibling variable max++, got {issues}"

    def test_sibling_variable_xx_does_not_progress_counter(self):
        code = """
        public class App {
            public void run() {
                int x = 0;
                while (true) {
                    int xx = 0;
                    xx++;
                    if (x > 10) break;
                }
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_LOOP_001"]
        assert len(issues) == 1, f"Expected 1 infinite loop issue for sibling variable xx++, got {issues}"

    def test_legitimate_post_increment_safe(self):
        code = """
        public class App {
            public void run() {
                int x = 0;
                while (true) {
                    x++;
                    if (x > 10) break;
                }
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_LOOP_001"]
        assert len(issues) == 0, f"Expected 0 issues for legitimate x++, got {issues}"

    def test_legitimate_pre_increment_safe(self):
        code = """
        public class App {
            public void run() {
                int x = 0;
                while (true) {
                    ++x;
                    if (x > 10) break;
                }
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_LOOP_001"]
        assert len(issues) == 0, f"Expected 0 issues for legitimate ++x, got {issues}"

    def test_legitimate_plus_assign_safe(self):
        code = """
        public class App {
            public void run() {
                int x = 0;
                while (true) {
                    x += 1;
                    if (x > 10) break;
                }
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_LOOP_001"]
        assert len(issues) == 0, f"Expected 0 issues for legitimate x += 1, got {issues}"

    def test_legitimate_assign_add_safe(self):
        code = """
        public class App {
            public void run() {
                int x = 0;
                while (true) {
                    x = x + 1;
                    if (x > 10) break;
                }
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_LOOP_001"]
        assert len(issues) == 0, f"Expected 0 issues for legitimate x = x + 1, got {issues}"

    def test_legitimate_decrement_towards_lower_bound_safe(self):
        code = """
        public class App {
            public void run() {
                int x = 10;
                while (true) {
                    x--;
                    if (x < 0) break;
                }
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_LOOP_001"]
        assert len(issues) == 0, f"Expected 0 issues for legitimate x--, got {issues}"

    def test_diverging_decrement_flagged(self):
        code = """
        public class App {
            public void run() {
                int x = 0;
                while (true) {
                    x--;
                    if (x > 10) break;
                }
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_LOOP_001"]
        assert len(issues) == 1, f"Expected 1 issue for diverging counter x--, got {issues}"

    def test_inverted_condition_expression_safe(self):
        code = """
        public class App {
            public void run() {
                int x = 0;
                while (true) {
                    x++;
                    if (10 <= x) break;
                }
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_LOOP_001"]
        assert len(issues) == 0, f"Expected 0 issues for inverted condition 10 <= x with x++, got {issues}"


# ==============================================================================
# DEFECT-P3-003: Per-Allocation Resource Lifecycle Tracking (PY_RES_001, JAVA_RES_001)
# ==============================================================================
class TestDefectP3003ResourceLifecycle:
    def test_python_reproducer_reassignment_overwrites_unclosed_resource(self):
        code = """
        def process():
            f = open("a.txt")
            f = open("b.txt")
            f.close()
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_RES_001"]
        assert len(issues) == 1, f"Expected 1 issue for overwritten unclosed resource, got {issues}"
        assert "a.txt" in issues[0]["code_snippet"]

    def test_python_sequential_allocations_both_closed_safe(self):
        code = """
        def process():
            f = open("a.txt")
            f.close()
            f = open("b.txt")
            f.close()
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_RES_001"]
        assert len(issues) == 0, f"Expected 0 issues when both sequentially closed, got {issues}"

    def test_python_alias_before_reassignment_alias_closed_first_safe(self):
        code = """
        def process():
            f = open("a.txt")
            g = f
            f = open("b.txt")
            g.close()
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_RES_001"]
        assert len(issues) == 1, f"Expected 1 issue for leaked b.txt, got {issues}"
        assert "b.txt" in issues[0]["code_snippet"]

    def test_python_alias_before_reassignment_both_closed_safe(self):
        code = """
        def process():
            f = open("a.txt")
            g = f
            f = open("b.txt")
            f.close()
            g.close()
        """
        issues = [i for i in _analyze(code, "Python") if i["rule_id"] == "PY_RES_001"]
        assert len(issues) == 0, f"Expected 0 issues when both allocations closed via handles, got {issues}"

    def test_java_reproducer_reassignment_overwrites_unclosed_resource(self):
        code = """
        import java.io.*;
        public class App {
            public void process() throws Exception {
                FileInputStream f = new FileInputStream("a.txt");
                f = new FileInputStream("b.txt");
                f.close();
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_RES_001"]
        assert len(issues) == 1, f"Expected 1 issue for overwritten unclosed Java resource, got {issues}"
        assert "a.txt" in issues[0]["code_snippet"]

    def test_java_sequential_allocations_both_closed_safe(self):
        code = """
        import java.io.*;
        public class App {
            public void process() throws Exception {
                FileInputStream f = new FileInputStream("a.txt");
                f.close();
                f = new FileInputStream("b.txt");
                f.close();
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_RES_001"]
        assert len(issues) == 0, f"Expected 0 issues when both Java allocations sequentially closed, got {issues}"

    def test_java_alias_before_reassignment_alias_closed_first_safe(self):
        code = """
        import java.io.*;
        public class App {
            public void process() throws Exception {
                FileInputStream f = new FileInputStream("a.txt");
                FileInputStream g = f;
                f = new FileInputStream("b.txt");
                g.close();
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_RES_001"]
        assert len(issues) == 1, f"Expected 1 issue for leaked Java b.txt, got {issues}"
        assert "b.txt" in issues[0]["code_snippet"]

    def test_java_alias_before_reassignment_both_closed_safe(self):
        code = """
        import java.io.*;
        public class App {
            public void process() throws Exception {
                FileInputStream f = new FileInputStream("a.txt");
                FileInputStream g = f;
                f = new FileInputStream("b.txt");
                f.close();
                g.close();
            }
        }
        """
        issues = [i for i in _analyze(code, "Java") if i["rule_id"] == "JAVA_RES_001"]
        assert len(issues) == 0, f"Expected 0 issues when both Java allocations closed, got {issues}"

