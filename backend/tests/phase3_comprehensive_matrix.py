"""
phase3_comprehensive_matrix.py
==============================
Exhaustive adversarial test matrix across all 24 rules and edge cases.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path("c:/Users/seque/Desktop/CODES/Projects/BugTracker/backend")
sys.path.insert(0, str(BACKEND_DIR))

from app.services.ast_generator import ASTGenerator
from app.services.static_analyzer import StaticAnalyzer

gen = ASTGenerator()
analyzer = StaticAnalyzer()


def analyze(source: str, language: str) -> list[dict]:
    ext_map = {"Python": ".py", "JavaScript": ".js", "Java": ".java"}
    suffix = ext_map.get(language, ".txt")

    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8") as f:
        f.write(source)
        tmp_path = f.name

    try:
        ast_res = gen.generate_ast(tmp_path, language)
        if not ast_res.get("success"):
            return []
        res = analyzer.analyze(
            ast=ast_res["ast"],
            file_path="src/Test" + suffix,
            language=language,
            source_code=source,
        )
        return res.get("issues", [])
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_rule(rule_id: str, lang: str, code: str, expect_flag: bool, desc: str):
    issues = [i for i in analyze(code, lang) if i.get("rule_id") == rule_id]
    has_issue = len(issues) > 0
    if has_issue == expect_flag:
        print(f"  OK   [{rule_id}] {desc}")
        return True, ""
    else:
        status = "FALSE POSITIVE" if has_issue and not expect_flag else "FALSE NEGATIVE"
        msg = f"  FAIL [{status}] [{rule_id}] {desc} — got {len(issues)} findings ({[i['message'] for i in issues]})"
        print(msg)
        return False, msg


def run_all():
    print("=" * 80)
    print("COMPREHENSIVE ADVERSARIAL MATRIX (ALL 24 RULES)")
    print("=" * 80)

    failures = []

    # --- 1. PY_DIV_001 ---
    ok, m = test_rule("PY_DIV_001", "Python", "def f(x):\n    if x != 0:\n        return 10 / x", False, "Guarded x != 0")
    if not ok: failures.append(m)
    ok, m = test_rule("PY_DIV_001", "Python", "def f(x):\n    if x == 0:\n        return 10 / x", True, "Guarded x == 0")
    if not ok: failures.append(m)
    ok, m = test_rule("PY_DIV_001", "Python", "def f(x):\n    if x > 10:\n        return 1\n    else:\n        return 100 / x", False, "Else of x > 10 is x <= 10, not zero")
    if not ok: failures.append(m)
    ok, m = test_rule("PY_DIV_001", "Python", "def f(x):\n    if x < -5:\n        return 1\n    else:\n        return 100 / x", False, "Else of x < -5 is x >= -5, not zero")
    if not ok: failures.append(m)

    # --- 2. PY_RES_001 ---
    ok, m = test_rule("PY_RES_001", "Python", "def f():\n    f = open('a.txt')\n    g = f\n    g.close()", False, "Aliased close g.close()")
    if not ok: failures.append(m)
    ok, m = test_rule("PY_RES_001", "Python", "def f(flag):\n    f = open('a.txt')\n    if flag:\n        f.close()", True, "Conditional close in if")
    if not ok: failures.append(m)
    ok, m = test_rule("PY_RES_001", "Python", "def f():\n    f = open('a.txt')\n    f = open('b.txt')\n    f.close()", True, "Overwritten resource allocation without close")
    if not ok: failures.append(m)

    # --- 3. PY_EXC_001 ---
    ok, m = test_rule("PY_EXC_001", "Python", "try:\n    x()\nexcept:\n    pass", True, "Bare except")
    if not ok: failures.append(m)
    ok, m = test_rule("PY_EXC_001", "Python", "try:\n    x()\nexcept BaseException:\n    pass", True, "BaseException except")
    if not ok: failures.append(m)
    ok, m = test_rule("PY_EXC_001", "Python", "try:\n    x()\nexcept ValueError:\n    pass", False, "Specific ValueError except")
    if not ok: failures.append(m)

    # --- 4. PY_ASS_001 ---
    ok, m = test_rule("PY_ASS_001", "Python", "assert x > 0", True, "Assert in prod code")
    if not ok: failures.append(m)
    ok, m = test_rule("PY_ASS_001", "Python", "assert isinstance(x, int)", False, "assert isinstance type guard")
    if not ok: failures.append(m)

    # --- 5. PY_MUT_001 ---
    ok, m = test_rule("PY_MUT_001", "Python", "DEFAULT = []\ndef f(x=DEFAULT):\n    pass", True, "Module mutable list default")
    if not ok: failures.append(m)
    ok, m = test_rule("PY_MUT_001", "Python", "a = []\nb = a\nc = b\ndef f(x=c):\n    pass", True, "Alias chain default")
    if not ok: failures.append(m)
    ok, m = test_rule("PY_MUT_001", "Python", "DEFAULT = (1, 2)\ndef f(x=DEFAULT):\n    pass", False, "Immutable tuple default")
    if not ok: failures.append(m)

    # --- 6. PY_EVAL_001 ---
    ok, m = test_rule("PY_EVAL_001", "Python", "eval(user_input)", True, "Dynamic eval")
    if not ok: failures.append(m)
    ok, m = test_rule("PY_EVAL_001", "Python", "eval('1 + 1')", False, "Static constant literal eval")
    if not ok: failures.append(m)

    # --- 7. PY_NONE_001 ---
    ok, m = test_rule("PY_NONE_001", "Python", "if x == None:\n    pass", True, "x == None")
    if not ok: failures.append(m)
    ok, m = test_rule("PY_NONE_001", "Python", "if x is None:\n    pass", False, "x is None")
    if not ok: failures.append(m)

    # --- 8. PY_UNREACH_001 ---
    ok, m = test_rule("PY_UNREACH_001", "Python", "def f():\n    return 1\n    x = 2", True, "Code after return")
    if not ok: failures.append(m)
    ok, m = test_rule("PY_UNREACH_001", "Python", "def f(a, b):\n    if a:\n        return 1\n    elif b:\n        x = 10\n    else:\n        return 2\n    return x + 5", False, "Code after if/elif/else where elif does not terminate")
    if not ok: failures.append(m)

    # --- 9. PY_CONSTCOND_001 ---
    ok, m = test_rule("PY_CONSTCOND_001", "Python", "if True:\n    pass", True, "if True")
    if not ok: failures.append(m)
    ok, m = test_rule("PY_CONSTCOND_001", "Python", "if __name__ == '__main__':\n    pass", False, "if __name__ == '__main__'")
    if not ok: failures.append(m)

    # --- 10. JS_DIV_001 ---
    ok, m = test_rule("JS_DIV_001", "JavaScript", "function f(x) { if (x > 10) return 1; else return 100 / x; }", False, "JS else of x > 10 is x <= 10")
    if not ok: failures.append(m)

    # --- 11. JS_EQ_001 ---
    ok, m = test_rule("JS_EQ_001", "JavaScript", "if (a == b) {}", True, "Loose equality a == b")
    if not ok: failures.append(m)
    ok, m = test_rule("JS_EQ_001", "JavaScript", "if (a == null) {}", False, "Loose equality a == null idiom")
    if not ok: failures.append(m)
    ok, m = test_rule("JS_EQ_001", "JavaScript", "if (typeof a == 'string') {}", False, "typeof a == 'string'")
    if not ok: failures.append(m)

    # --- 12. JS_AWA_001 ---
    ok, m = test_rule("JS_AWA_001", "JavaScript", "async function f(items) { for (let count = 0; count < items.length; count++) { await fetch(items[count]); } }", True, "Await in for loop with count var")
    if not ok: failures.append(m)
    ok, m = test_rule("JS_AWA_001", "JavaScript", "async function f() { while (cursor) { cursor = await fetch(cursor); } }", False, "Pagination loop updating cursor")
    if not ok: failures.append(m)

    # --- 13. JS_EVAL_001 ---
    ok, m = test_rule("JS_EVAL_001", "JavaScript", "eval(userInput);", True, "eval dynamic input")
    if not ok: failures.append(m)
    ok, m = test_rule("JS_EVAL_001", "JavaScript", "eval('42');", False, "eval static constant")
    if not ok: failures.append(m)

    # --- 14. JS_UNREACH_001 ---
    ok, m = test_rule("JS_UNREACH_001", "JavaScript", "function f() { return 1; let x = 2; }", True, "JS unreachable after return")
    if not ok: failures.append(m)
    ok, m = test_rule("JS_UNREACH_001", "JavaScript", "function f(a, b) { if (a) { return 1; } else if (b) { let x = 10; } else { return 2; } return 3; }", False, "JS code after if/else-if/else where else-if does not terminate")
    if not ok: failures.append(m)

    # --- 15. JS_CONSTCOND_001 ---
    ok, m = test_rule("JS_CONSTCOND_001", "JavaScript", "if (true) {}", True, "if (true)")
    if not ok: failures.append(m)
    ok, m = test_rule("JS_CONSTCOND_001", "JavaScript", "while (true) {}", False, "while (true)")
    if not ok: failures.append(m)

    # --- 16. JS_PROMISE_001 ---
    ok, m = test_rule("JS_PROMISE_001", "JavaScript", "fetch(url);", True, "Floating unhandled fetch")
    if not ok: failures.append(m)
    ok, m = test_rule("JS_PROMISE_001", "JavaScript", "button.addEventListener('click', async () => { await fetch(url); });", False, "Listener with async callback")
    if not ok: failures.append(m)
    ok, m = test_rule("JS_PROMISE_001", "JavaScript", "const p = () => fetch(url);", False, "Arrow function returning fetch")
    if not ok: failures.append(m)

    # --- 17. JAVA_DIV_001 ---
    ok, m = test_rule("JAVA_DIV_001", "Java", "public class A { public int f(int x) { if (x > 10) return 1; else return 100 / x; } }", False, "Java else of x > 10 is x <= 10")
    if not ok: failures.append(m)

    # --- 18. JAVA_EXC_001 ---
    ok, m = test_rule("JAVA_EXC_001", "Java", "public class A { public void f() { try { doWork(); } catch (Exception e) {} } }", True, "Empty catch block")
    if not ok: failures.append(m)
    ok, m = test_rule("JAVA_EXC_001", "Java", "public class A { public void f() { try { doWork(); } catch (Exception ignored) {} } }", False, "Intentionally ignored catch")
    if not ok: failures.append(m)

    # --- 19. JAVA_EQ_001 ---
    ok, m = test_rule("JAVA_EQ_001", "Java", "public class A { public boolean f(String a, String b) { return a == b; } }", True, "String == comparison")
    if not ok: failures.append(m)
    ok, m = test_rule("JAVA_EQ_001", "Java", "public class A { public boolean f(int id, int otherId) { return id == otherId; } }", False, "int id == otherId")
    if not ok: failures.append(m)

    # --- 20. JAVA_RES_001 ---
    ok, m = test_rule("JAVA_RES_001", "Java", "import java.io.*; public class A { public void f() throws Exception { FileInputStream in = new FileInputStream('a'); in.close(); } }", False, "Direct close in Java")
    if not ok: failures.append(m)
    ok, m = test_rule("JAVA_RES_001", "Java", "import java.io.*; public class A { public void f(boolean flag) throws Exception { FileInputStream in = new FileInputStream('a'); if (flag) in.close(); } }", True, "Conditional close in Java")
    if not ok: failures.append(m)

    # --- 21. JAVA_LOOP_001 ---
    ok, m = test_rule("JAVA_LOOP_001", "Java", "public class A { public void f() { while (true) {} } }", True, "while(true) with no break")
    if not ok: failures.append(m)
    ok, m = test_rule("JAVA_LOOP_001", "Java", "public class A { public void f() { while (true) { break; } } }", False, "while(true) with unconditional break")
    if not ok: failures.append(m)
    ok, m = test_rule("JAVA_LOOP_001", "Java", "public class A { public void f() { int x = 0; while (true) { // x++\n if (x > 10) break; } } }", True, "while(true) with comment // x++")
    if not ok: failures.append(m)

    # --- 22. JAVA_NULL_001 ---
    ok, m = test_rule("JAVA_NULL_001", "Java", "public class A { public void f() { String s = null; s.length(); } }", True, "Null method call s.length()")
    if not ok: failures.append(m)
    ok, m = test_rule("JAVA_NULL_001", "Java", "public class A { public void f() { String s = null; if (s != null) { s.length(); } } }", False, "Guarded null method call")
    if not ok: failures.append(m)

    # --- 23. JAVA_UNREACH_001 ---
    ok, m = test_rule("JAVA_UNREACH_001", "Java", "public class A { public int f() { return 1; int x = 2; } }", True, "Java unreachable after return")
    if not ok: failures.append(m)

    # --- 24. JAVA_CONSTCOND_001 ---
    ok, m = test_rule("JAVA_CONSTCOND_001", "Java", "public class A { public void f() { if (true) {} } }", True, "Java if (true)")
    if not ok: failures.append(m)
    ok, m = test_rule("JAVA_CONSTCOND_001", "Java", "public class A { public void f() { while (true) {} } }", False, "Java while (true)")
    if not ok: failures.append(m)

    print("\n" + "=" * 80)
    print(f"FAILED ADVERSARIAL CASES: {len(failures)}")
    for f in failures:
        print(f)
    print("=" * 80)


if __name__ == "__main__":
    run_all()
