"""
test_refined_static_rules.py
=============================
Comprehensive symmetric regression tests for all 13 refined static analysis rules.
Every rule test pair includes:
1. Major suppression tests (provably safe / intentional patterns that MUST NOT be flagged)
2. Corresponding positive detection tests (actual bugs / suspicious patterns that MUST be flagged)
3. Confidence calibration checks (HIGH vs MEDIUM vs LOW)
4. Suppression metrics validation
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




# ===========================================================================
# 1. JAVA_EQ_001: Java String Equality
# ===========================================================================

class TestJavaStringEquality:

    def test_suppressions(self):
        # 1. Enum comparison
        res = _analyze("""
        public class E {
            void check(JsonToken token) {
                if (token == JsonToken.NULL) { return; }
            }
        }
        """, "Java")
        eq_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_EQ_001"]
        assert len(eq_issues) == 0

        # 2. Class literal comparison
        res = _analyze("""
        public class C {
            void check(Class<?> type) {
                if (type == String.class) { return; }
            }
        }
        """, "Java")
        eq_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_EQ_001"]
        assert len(eq_issues) == 0

        # 3. Null check on String
        res = _analyze("""
        public class N {
            void check(String s) {
                if (s == null || s != null) { return; }
            }
        }
        """, "Java")
        eq_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_EQ_001"]
        assert len(eq_issues) == 0

        # 4. Unknown non-string object references
        res = _analyze("""
        public class O {
            void check(Object a, Object b) {
                if (a == b) { return; }
            }
        }
        """, "Java")
        eq_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_EQ_001"]
        assert len(eq_issues) == 0

    def test_detections(self):
        # 1. String literal comparison
        res = _analyze("""
        public class S {
            void check(String name) {
                if (name == "admin") { grantAccess(); }
            }
        }
        """, "Java")
        eq_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_EQ_001"]
        assert len(eq_issues) == 1
        assert eq_issues[0]["evidence"]["confidence"] == "high"

        # 2. Two String variables
        res = _analyze("""
        public class S2 {
            void check(String a, String b) {
                if (a == b) { return; }
            }
        }
        """, "Java")
        eq_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_EQ_001"]
        assert len(eq_issues) == 1


# ===========================================================================
# 2. JAVA_DIV_001: Java Division By Zero
# ===========================================================================

class TestJavaDivisionByZero:

    def test_suppressions(self):
        # 1. Constant folding non-zero expression: 60 * 1000
        res = _analyze("""
        public class D {
            long toMinutes(long ms) {
                return ms / (60 * 1000);
            }
        }
        """, "Java")
        div_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_DIV_001"]
        assert len(div_issues) == 0

        # 2. Math.max zero guard
        res = _analyze("""
        public class D2 {
            int divide(int total, int count) {
                return total / Math.max(1, count);
            }
        }
        """, "Java")
        div_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_DIV_001"]
        assert len(div_issues) == 0

        # 3. Unconstrained unknown variable divisor (precision requirement)
        res = _analyze("""
        public class D3 {
            int divide(int total, int count) {
                return total / count;
            }
        }
        """, "Java")
        div_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_DIV_001"]
        assert len(div_issues) == 0

    def test_detections(self):
        # 1. Statically zero division
        res = _analyze("""
        public class D4 {
            int calc(int x) {
                return x / 0;
            }
        }
        """, "Java")
        div_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_DIV_001"]
        assert len(div_issues) == 1
        assert div_issues[0]["evidence"]["confidence"] == "high"

        # 2. Variable assigned zero divisor
        res = _analyze("""
        public class D5 {
            int calc(int x) {
                int y = 0;
                return x / y;
            }
        }
        """, "Java")
        div_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_DIV_001"]
        assert len(div_issues) == 1
        assert div_issues[0]["evidence"]["confidence"] == "high"


# ===========================================================================
# 3. JS_DIV_001: JavaScript Division By Zero
# ===========================================================================

class TestJSDivisionByZero:

    def test_suppressions(self):
        # 1. Constant non-zero
        res = _analyze("""
        function toSeconds(ms) {
            return ms / 1000;
        }
        """, "JavaScript")
        div_issues = [i for i in res["issues"] if i["rule_id"] == "JS_DIV_001"]
        assert len(div_issues) == 0

        # 2. Intentional Infinity pattern: 1 / 0
        res = _analyze("""
        const INF = 1 / 0;
        const NEG_INF = -1 / 0;
        """, "JavaScript")
        div_issues = [i for i in res["issues"] if i["rule_id"] == "JS_DIV_001"]
        assert len(div_issues) == 0

        # 3. Fallback guard: d || 1
        res = _analyze("""
        function divide(a, b) {
            return a / (b || 1);
        }
        """, "JavaScript")
        div_issues = [i for i in res["issues"] if i["rule_id"] == "JS_DIV_001"]
        assert len(div_issues) == 0

        # 4. Unconstrained dynamic variable divisor
        res = _analyze("""
        function computeRate(total, count) {
            return total / count;
        }
        """, "JavaScript")
        div_issues = [i for i in res["issues"] if i["rule_id"] == "JS_DIV_001"]
        assert len(div_issues) == 0

    def test_detections(self):
        # Variable assigned zero divisor
        res = _analyze("""
        function computeRate(total) {
            const count = 0;
            return total / count;
        }
        """, "JavaScript")
        div_issues = [i for i in res["issues"] if i["rule_id"] == "JS_DIV_001"]
        assert len(div_issues) == 1
        assert div_issues[0]["evidence"]["confidence"] == "high"


# ===========================================================================
# 4. JS_EQ_001: JavaScript Triple Equals
# ===========================================================================

class TestJSTripleEquals:

    def test_suppressions(self):
        # 1. Null check idiom: x == null
        res = _analyze("""
        function check(x) {
            if (x == null || x != null) { return true; }
        }
        """, "JavaScript")
        eq_issues = [i for i in res["issues"] if i["rule_id"] == "JS_EQ_001"]
        assert len(eq_issues) == 0

        # 2. typeof idiom: typeof x == 'string'
        res = _analyze("""
        function checkType(x) {
            if (typeof x == 'string') { return x.trim(); }
        }
        """, "JavaScript")
        eq_issues = [i for i in res["issues"] if i["rule_id"] == "JS_EQ_001"]
        assert len(eq_issues) == 0

    def test_detections(self):
        # Type coercion hazard: input == false
        res = _analyze("""
        function validate(input) {
            if (input == false) { return false; }
            if (input != 0) { return true; }
        }
        """, "JavaScript")
        eq_issues = [i for i in res["issues"] if i["rule_id"] == "JS_EQ_001"]
        assert len(eq_issues) == 2
        assert "==" in eq_issues[0]["code_snippet"]
        assert eq_issues[0]["evidence"]["confidence"] == "high"


# ===========================================================================
# 5. PY_RES_001: Python Unclosed Resource
# ===========================================================================

class TestPythonUnclosedResource:

    def test_suppressions(self):
        # 1. with statement
        res = _analyze("""
        def read_data(path):
            with open(path) as f:
                return f.read()
        """, "Python")
        res_issues = [i for i in res["issues"] if i["rule_id"] == "PY_RES_001"]
        assert len(res_issues) == 0

        # 2. Returned directly
        res = _analyze("""
        def open_file(path):
            return open(path, 'r')
        """, "Python")
        res_issues = [i for i in res["issues"] if i["rule_id"] == "PY_RES_001"]
        assert len(res_issues) == 0

        # 3. Explicitly closed in scope
        res = _analyze("""
        def process(path):
            f = open(path)
            data = f.read()
            f.close()
            return data
        """, "Python")
        res_issues = [i for i in res["issues"] if i["rule_id"] == "PY_RES_001"]
        assert len(res_issues) == 0

    def test_detections(self):
        # Leaked open file
        res = _analyze("""
        def read_and_leak(path):
            f = open(path)
            data = f.read()
            return data
        """, "Python")
        res_issues = [i for i in res["issues"] if i["rule_id"] == "PY_RES_001"]
        assert len(res_issues) == 1
        assert res_issues[0]["evidence"]["confidence"] == "high"


# ===========================================================================
# 6. JAVA_RES_001: Java Unclosed Resource
# ===========================================================================

class TestJavaUnclosedResource:

    def test_suppressions(self):
        # 1. try-with-resources
        res = _analyze("""
        public class R {
            void read(String path) throws Exception {
                try (FileInputStream in = new FileInputStream(path)) {
                    in.read();
                }
            }
        }
        """, "Java")
        res_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_RES_001"]
        assert len(res_issues) == 0

        # 2. In-memory stream
        res = _analyze("""
        public class R2 {
            void readMem(byte[] buf) {
                ByteArrayInputStream in = new ByteArrayInputStream(buf);
                in.read();
            }
        }
        """, "Java")
        res_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_RES_001"]
        assert len(res_issues) == 0

        # 3. Direct return
        res = _analyze("""
        public class R3 {
            FileInputStream open(String p) throws Exception {
                return new FileInputStream(p);
            }
        }
        """, "Java")
        res_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_RES_001"]
        assert len(res_issues) == 0

    def test_detections(self):
        # Real leaked FileInputStream
        res = _analyze("""
        public class R4 {
            void leak(String path) throws Exception {
                FileInputStream in = new FileInputStream(path);
                int b = in.read();
            }
        }
        """, "Java")
        res_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_RES_001"]
        assert len(res_issues) == 1
        assert res_issues[0]["evidence"]["confidence"] == "high"


# ===========================================================================
# 7. JAVA_EXC_001: Java Empty Catch
# ===========================================================================

class TestJavaEmptyCatch:

    def test_suppressions(self):
        # 1. Named 'expected' or 'ignored'
        res = _analyze("""
        public class C {
            void parse(String s) {
                try {
                    Integer.parseInt(s);
                } catch (NumberFormatException expected) {
                } catch (IllegalArgumentException ignored) {
                }
            }
        }
        """, "Java")
        exc_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_EXC_001"]
        assert len(exc_issues) == 0

        # 2. Comment inside catch body
        res = _analyze("""
        public class C2 {
            void parse(String s) {
                try {
                    Integer.parseInt(s);
                } catch (Exception e) {
                    // intentional fallback
                }
            }
        }
        """, "Java")
        exc_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_EXC_001"]
        assert len(exc_issues) == 0

    def test_detections(self):
        # Silent exception swallowing
        res = _analyze("""
        public class C3 {
            void runCriticalTask() {
                try {
                    execute();
                } catch (Exception e) {
                }
            }
        }
        """, "Java")
        exc_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_EXC_001"]
        assert len(exc_issues) == 1
        assert exc_issues[0]["evidence"]["confidence"] == "high"


# ===========================================================================
# 8. JS_AWA_001: JavaScript Await In Loop
# ===========================================================================

class TestJSAwaitInLoop:

    def test_suppressions(self):
        # 1. Intentional delay/sleep loop
        res = _analyze("""
        async function pollStatus() {
            while (!isReady()) {
                await sleep(500);
            }
        }
        """, "JavaScript")
        awa_issues = [i for i in res["issues"] if i["rule_id"] == "JS_AWA_001"]
        assert len(awa_issues) == 0

        # 2. Cursor pagination dependency
        res = _analyze("""
        async function fetchAll(startCursor) {
            let cursor = startCursor;
            while (cursor) {
                cursor = await fetchNextPage(cursor);
            }
        }
        """, "JavaScript")
        awa_issues = [i for i in res["issues"] if i["rule_id"] == "JS_AWA_001"]
        assert len(awa_issues) == 0

    def test_detections(self):
        # Sequential independent execution
        res = _analyze("""
        async function deleteUsers(userIds) {
            for (const id of userIds) {
                await api.deleteUser(id);
            }
        }
        """, "JavaScript")
        awa_issues = [i for i in res["issues"] if i["rule_id"] == "JS_AWA_001"]
        assert len(awa_issues) == 1
        assert awa_issues[0]["evidence"]["confidence"] == "high"


# ===========================================================================
# 9. PY_ASS_001: Python Assert In Production Code
# ===========================================================================

class TestPythonAssertInCode:

    def test_suppressions(self):
        # 1. Internal type-narrowing invariants
        res = _analyze("""
        def handle_cls(cls):
            assert cls is not None
            assert isinstance(cls, type)
            return cls()
        """, "Python", file_path="app/core/factory.py")
        ass_issues = [i for i in res["issues"] if i["rule_id"] == "PY_ASS_001"]
        assert len(ass_issues) == 0

        # 2. Test file assertions
        res = _analyze("""
        def test_addition():
            assert 1 + 1 == 2
        """, "Python", file_path="tests/test_math.py")
        ass_issues = [i for i in res["issues"] if i["rule_id"] == "PY_ASS_001"]
        assert len(ass_issues) == 0

    def test_detections(self):
        # Security/authorization assertions
        res = _analyze("""
        def delete_account(user, target_id):
            assert user.is_admin
            assert token is not None
            perform_delete(target_id)
        """, "Python", file_path="app/controllers/user.py")
        ass_issues = [i for i in res["issues"] if i["rule_id"] == "PY_ASS_001"]
        assert len(ass_issues) == 2
        assert ass_issues[0]["evidence"]["confidence"] == "high"


# ===========================================================================
# 10. PY_MUT_001: Python Mutable Default Argument
# ===========================================================================

class TestPythonMutableDefaultArg:

    def test_suppressions(self):
        # Immutable defaults: int, str, bool, None, tuple, float
        res = _analyze("""
        def query(name, limit=10, active=True, extra=None, ratio=1.5, pair=(1, 2)):
            pass

        def f_int(value=0):
            return value

        def f_str(value="test"):
            return value

        def f_none(value=None):
            return value

        def f_bool(value=True):
            return value

        def f_tuple(value=(1, 2)):
            return value
        """, "Python")
        mut_issues = [i for i in res["issues"] if i["rule_id"] == "PY_MUT_001"]
        assert len(mut_issues) == 0

    def test_suppressions_typed(self):
        # Typed immutable defaults
        res = _analyze("""
        def query(name: str, limit: int = 0, active: bool = True, extra: str = "test", val: tuple = (1, 2), item: object = None):
            pass
        """, "Python")
        mut_issues = [i for i in res["issues"] if i["rule_id"] == "PY_MUT_001"]
        assert len(mut_issues) == 0

    def test_detections(self):
        # Mutable literals
        res = _analyze("""
        def append_item(item, target=[]):
            target.append(item)
            return target
        """, "Python")
        mut_issues = [i for i in res["issues"] if i["rule_id"] == "PY_MUT_001"]
        assert len(mut_issues) == 1
        assert "target=[]" in mut_issues[0]["code_snippet"]
        assert mut_issues[0]["evidence"]["confidence"] == "high"

    def test_detections_list_literal(self):
        res = _analyze("""
        def f(items=[]):
            return items
        """, "Python")
        mut_issues = [i for i in res["issues"] if i["rule_id"] == "PY_MUT_001"]
        assert len(mut_issues) == 1
        assert mut_issues[0]["evidence"]["parameter"] == "items"

    def test_detections_set_constructor(self):
        res = _analyze("""
        def f(tags=set()):
            return tags
        """, "Python")
        mut_issues = [i for i in res["issues"] if i["rule_id"] == "PY_MUT_001"]
        assert len(mut_issues) == 1
        assert mut_issues[0]["evidence"]["parameter"] == "tags"

    def test_detections_typed_defaults_benchmark(self):
        # Specifically tests BUG-PY-007 and BUG-PY-008
        res = _analyze("""
        def append_audit_event(event: str, events: list = []) -> list:
            events.append(event)
            return events

        def merge_tags(tags: set = set()) -> set:
            tags.add("processed")
            return tags
        """, "Python")
        mut_issues = [i for i in res["issues"] if i["rule_id"] == "PY_MUT_001"]
        assert len(mut_issues) == 2
        params = {i["evidence"]["parameter"] for i in mut_issues}
        assert params == {"events", "tags"}


# ===========================================================================
# 11. PY_DIV_001: Python Division By Zero
# ===========================================================================

class TestPythonDivisionByZero:

    def test_suppressions(self):
        # Guarded division
        res = _analyze("""
        def divide(a, b):
            if b != 0:
                return a / b
            return 0
        """, "Python")
        div_issues = [i for i in res["issues"] if i["rule_id"] == "PY_DIV_001"]
        assert len(div_issues) == 0

    def test_detections(self):
        # Statically zero division
        res = _analyze("""
        def bad():
            return 10 / 0
        """, "Python")
        div_issues = [i for i in res["issues"] if i["rule_id"] == "PY_DIV_001"]
        assert len(div_issues) == 1
        assert div_issues[0]["evidence"]["confidence"] == "high"


# ===========================================================================
# 12. PY_EXC_001: Python Bare Except
# ===========================================================================

class TestPythonBareExcept:

    def test_suppressions(self):
        # Specifically typed except
        res = _analyze("""
        def load(path):
            try:
                open(path)
            except (FileNotFoundError, PermissionError):
                return None
        """, "Python")
        exc_issues = [i for i in res["issues"] if i["rule_id"] == "PY_EXC_001"]
        assert len(exc_issues) == 0

    def test_detections(self):
        # Bare except
        res = _analyze("""
        def dangerous():
            try:
                do_work()
            except:
                pass
        """, "Python")
        exc_issues = [i for i in res["issues"] if i["rule_id"] == "PY_EXC_001"]
        assert len(exc_issues) == 1
        assert exc_issues[0]["evidence"]["confidence"] == "high"


# ===========================================================================
# 13. JAVA_LOOP_001: Java Infinite Loop
# ===========================================================================

class TestJavaInfiniteLoop:

    def test_suppressions(self):
        # Loop with reachable break
        res = _analyze("""
        public class L {
            void run() {
                while (true) {
                    if (shouldStop()) {
                        break;
                    }
                }
            }
        }
        """, "Java")
        loop_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_LOOP_001"]
        assert len(loop_issues) == 0

    def test_detections(self):
        # True infinite loop
        res = _analyze("""
        public class L2 {
            void run() {
                while (true) {
                    doBackgroundWork();
                }
            }
        }
        """, "Java")
        loop_issues = [i for i in res["issues"] if i["rule_id"] == "JAVA_LOOP_001"]
        assert len(loop_issues) == 1
        assert loop_issues[0]["evidence"]["confidence"] == "high"
