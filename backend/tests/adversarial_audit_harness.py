"""
adversarial_audit_harness.py
============================
Strict, independent adversarial test harness for Phase 2 Quality Audit of BugTracker Static Analyzer V2.
Tests ALL 24 active rules individually across:
  A. Positive cases (simplest, realistic, multiple, nested, inside functions/classes)
  B. Negative cases (safe code, legitimate idioms, equivalent safe alternatives, syntax decoys)
  C. Edge cases (nesting, branches, loops, try/catch/finally, aliases, reassignment, shadowing, constants, unknown values, early exits)
  D. Adversarial attack cases (specifically probing sections 5-21)

Also audits:
  - Cross-rule interactions & deduplication
  - Output contract schema adherence
  - Performance profiling (small, medium, large, deeply nested ASTs)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# Ensure backend path is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.services.ast_generator import ASTGenerator
from app.services.static_analyzer import StaticAnalyzer
from app.services.static_analyzer.rules import ALL_RULES

gen = ASTGenerator()
analyzer = StaticAnalyzer()


@dataclass
class TestCaseResult:
    category: str  # 'positive', 'negative', 'edge', 'adversarial'
    name: str
    rule_id: str
    language: str
    source_code: str
    expected_findings_count: Optional[int]  # None if min expectation or specific rule check
    actual_findings_count: int
    passed: bool
    issues: List[Dict[str, Any]]
    failure_reason: Optional[str] = None
    is_false_positive: bool = False
    is_false_negative: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleAuditSummary:
    rule_id: str
    language: str
    positive_total: int = 0
    positive_passed: int = 0
    negative_total: int = 0
    negative_passed: int = 0
    edge_total: int = 0
    edge_passed: int = 0
    adversarial_total: int = 0
    adversarial_passed: int = 0
    false_positives: List[TestCaseResult] = field(default_factory=list)
    false_negatives: List[TestCaseResult] = field(default_factory=list)
    other_failures: List[TestCaseResult] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.false_positives or self.false_negatives or self.other_failures:
            # If there are severe logic bugs, FAIL or PASS WITH WARNINGS
            if len(self.false_positives) > 1 or len(self.false_negatives) > 1:
                return "FAIL"
            return "PASS WITH WARNINGS"
        return "PASS"


class AdversarialAuditRunner:
    def __init__(self):
        self.results: List[TestCaseResult] = []
        self.summaries: Dict[str, RuleAuditSummary] = {}
        # Pre-populate all 24 rules
        for r in ALL_RULES:
            lang = r.LANGUAGES[0] if r.LANGUAGES else "Unknown"
            self.summaries[r.rule_id] = RuleAuditSummary(rule_id=r.rule_id, language=lang)

    def analyze_source(self, source: str, language: str, file_path: str = "src/Example") -> Dict[str, Any]:
        ext_map = {"Python": ".py", "JavaScript": ".js", "Java": ".java"}
        suffix = ext_map.get(language, ".txt")
        full_path = file_path if file_path.endswith(suffix) else file_path + suffix

        with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8") as f:
            f.write(source)
            tmp_path = f.name

        try:
            ast_res = gen.generate_ast(tmp_path, language)
            if not ast_res.get("success"):
                return {"success": False, "error": ast_res.get("error"), "issues": []}
            res = analyzer.analyze(
                ast=ast_res["ast"],
                file_path=full_path,
                language=language,
                source_code=source,
            )
            return res
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def run_case(
        self,
        category: str,
        name: str,
        rule_id: str,
        language: str,
        source_code: str,
        expected_findings: int,
        file_path: str = "src/Example",
        validator: Optional[Callable[[List[Dict[str, Any]]], Tuple[bool, Optional[str]]]] = None,
    ) -> TestCaseResult:
        res = self.analyze_source(source_code, language, file_path=file_path)
        issues = [i for i in res.get("issues", []) if i.get("rule_id") == rule_id]
        actual_count = len(issues)

        passed = True
        failure_reason = None
        is_fp = False
        is_fn = False

        if category in ("positive", "edge_positive", "adversarial_positive"):
            if actual_count < expected_findings:
                passed = False
                is_fn = True
                failure_reason = f"Expected >= {expected_findings} findings for {rule_id}, got {actual_count}"
        elif category in ("negative", "edge_negative", "adversarial_negative"):
            if actual_count > 0:
                passed = False
                is_fp = True
                failure_reason = f"False Positive: Expected 0 findings for {rule_id}, got {actual_count} ({[i['message'] for i in issues]})"
        else:
            if actual_count != expected_findings:
                passed = False
                if expected_findings == 0 and actual_count > 0:
                    is_fp = True
                elif expected_findings > 0 and actual_count == 0:
                    is_fn = True
                failure_reason = f"Expected {expected_findings} findings for {rule_id}, got {actual_count}"

        if passed and validator:
            v_ok, v_err = validator(issues)
            if not v_ok:
                passed = False
                failure_reason = f"Validation failed: {v_err}"

        tc_res = TestCaseResult(
            category=category,
            name=name,
            rule_id=rule_id,
            language=language,
            source_code=source_code,
            expected_findings_count=expected_findings,
            actual_findings_count=actual_count,
            passed=passed,
            issues=issues,
            failure_reason=failure_reason,
            is_false_positive=is_fp,
            is_false_negative=is_fn,
            details={"all_issues": res.get("issues", [])},
        )
        self.results.append(tc_res)

        # Update summary
        summary = self.summaries.get(rule_id)
        if summary:
            cat_norm = category.split("_")[0]
            if cat_norm == "positive":
                summary.positive_total += 1
                if passed:
                    summary.positive_passed += 1
            elif cat_norm == "negative":
                summary.negative_total += 1
                if passed:
                    summary.negative_passed += 1
            elif cat_norm == "edge":
                summary.edge_total += 1
                if passed:
                    summary.edge_passed += 1
            elif cat_norm == "adversarial":
                summary.adversarial_total += 1
                if passed:
                    summary.adversarial_passed += 1

            if is_fp:
                summary.false_positives.append(tc_res)
            elif is_fn:
                summary.false_negatives.append(tc_res)
            elif not passed:
                summary.other_failures.append(tc_res)

        return tc_res


def register_all_tests(runner: AdversarialAuditRunner):
    """Registers comprehensive test suites for each of the 24 rules."""

    # =========================================================================
    # 1. PY_DIV_001 (Python Division by Zero)
    # =========================================================================
    r = "PY_DIV_001"
    lang = "Python"
    # Positive
    runner.run_case("positive", "PY_DIV: simple x / 0", r, lang, "x = 10 / 0\n", 1)
    runner.run_case("positive", "PY_DIV: integer // 0", r, lang, "def f(a):\n    return a // 0\n", 1)
    runner.run_case("positive", "PY_DIV: nested occurrence in class method", r, lang,
                    "class Calc:\n    def divide(self, val):\n        return val / 0.0\n", 1)
    runner.run_case("positive", "PY_DIV: multiple occurrences", r, lang,
                    "a = 1 / 0\nb = 2 / 0\n", 2)
    runner.run_case("positive", "PY_DIV: alias propagation x=0; y=x; z=y; 10/z", r, lang,
                    "x = 0\ny = x\nz = y\nans = 10 / z\n", 1)
    runner.run_case("positive", "PY_DIV: constant folded zero 10 / (2 - 2)", r, lang,
                    "ans = 10 / (2 - 2)\n", 1)
    runner.run_case("positive", "PY_DIV: inside known-zero guard `if x == 0: 10 / x`", r, lang,
                    "def f(x):\n    if x == 0:\n        return 10 / x\n", 1)
    runner.run_case("positive", "PY_DIV: both branches assign 0 `if c: x=0 else: x=0; 10/x`", r, lang,
                    "if c:\n    x = 0\nelse:\n    x = 0\ny = 10 / x\n", 1)

    # Negative
    runner.run_case("negative", "PY_DIV: safe division x / 1", r, lang, "ans = 10 / 1\n", 0)
    runner.run_case("negative", "PY_DIV: safe division x / -1", r, lang, "ans = 10 / -1\n", 0)
    runner.run_case("negative", "PY_DIV: unconstrained dynamic parameter x / y", r, lang,
                    "def f(x, y):\n    return x / y\n", 0)
    runner.run_case("negative", "PY_DIV: protected by try-except ZeroDivisionError", r, lang,
                    "try:\n    x = 10 / 0\nexcept ZeroDivisionError:\n    x = 0\n", 0)
    runner.run_case("negative", "PY_DIV: guarded by `if x != 0`", r, lang,
                    "def f(x):\n    if x != 0:\n        return 10 / x\n", 0)
    runner.run_case("negative", "PY_DIV: guarded by early return `if x == 0: return; 10 / x`", r, lang,
                    "def f(x):\n    if x == 0:\n        return\n    return 10 / x\n", 0)
    runner.run_case("negative", "PY_DIV: safe reassignment x=0; x=1; 10/x", r, lang,
                    "x = 0\nx = 1\ny = 10 / x\n", 0)
    runner.run_case("negative", "PY_DIV: string and comment decoy", r, lang,
                    'text = "10 / 0"\n# 10 / 0\n', 0)

    # Edge & Adversarial
    runner.run_case("edge_negative", "PY_DIV: path sensitive if c: x=0 else: x=1; 10/x", r, lang,
                    "if condition:\n    x = 0\nelse:\n    x = 1\ny = 10 / x\n", 0)
    runner.run_case("edge_positive", "PY_DIV: hex and binary zero literals 0x0, 0b0", r, lang,
                    "a = 10 / 0x0\nb = 10 / 0b0\n", 2)
    runner.run_case("edge_negative", "PY_DIV: hex and binary non-zero literals 0x1, 0b1", r, lang,
                    "a = 10 / 0x1\nb = 10 / 0b1\n", 0)
    runner.run_case("adversarial_positive", "PY_DIV: nested arithmetic zero 10 / ((5 * 2) - 10)", r, lang,
                    "y = 10 / ((5 * 2) - 10)\n", 1)
    runner.run_case("adversarial_negative", "PY_DIV: dynamic function call divisor x = get_val(); 10/x", r, lang,
                    "x = get_val()\ny = 10 / x\n", 0)

    # =========================================================================
    # 2. PY_EXC_001 (Python Exception Handling)
    # =========================================================================
    r = "PY_EXC_001"
    lang = "Python"
    # Positive
    runner.run_case("positive", "PY_EXC: bare except:", r, lang,
                    "try:\n    do_something()\nexcept:\n    pass\n", 1)
    runner.run_case("positive", "PY_EXC: except BaseException:", r, lang,
                    "try:\n    do_something()\nexcept BaseException:\n    pass\n", 1)
    runner.run_case("positive", "PY_EXC: except Exception: pass (swallowed)", r, lang,
                    "try:\n    do_something()\nexcept Exception:\n    pass\n", 1)
    runner.run_case("positive", "PY_EXC: except Exception: ... (ellipsis swallowed)", r, lang,
                    "try:\n    do_something()\nexcept Exception:\n    ...\n", 1)

    # Negative
    runner.run_case("negative", "PY_EXC: specific exception except ValueError: pass", r, lang,
                    "try:\n    do_something()\nexcept ValueError:\n    pass\n", 0)
    runner.run_case("negative", "PY_EXC: specific KeyError / FileNotFoundError", r, lang,
                    "try:\n    do_something()\nexcept (KeyError, FileNotFoundError):\n    pass\n", 0)
    runner.run_case("negative", "PY_EXC: logged exception with logger.error", r, lang,
                    "try:\n    do_something()\nexcept Exception as e:\n    logger.error(e)\n", 0)
    runner.run_case("negative", "PY_EXC: reraised exception with raise", r, lang,
                    "try:\n    do_something()\nexcept Exception:\n    raise\n", 0)
    runner.run_case("negative", "PY_EXC: reraised custom exception raise MyError(e)", r, lang,
                    "try:\n    do_something()\nexcept Exception as e:\n    raise MyError(e)\n", 0)
    runner.run_case("negative", "PY_EXC: fallback return default_value", r, lang,
                    "def get_data():\n    try:\n        return fetch()\n    except Exception:\n        return []\n", 0)

    # Edge & Adversarial
    runner.run_case("edge_negative", "PY_EXC: print logging exception", r, lang,
                    "try:\n    do_something()\nexcept Exception as e:\n    print(f'Error: {e}')\n", 0)
    runner.run_case("adversarial_positive", "PY_EXC: nested try-except with swallowed inner Exception", r, lang,
                    "try:\n    try:\n        work()\n    except Exception:\n        pass\nexcept ValueError:\n    handle()\n", 1)

    # =========================================================================
    # 3. PY_MUT_001 (Python Mutable Default Argument)
    # =========================================================================
    r = "PY_MUT_001"
    lang = "Python"
    # Positive
    runner.run_case("positive", "PY_MUT: list default def f(x=[])", r, lang,
                    "def f(x=[]):\n    x.append(1)\n", 1)
    runner.run_case("positive", "PY_MUT: dict default def f(x={})", r, lang,
                    "def f(x={}):\n    pass\n", 1)
    runner.run_case("positive", "PY_MUT: set() call default def f(x=set())", r, lang,
                    "def f(x=set()):\n    pass\n", 1)
    runner.run_case("positive", "PY_MUT: aliased global list def f(x=GLOBAL_LIST)", r, lang,
                    "DEFAULT_ITEMS = []\ndef f(x=DEFAULT_ITEMS):\n    pass\n", 1)

    # Negative
    runner.run_case("negative", "PY_MUT: safe None default def f(x=None)", r, lang,
                    "def f(x=None):\n    if x is None:\n        x = []\n", 0)
    runner.run_case("negative", "PY_MUT: immutable tuple default def f(x=())", r, lang,
                    "def f(x=()):\n    pass\n", 0)
    runner.run_case("negative", "PY_MUT: immutable int/string default def f(x=0, y='init')", r, lang,
                    "def f(x=0, y='init'):\n    pass\n", 0)
    runner.run_case("negative", "PY_MUT: variable reassigned to immutable before func def", r, lang,
                    "a = []\na = 1\ndef f(x=a):\n    pass\n", 0)

    # Edge & Adversarial
    runner.run_case("edge_positive", "PY_MUT: inside nested lambda or method", r, lang,
                    "class Service:\n    def execute(self, opts={}):\n        pass\n", 1)
    runner.run_case("adversarial_positive", "PY_MUT: 3-step alias chain a=[]; b=a; c=b; def f(x=c)", r, lang,
                    "a = []\nb = a\nc = b\ndef f(x=c):\n    pass\n", 1)

    # =========================================================================
    # 4. PY_RES_001 (Python Unclosed Resource)
    # =========================================================================
    r = "PY_RES_001"
    lang = "Python"
    # Positive
    runner.run_case("positive", "PY_RES: leaked local open()", r, lang,
                    "def read_file(p):\n    f = open(p)\n    data = f.read()\n    return data\n", 1)
    runner.run_case("positive", "PY_RES: conditionally closed resource (MAYBE_OPEN)", r, lang,
                    "def read_file(p, flag):\n    f = open(p)\n    if flag:\n        f.close()\n    return 'done'\n", 1)
    runner.run_case("positive", "PY_RES: bare open() call without variable", r, lang,
                    "def process(p):\n    open(p).read()\n", 1)

    # Negative
    runner.run_case("negative", "PY_RES: managed with with-statement", r, lang,
                    "def read_file(p):\n    with open(p) as f:\n        return f.read()\n", 0)
    runner.run_case("negative", "PY_RES: explicit unconditional close()", r, lang,
                    "def read_file(p):\n    f = open(p)\n    data = f.read()\n    f.close()\n    return data\n", 0)
    runner.run_case("negative", "PY_RES: cleanup inside finally block", r, lang,
                    "def read_file(p):\n    f = open(p)\n    try:\n        return f.read()\n    finally:\n        f.close()\n", 0)
    runner.run_case("negative", "PY_RES: returned open resource (ownership transfer)", r, lang,
                    "def open_handler(p):\n    f = open(p)\n    return f\n", 0)
    runner.run_case("negative", "PY_RES: direct return open(p)", r, lang,
                    "def get_stream(p):\n    return open(p)\n", 0)

    # Edge & Adversarial
    runner.run_case("adversarial_negative", "PY_RES: io.open managed in with", r, lang,
                    "import io\ndef read_f(p):\n    with io.open(p) as f:\n        return f.read()\n", 0)

    # =========================================================================
    # 5. PY_ASS_001 (Python Assert in Production Code)
    # =========================================================================
    r = "PY_ASS_001"
    lang = "Python"
    # Positive
    runner.run_case("positive", "PY_ASS: assert in production function", r, lang,
                    "def validate(user):\n    assert user.is_authenticated\n", 1,
                    file_path="src/auth_service.py")
    runner.run_case("positive", "PY_ASS: assert with custom message", r, lang,
                    "def transfer(amount):\n    assert amount > 0, 'Amount must be positive'\n", 1,
                    file_path="src/payment.py")

    # Negative
    runner.run_case("negative", "PY_ASS: assert in test file is allowed", r, lang,
                    "def test_auth():\n    assert 1 == 1\n", 0,
                    file_path="tests/test_auth.py")
    runner.run_case("negative", "PY_ASS: internal invariant isinstance check", r, lang,
                    "def f(x):\n    assert isinstance(x, int)\n", 0,
                    file_path="src/types.py")
    runner.run_case("negative", "PY_ASS: internal invariant cls is not None", r, lang,
                    "class Meta:\n    def hook(cls):\n        assert cls is not None\n", 0,
                    file_path="src/meta.py")

    # Edge & Adversarial
    runner.run_case("edge_positive", "PY_ASS: security token assert has high severity/confidence", r, lang,
                    "def check_access(token):\n    assert token is not None\n", 1,
                    file_path="src/api.py",
                    validator=lambda issues: (issues[0].get("confidence") == "high", "Expected high confidence for security keyword"))

    # =========================================================================
    # 6. PY_EVAL_001 (Python Eval/Exec Usage)
    # =========================================================================
    r = "PY_EVAL_001"
    lang = "Python"
    # Positive
    runner.run_case("positive", "PY_EVAL: eval(user_input)", r, lang,
                    "def run(user_input):\n    return eval(user_input)\n", 1)
    runner.run_case("positive", "PY_EVAL: exec(dynamic_code)", r, lang,
                    "def run(code):\n    exec(code)\n", 1)
    runner.run_case("positive", "PY_EVAL: eval with formatted dynamic string", r, lang,
                    "def run(param):\n    eval(f'obj.{param}')\n", 1)

    # Negative
    runner.run_case("negative", "PY_EVAL: literal constant eval('1 + 1')", r, lang,
                    "val = eval('1 + 1')\n", 0)
    runner.run_case("negative", "PY_EVAL: literal dictionary eval('{\"a\": 1}')", r, lang,
                    "val = eval('{\"a\": 1}')\n", 0)

    # Edge & Adversarial
    runner.run_case("adversarial_positive", "PY_EVAL: eval inside class method with request arg", r, lang,
                    "class Handler:\n    def process(self, request):\n        return eval(request.body)\n", 1)

    # =========================================================================
    # 7. PY_NONE_001 (Python None Comparison)
    # =========================================================================
    r = "PY_NONE_001"
    lang = "Python"
    # Positive
    runner.run_case("positive", "PY_NONE: x == None", r, lang,
                    "if x == None:\n    pass\n", 1)
    runner.run_case("positive", "PY_NONE: x != None", r, lang,
                    "if x != None:\n    pass\n", 1)
    runner.run_case("positive", "PY_NONE: None == x (reversed)", r, lang,
                    "if None == x:\n    pass\n", 1)
    runner.run_case("positive", "PY_NONE: None != x (reversed)", r, lang,
                    "if None != x:\n    pass\n", 1)

    # Negative
    runner.run_case("negative", "PY_NONE: idiomatic x is None", r, lang,
                    "if x is None:\n    pass\n", 0)
    runner.run_case("negative", "PY_NONE: idiomatic x is not None", r, lang,
                    "if x is not None:\n    pass\n", 0)
    runner.run_case("negative", "PY_NONE: regular equality comparison x == y", r, lang,
                    "if x == y:\n    pass\n", 0)

    # Edge & Adversarial
    runner.run_case("edge_positive", "PY_NONE: multiple None comparisons in compound boolean", r, lang,
                    "if a == None and b != None:\n    pass\n", 2)

    # =========================================================================
    # 8. PY_UNREACH_001 (Python Unreachable Code)
    # =========================================================================
    r = "PY_UNREACH_001"
    lang = "Python"
    # Positive
    runner.run_case("positive", "PY_UNREACH: dead code after return", r, lang,
                    "def f(x):\n    return x\n    print('dead')\n", 1)
    runner.run_case("positive", "PY_UNREACH: dead code after raise", r, lang,
                    "def f():\n    raise ValueError('error')\n    cleanup()\n", 1)
    runner.run_case("positive", "PY_UNREACH: dead code after exit()", r, lang,
                    "def f():\n    sys.exit(1)\n    return 0\n", 1)

    # Negative
    runner.run_case("negative", "PY_UNREACH: reachable conditional return", r, lang,
                    "def f(x):\n    if x > 0:\n        return x\n    return -x\n", 0)
    runner.run_case("negative", "PY_UNREACH: statements inside branch", r, lang,
                    "def f(x):\n    if x:\n        do_a()\n    else:\n        do_b()\n    return 1\n", 0)

    # Edge & Adversarial
    runner.run_case("edge_positive", "PY_UNREACH: dead code after both if/else branches return", r, lang,
                    "def f(x):\n    if x:\n        return 1\n    else:\n        return 2\n    print('dead')\n", 1)

    # =========================================================================
    # 9. PY_CONSTCOND_001 (Python Constant Condition)
    # =========================================================================
    r = "PY_CONSTCOND_001"
    lang = "Python"
    # Positive
    runner.run_case("positive", "PY_CONSTCOND: if True:", r, lang,
                    "if True:\n    do_something()\n", 1)
    runner.run_case("positive", "PY_CONSTCOND: if False:", r, lang,
                    "if False:\n    never_run()\n", 1)
    runner.run_case("positive", "PY_CONSTCOND: while False:", r, lang,
                    "while False:\n    never_run()\n", 1)
    runner.run_case("positive", "PY_CONSTCOND: constant arithmetic if 1 == 2:", r, lang,
                    "if 1 == 2:\n    never_run()\n", 1)

    # Negative
    runner.run_case("negative", "PY_CONSTCOND: idiom if __name__ == '__main__':", r, lang,
                    "if __name__ == '__main__':\n    main()\n", 0)
    runner.run_case("negative", "PY_CONSTCOND: idiom if TYPE_CHECKING:", r, lang,
                    "if TYPE_CHECKING:\n    from typing import List\n", 0)
    runner.run_case("negative", "PY_CONSTCOND: intentional loop while True:", r, lang,
                    "while True:\n    if check(): break\n", 0)
    runner.run_case("negative", "PY_CONSTCOND: dynamic condition if x > 10:", r, lang,
                    "if x > 10:\n    process()\n", 0)

    # Edge & Adversarial
    runner.run_case("adversarial_positive", "PY_CONSTCOND: constant folded boolean if 10 > 2 and 5 < 3:", r, lang,
                    "if 10 > 2 and 5 < 3:\n    pass\n", 1)

    # =========================================================================
    # 10. JS_DIV_001 (JavaScript Division by Zero)
    # =========================================================================
    r = "JS_DIV_001"
    lang = "JavaScript"
    # Positive
    runner.run_case("positive", "JS_DIV: simple x / 0", r, lang,
                    "const ans = 10 / 0;\n", 1)
    runner.run_case("positive", "JS_DIV: modulo by zero x % 0", r, lang,
                    "const ans = 10 % 0;\n", 1)
    runner.run_case("positive", "JS_DIV: variable divisor const d = 0; 10 / d", r, lang,
                    "const d = 0;\nconst ans = 10 / d;\n", 1)
    runner.run_case("positive", "JS_DIV: negative zero 10 / -0", r, lang,
                    "const ans = 10 / -0;\n", 1)

    # Negative
    runner.run_case("negative", "JS_DIV: safe division 10 / 2", r, lang,
                    "const ans = 10 / 2;\n", 0)
    runner.run_case("negative", "JS_DIV: intentional Infinity constant const INF = 1 / 0;", r, lang,
                    "const INF = 1 / 0;\n", 0)
    runner.run_case("negative", "JS_DIV: intentional NEG_INFINITY = -1 / 0;", r, lang,
                    "const NEG_INF = -1 / 0;\n", 0)
    runner.run_case("negative", "JS_DIV: logical fallback divisor 10 / (d || 1)", r, lang,
                    "const ans = 10 / (d || 1);\n", 0)
    runner.run_case("negative", "JS_DIV: nullish coalescing fallback 10 / (d ?? 1)", r, lang,
                    "const ans = 10 / (d ?? 1);\n", 0)
    runner.run_case("negative", "JS_DIV: dynamic unknown divisor a / b", r, lang,
                    "function calc(a, b) { return a / b; }\n", 0)

    # Edge & Adversarial
    runner.run_case("edge_positive", "JS_DIV: constant folded zero 10 / (5 - 5)", r, lang,
                    "const ans = 10 / (5 - 5);\n", 1)
    runner.run_case("edge_negative", "JS_DIV: guarded division if (d !== 0) 10 / d", r, lang,
                    "if (d !== 0) { const ans = 10 / d; }\n", 0)

    # =========================================================================
    # 11. JS_EQ_001 (JavaScript Loose Equality)
    # =========================================================================
    r = "JS_EQ_001"
    lang = "JavaScript"
    # Positive
    runner.run_case("positive", "JS_EQ: loose equality a == b", r, lang,
                    "if (a == b) { doSomething(); }\n", 1)
    runner.run_case("positive", "JS_EQ: loose inequality a != b", r, lang,
                    "if (a != b) { doSomething(); }\n", 1)
    runner.run_case("positive", "JS_EQ: string literal comparison a == 'hello'", r, lang,
                    "if (a == 'hello') { doSomething(); }\n", 1)

    # Negative
    runner.run_case("negative", "JS_EQ: strict equality a === b", r, lang,
                    "if (a === b) { doSomething(); }\n", 0)
    runner.run_case("negative", "JS_EQ: strict inequality a !== b", r, lang,
                    "if (a !== b) { doSomething(); }\n", 0)
    runner.run_case("negative", "JS_EQ: idiom a == null (nullish check)", r, lang,
                    "if (a == null) { doSomething(); }\n", 0)
    runner.run_case("negative", "JS_EQ: idiom null == a (reversed nullish check)", r, lang,
                    "if (null == a) { doSomething(); }\n", 0)
    runner.run_case("negative", "JS_EQ: idiom typeof a == 'string'", r, lang,
                    "if (typeof a == 'string') { doSomething(); }\n", 0)

    # Edge & Adversarial
    runner.run_case("adversarial_positive", "JS_EQ: loose comparison with number literal a == 0", r, lang,
                    "if (a == 0) { doSomething(); }\n", 1)

    # =========================================================================
    # 12. JS_AWA_001 (JavaScript Await in Loop)
    # =========================================================================
    r = "JS_AWA_001"
    lang = "JavaScript"
    # Positive
    runner.run_case("positive", "JS_AWA: await in for loop", r, lang,
                    "async function run(items) {\n    for (let i = 0; i < items.length; i++) {\n        await processItem(items[i]);\n    }\n}\n", 1)
    runner.run_case("positive", "JS_AWA: await in for..of loop", r, lang,
                    "async function run(items) {\n    for (const item of items) {\n        await processItem(item);\n    }\n}\n", 1)
    runner.run_case("positive", "JS_AWA: await in while loop", r, lang,
                    "async function run(items) {\n    while (hasWork()) {\n        await doWork();\n    }\n}\n", 1)

    # Negative
    runner.run_case("negative", "JS_AWA: for await of loop is intentional streaming", r, lang,
                    "async function run(stream) {\n    for await (const chunk of stream) {\n        consume(chunk);\n    }\n}\n", 0)
    runner.run_case("negative", "JS_AWA: intentional delay await sleep(100)", r, lang,
                    "async function poll() {\n    while (true) {\n        await sleep(100);\n    }\n}\n", 0)
    runner.run_case("negative", "JS_AWA: browser automation await page.click()", r, lang,
                    "async function run(elements) {\n    for (const el of elements) {\n        await page.click(el);\n    }\n}\n", 0)
    runner.run_case("negative", "JS_AWA: database transaction await tx.query()", r, lang,
                    "async function run(records) {\n    for (const r of records) {\n        await tx.query('INSERT', r);\n    }\n}\n", 0)
    runner.run_case("negative", "JS_AWA: pagination cursor = await fetchNextPage(cursor)", r, lang,
                    "async function fetchAll() {\n    let cursor = null;\n    while (cursor) {\n        cursor = await fetchNext(cursor);\n    }\n}\n", 0)

    # Edge & Adversarial
    runner.run_case("adversarial_positive", "JS_AWA: loop with variable named result but independent tasks", r, lang,
                    "async function run(items) {\n    for (let i = 0; i < items.length; i++) {\n        const result = await fetchItem(items[i]);\n    }\n}\n", 1)

    # =========================================================================
    # 13. JS_EVAL_001 (JavaScript Eval Usage)
    # =========================================================================
    r = "JS_EVAL_001"
    lang = "JavaScript"
    # Positive
    runner.run_case("positive", "JS_EVAL: dynamic eval(userInput)", r, lang,
                    "function execUser(userInput) { return eval(userInput); }\n", 1)
    runner.run_case("positive", "JS_EVAL: window.eval(dynamicCode)", r, lang,
                    "function execWindow(code) { window.eval(code); }\n", 1)
    runner.run_case("positive", "JS_EVAL: globalThis.eval(payload)", r, lang,
                    "function execGlobal(payload) { globalThis.eval(payload); }\n", 1)

    # Negative
    runner.run_case("negative", "JS_EVAL: static literal eval('2 + 2')", r, lang,
                    "const res = eval('2 + 2');\n", 0)

    # Edge & Adversarial
    runner.run_case("adversarial_positive", "JS_EVAL: dynamic constructed string in eval", r, lang,
                    "function run(mod) { eval('require(\"' + mod + '\")'); }\n", 1)

    # =========================================================================
    # 14. JS_UNREACH_001 (JavaScript Unreachable Code)
    # =========================================================================
    r = "JS_UNREACH_001"
    lang = "JavaScript"
    # Positive
    runner.run_case("positive", "JS_UNREACH: statement after return", r, lang,
                    "function f(x) {\n    return x;\n    console.log('dead');\n}\n", 1)
    runner.run_case("positive", "JS_UNREACH: statement after throw", r, lang,
                    "function validate(x) {\n    throw new Error('Invalid');\n    return false;\n}\n", 1)

    # Negative
    runner.run_case("negative", "JS_UNREACH: reachable conditional return", r, lang,
                    "function f(x) {\n    if (x > 0) return x;\n    return 0;\n}\n", 0)

    # Edge & Adversarial
    runner.run_case("edge_positive", "JS_UNREACH: dead code after process.exit()", r, lang,
                    "function fatal() {\n    process.exit(1);\n    cleanup();\n}\n", 1)

    # =========================================================================
    # 15. JS_CONSTCOND_001 (JavaScript Constant Condition)
    # =========================================================================
    r = "JS_CONSTCOND_001"
    lang = "JavaScript"
    # Positive
    runner.run_case("positive", "JS_CONSTCOND: if (true)", r, lang,
                    "if (true) { doSomething(); }\n", 1)
    runner.run_case("positive", "JS_CONSTCOND: if (false)", r, lang,
                    "if (false) { neverRun(); }\n", 1)
    runner.run_case("positive", "JS_CONSTCOND: while (false)", r, lang,
                    "while (false) { neverRun(); }\n", 1)
    runner.run_case("positive", "JS_CONSTCOND: constant comparison if (1 === 2)", r, lang,
                    "if (1 === 2) { neverRun(); }\n", 1)

    # Negative
    runner.run_case("negative", "JS_CONSTCOND: dynamic condition if (isValid && count > 0)", r, lang,
                    "if (isValid && count > 0) { process(); }\n", 0)

    # Edge & Adversarial
    runner.run_case("adversarial_positive", "JS_CONSTCOND: constant arithmetic if (10 * 0 === 0)", r, lang,
                    "if (10 * 0 === 0) { pass(); }\n", 1)

    # =========================================================================
    # 16. JS_PROMISE_001 (JavaScript Unhandled Promise)
    # =========================================================================
    r = "JS_PROMISE_001"
    lang = "JavaScript"
    # Positive
    runner.run_case("positive", "JS_PROMISE: bare unhandled fetch()", r, lang,
                    "function trigger() {\n    fetch('/api/data');\n}\n", 1)
    runner.run_case("positive", "JS_PROMISE: unhandled axios.post()", r, lang,
                    "function send(data) {\n    axios.post('/submit', data);\n}\n", 1)
    runner.run_case("positive", "JS_PROMISE: unhandled fs.promises.writeFile()", r, lang,
                    "function write(data) {\n    fs.promises.writeFile('out.txt', data);\n}\n", 1)

    # Negative
    runner.run_case("negative", "JS_PROMISE: awaited fetch()", r, lang,
                    "async function trigger() {\n    await fetch('/api/data');\n}\n", 0)
    runner.run_case("negative", "JS_PROMISE: chained .catch() fetch()", r, lang,
                    "function trigger() {\n    fetch('/api/data').catch(err => console.error(err));\n}\n", 0)
    runner.run_case("negative", "JS_PROMISE: returned fetch()", r, lang,
                    "function trigger() {\n    return fetch('/api/data');\n}\n", 0)
    runner.run_case("negative", "JS_PROMISE: assigned to variable const p = fetch()", r, lang,
                    "function trigger() {\n    const p = fetch('/api/data');\n}\n", 0)

    # Edge & Adversarial
    runner.run_case("edge_negative", "JS_PROMISE: custom sendTelemetry() not a recognized unhandled promise API", r, lang,
                    "function log() {\n    sendTelemetry();\n}\n", 0)

    # =========================================================================
    # 17. JAVA_DIV_001 (Java Division by Zero)
    # =========================================================================
    r = "JAVA_DIV_001"
    lang = "Java"
    # Positive
    runner.run_case("positive", "JAVA_DIV: simple x / 0", r, lang,
                    "public class C { int f(int x) { return x / 0; } }\n", 1)
    runner.run_case("positive", "JAVA_DIV: variable divisor int d = 0; x / d", r, lang,
                    "public class C { int f(int x) { int d = 0; return x / d; } }\n", 1)
    runner.run_case("positive", "JAVA_DIV: constant folded zero 10 / (5 - 5)", r, lang,
                    "public class C { int f() { return 10 / (5 - 5); } }\n", 1)

    # Negative
    runner.run_case("negative", "JAVA_DIV: safe division x / 2", r, lang,
                    "public class C { int f(int x) { return x / 2; } }\n", 0)
    runner.run_case("negative", "JAVA_DIV: hex literal non-zero 10 / 0xFF", r, lang,
                    "public class C { int f() { return 10 / 0xFF; } }\n", 0)
    runner.run_case("negative", "JAVA_DIV: dynamic unknown divisor a / b", r, lang,
                    "public class C { int f(int a, int b) { return a / b; } }\n", 0)
    runner.run_case("negative", "JAVA_DIV: guarded by if (d != 0) x / d", r, lang,
                    "public class C { int f(int x, int d) { if (d != 0) { return x / d; } return 0; } }\n", 0)

    # Edge & Adversarial
    runner.run_case("edge_positive", "JAVA_DIV: modulo by zero x % 0", r, lang,
                    "public class C { int f(int x) { return x % 0; } }\n", 1)

    # =========================================================================
    # 18. JAVA_EQ_001 (Java String Equality)
    # =========================================================================
    r = "JAVA_EQ_001"
    lang = "Java"
    # Positive
    runner.run_case("positive", "JAVA_EQ: String variable == string literal", r, lang,
                    "public class C { boolean f(String s) { return s == \"test\"; } }\n", 1)
    runner.run_case("positive", "JAVA_EQ: String parameter == String parameter", r, lang,
                    "public class C { boolean f(String a, String b) { return a == b; } }\n", 1)
    runner.run_case("positive", "JAVA_EQ: java.lang.String == other", r, lang,
                    "public class C { boolean f(java.lang.String a, String b) { return a != b; } }\n", 1)

    # Negative
    runner.run_case("negative", "JAVA_EQ: value equality .equals()", r, lang,
                    "public class C { boolean f(String s) { return s.equals(\"test\"); } }\n", 0)
    runner.run_case("negative", "JAVA_EQ: null comparison s == null", r, lang,
                    "public class C { boolean f(String s) { return s == null; } }\n", 0)
    runner.run_case("negative", "JAVA_EQ: primitive integer comparison a == b", r, lang,
                    "public class C { boolean f(int a, int b) { return a == b; } }\n", 0)
    runner.run_case("negative", "JAVA_EQ: class literal comparison type == String.class", r, lang,
                    "public class C { boolean f(Class<?> type) { return type == String.class; } }\n", 0)
    runner.run_case("negative", "JAVA_EQ: enum constant comparison state == State.ACTIVE", r, lang,
                    "public class C { boolean f(State state) { return state == State.ACTIVE; } }\n", 0)

    # Edge & Adversarial
    runner.run_case("adversarial_positive", "JAVA_EQ: String-returning method == literal", r, lang,
                    "public class C { boolean f(User u) { return u.getName() == \"admin\"; } }\n", 1)

    # =========================================================================
    # 19. JAVA_EXC_001 (Java Empty Catch Block)
    # =========================================================================
    r = "JAVA_EXC_001"
    lang = "Java"
    # Positive
    runner.run_case("positive", "JAVA_EXC: completely empty catch block", r, lang,
                    "public class C { void f() { try { doWork(); } catch (Exception e) {} } }\n", 1)
    runner.run_case("positive", "JAVA_EXC: catch block with only empty semicolons", r, lang,
                    "public class C { void f() { try { doWork(); } catch (Exception e) { ; } } }\n", 1)

    # Negative
    runner.run_case("negative", "JAVA_EXC: intentional parameter name catch (Exception ignored)", r, lang,
                    "public class C { void f() { try { doWork(); } catch (Exception ignored) {} } }\n", 0)
    runner.run_case("negative", "JAVA_EXC: intentional comment // expected", r, lang,
                    "public class C { void f() { try { doWork(); } catch (Exception e) { // expected\n } } }\n", 0)
    runner.run_case("negative", "JAVA_EXC: rethrowing catch throw e", r, lang,
                    "public class C { void f() throws Exception { try { doWork(); } catch (Exception e) { throw e; } } }\n", 0)
    runner.run_case("negative", "JAVA_EXC: logged catch log.error(e)", r, lang,
                    "public class C { void f() { try { doWork(); } catch (Exception e) { logger.error(\"err\", e); } } }\n", 0)

    # Edge & Adversarial
    runner.run_case("adversarial_positive", "JAVA_EXC: empty catch in nested try block", r, lang,
                    "public class C { void f() { try { try { work(); } catch (IOException e) {} } catch (Exception e) { log.error(e); } } }\n", 1)

    # =========================================================================
    # 20. JAVA_LOOP_001 (Java Infinite Loop)
    # =========================================================================
    r = "JAVA_LOOP_001"
    lang = "Java"
    # Positive
    runner.run_case("positive", "JAVA_LOOP: while (true) with no break", r, lang,
                    "public class C { void f() { while (true) { doSomething(); } } }\n", 1)
    runner.run_case("positive", "JAVA_LOOP: for (;;) with no break", r, lang,
                    "public class C { void f() { for (;;) { doSomething(); } } }\n", 1)
    runner.run_case("positive", "JAVA_LOOP: break guarded by static false `if (false) break;`", r, lang,
                    "public class C { void f() { while (true) { if (false) break; } } }\n", 1)
    runner.run_case("positive", "JAVA_LOOP: diverging counter x-- while waiting for x > 10", r, lang,
                    "public class C { void f() { int x = 0; while (true) { if (x > 10) break; x--; } } }\n", 1)

    # Negative
    runner.run_case("negative", "JAVA_LOOP: unconditional break in loop", r, lang,
                    "public class C { void f() { while (true) { break; } } }\n", 0)
    runner.run_case("negative", "JAVA_LOOP: dynamic condition break `if (cond) break;`", r, lang,
                    "public class C { void f(boolean cond) { while (true) { if (cond) break; } } }\n", 0)
    runner.run_case("negative", "JAVA_LOOP: progressing counter x++ towards x >= 10", r, lang,
                    "public class C { void f() { int x = 0; while (true) { if (x >= 10) break; x++; } } }\n", 0)
    runner.run_case("negative", "JAVA_LOOP: loop exits via return", r, lang,
                    "public class C { int f() { while (true) { return 42; } } }\n", 0)
    runner.run_case("negative", "JAVA_LOOP: labeled break exiting outer loop", r, lang,
                    "public class C { void f() { outer: while (true) { while (true) { break outer; } } } }\n", 0)

    # Edge & Adversarial
    runner.run_case("adversarial_positive", "JAVA_LOOP: break inside nested switch only exits switch", r, lang,
                    "public class C { void f(int x) { while (true) { switch(x) { case 1: break; } } } }\n", 1)

    # =========================================================================
    # 21. JAVA_RES_001 (Java Unclosed Resource)
    # =========================================================================
    r = "JAVA_RES_001"
    lang = "Java"
    # Positive
    runner.run_case("positive", "JAVA_RES: leaked FileInputStream without close", r, lang,
                    "public class C { void f(File file) throws Exception { FileInputStream in = new FileInputStream(file); in.read(); } }\n", 1)
    runner.run_case("positive", "JAVA_RES: conditionally closed resource", r, lang,
                    "public class C { void f(File file, boolean flag) throws Exception { FileInputStream in = new FileInputStream(file); if (flag) in.close(); } }\n", 1)

    # Negative
    runner.run_case("negative", "JAVA_RES: managed by try-with-resources", r, lang,
                    "public class C { void f(File file) throws Exception { try (FileInputStream in = new FileInputStream(file)) { in.read(); } } }\n", 0)
    runner.run_case("negative", "JAVA_RES: explicit unconditional close()", r, lang,
                    "public class C { void f(File file) throws Exception { FileInputStream in = new FileInputStream(file); in.read(); in.close(); } }\n", 0)
    runner.run_case("negative", "JAVA_RES: closed in finally block", r, lang,
                    "public class C { void f(File file) throws Exception { FileInputStream in = new FileInputStream(file); try { in.read(); } finally { in.close(); } } }\n", 0)
    runner.run_case("negative", "JAVA_RES: returned resource (ownership transfer)", r, lang,
                    "public class C { FileInputStream f(File file) throws Exception { FileInputStream in = new FileInputStream(file); return in; } }\n", 0)

    # Edge & Adversarial
    runner.run_case("edge_positive", "JAVA_RES: leaked Socket connection", r, lang,
                    "public class C { void f(String host, int port) throws Exception { Socket s = new Socket(host, port); s.getInputStream(); } }\n", 1)

    # =========================================================================
    # 22. JAVA_NULL_001 (Java Null Dereference)
    # =========================================================================
    r = "JAVA_NULL_001"
    lang = "Java"
    # Positive
    runner.run_case("positive", "JAVA_NULL: explicit null method invocation String s = null; s.length()", r, lang,
                    "public class C { void f() { String s = null; s.length(); } }\n", 1)
    runner.run_case("positive", "JAVA_NULL: explicit null field access MyObj obj = null; obj.value", r, lang,
                    "public class C { void f() { MyObj obj = null; int x = obj.value; } }\n", 1)

    # Negative
    runner.run_case("negative", "JAVA_NULL: non-null variable String s = 'hello'; s.length()", r, lang,
                    "public class C { void f() { String s = \"hello\"; s.length(); } }\n", 0)
    runner.run_case("negative", "JAVA_NULL: guarded by if (s != null) s.length()", r, lang,
                    "public class C { void f(String s) { if (s != null) { s.length(); } } }\n", 0)
    runner.run_case("negative", "JAVA_NULL: early return guard if (s == null) return; s.length()", r, lang,
                    "public class C { void f(String s) { if (s == null) return; s.length(); } }\n", 0)
    runner.run_case("negative", "JAVA_NULL: dynamic method return String s = getValue(); s.length()", r, lang,
                    "public class C { void f() { String s = getValue(); s.length(); } }\n", 0)

    # Edge & Adversarial
    runner.run_case("edge_negative", "JAVA_NULL: reassigned from null to non-null s = null; s = 'safe'; s.length()", r, lang,
                    "public class C { void f() { String s = null; s = \"safe\"; s.length(); } }\n", 0)

    # =========================================================================
    # 23. JAVA_UNREACH_001 (Java Unreachable Code)
    # =========================================================================
    r = "JAVA_UNREACH_001"
    lang = "Java"
    # Positive
    runner.run_case("positive", "JAVA_UNREACH: statement after return", r, lang,
                    "public class C { int f(int x) { return x * 2; System.out.println(\"dead\"); } }\n", 1)
    runner.run_case("positive", "JAVA_UNREACH: statement after throw", r, lang,
                    "public class C { void f() { throw new RuntimeException(); cleanup(); } }\n", 1)

    # Negative
    runner.run_case("negative", "JAVA_UNREACH: reachable conditional return", r, lang,
                    "public class C { int f(int x) { if (x > 0) return x; return 0; } }\n", 0)

    # Edge & Adversarial
    runner.run_case("edge_positive", "JAVA_UNREACH: dead code after System.exit(0)", r, lang,
                    "public class C { void f() { System.exit(0); doWork(); } }\n", 1)

    # =========================================================================
    # 24. JAVA_CONSTCOND_001 (Java Constant Condition)
    # =========================================================================
    r = "JAVA_CONSTCOND_001"
    lang = "Java"
    # Positive
    runner.run_case("positive", "JAVA_CONSTCOND: if (true)", r, lang,
                    "public class C { void f() { if (true) { doAction(); } } }\n", 1)
    runner.run_case("positive", "JAVA_CONSTCOND: if (false)", r, lang,
                    "public class C { void f() { if (false) { doAction(); } } }\n", 1)
    runner.run_case("positive", "JAVA_CONSTCOND: constant comparison if (1 == 2)", r, lang,
                    "public class C { void f() { if (1 == 2) { doAction(); } } }\n", 1)

    # Negative
    runner.run_case("negative", "JAVA_CONSTCOND: dynamic condition if (flag)", r, lang,
                    "public class C { void f(boolean flag) { if (flag) { doAction(); } } }\n", 0)

    # Edge & Adversarial
    runner.run_case("adversarial_positive", "JAVA_CONSTCOND: constant folded if (10 + 5 == 15)", r, lang,
                    "public class C { void f() { if (10 + 5 == 15) { pass(); } } }\n", 1)


def run_cross_rule_tests(runner: AdversarialAuditRunner):
    """Audits cross-rule co-occurrence and deduplication."""
    # Multi-rule Python file
    py_multi_src = """
def process(x=[]):
    try:
        f = open("data.txt")
        ans = 10 / 0
    except Exception:
        pass
    return None
    print("unreachable")
"""
    res_py = runner.analyze_source(py_multi_src, "Python", "src/multi_py.py")
    issues_py = res_py.get("issues", [])
    rule_ids_py = [i["rule_id"] for i in issues_py]

    expected_rules_py = {"PY_MUT_001", "PY_DIV_001", "PY_EXC_001", "PY_UNREACH_001"}
    # Note: open inside try with div-by-zero might be unclosed or try-protected
    print(f"  [Cross-Rule Python] Found rules: {set(rule_ids_py)}")

    # Multi-rule JavaScript file
    js_multi_src = """
async function handler(items) {
    if (true) {
        fetch('/api/v1');
    }
    for (const item of items) {
        await process(item);
    }
    return 1 == 1;
    console.log("dead");
}
"""
    res_js = runner.analyze_source(js_multi_src, "JavaScript", "src/multi_js.js")
    issues_js = res_js.get("issues", [])
    rule_ids_js = [i["rule_id"] for i in issues_js]
    print(f"  [Cross-Rule JavaScript] Found rules: {set(rule_ids_js)}")

    # Multi-rule Java file
    java_multi_src = """
public class MultiTest {
    public void execute(String name) {
        if (true) {
            String s = null;
            s.length();
        }
        if (name == "admin") {
            int d = 10 / 0;
        }
        try {
            doWork();
        } catch (Exception e) {}
        return;
        System.out.println("dead");
    }
}
"""
    res_java = runner.analyze_source(java_multi_src, "Java", "src/MultiTest.java")
    issues_java = res_java.get("issues", [])
    rule_ids_java = [i["rule_id"] for i in issues_java]
    print(f"  [Cross-Rule Java] Found rules: {set(rule_ids_java)}")


def run_output_contract_audit(runner: AdversarialAuditRunner) -> Tuple[bool, List[str]]:
    """Validates that all produced issues strictly follow the candidate issue schema."""
    contract_errors = []
    required_fields = {
        "rule_id", "issue_type", "message", "file_path", "line_number", "column",
        "severity", "code_snippet", "evidence", "confidence",
    }
    valid_severities = {"critical", "high", "medium", "low", "info"}
    valid_languages = {"Python", "JavaScript", "Java"}

    total_issues = 0
    for r in runner.results:
        if r.language not in valid_languages:
            contract_errors.append(f"Result {r.name} has invalid language '{r.language}'")
        for issue in r.issues:
            total_issues += 1
            missing = required_fields - set(issue.keys())
            if missing:
                contract_errors.append(f"Issue {issue.get('rule_id')} missing required fields: {missing}")

            if issue.get("severity") not in valid_severities:
                contract_errors.append(f"Issue {issue.get('rule_id')} has invalid severity '{issue.get('severity')}'")

            if not isinstance(issue.get("line_number"), int) or issue["line_number"] < 1:
                contract_errors.append(f"Issue {issue.get('rule_id')} has invalid line_number {issue.get('line_number')}")

            if not isinstance(issue.get("evidence"), dict):
                contract_errors.append(f"Issue {issue.get('rule_id')} evidence is not a dict: {type(issue.get('evidence'))}")

    return len(contract_errors) == 0, contract_errors


def run_performance_audit(runner: AdversarialAuditRunner) -> Dict[str, Any]:
    """Profiles latency and scalability across small, medium, large, and deeply nested ASTs."""
    perf_results = {}

    # 1. Small file (~20 lines)
    small_py = "def f(x):\n    return x + 1\n" * 10
    t0 = time.perf_counter()
    runner.analyze_source(small_py, "Python")
    perf_results["small_file_latency_sec"] = time.perf_counter() - t0

    # 2. Medium file (~300 lines with variables, branches, loops)
    medium_java = "public class PerfMed {\n"
    for i in range(50):
        medium_java += f"    int func{i}(int x) {{ if (x > 0) return x * {i}; return 0; }}\n"
    medium_java += "}\n"
    t0 = time.perf_counter()
    runner.analyze_source(medium_java, "Java")
    perf_results["medium_file_latency_sec"] = time.perf_counter() - t0

    # 3. Large file (~1500 lines)
    large_js = "function big() {\n"
    for i in range(300):
        large_js += f"    const var_{i} = {i};\n    if (var_{i} > 100) {{ console.log(var_{i}); }}\n"
    large_js += "}\n"
    t0 = time.perf_counter()
    runner.analyze_source(large_js, "JavaScript")
    perf_results["large_file_latency_sec"] = time.perf_counter() - t0

    # 4. Deeply nested code (25 nested if blocks)
    nested_py = "def deep_nest(x):\n"
    indent = "    "
    for i in range(25):
        nested_py += f"{indent * (i + 1)}if x > {i}:\n"
    nested_py += f"{indent * 26}return x / 0\n"
    t0 = time.perf_counter()
    runner.analyze_source(nested_py, "Python")
    perf_results["deeply_nested_latency_sec"] = time.perf_counter() - t0

    return perf_results


def main():
    print("=" * 80)
    print(" PHASE 2 ADVERSARIAL QUALITY AUDIT HARNESS — BUGTRACKER STATIC ANALYZER V2")
    print("=" * 80)

    runner = AdversarialAuditRunner()
    print("\n[*] Registering and executing adversarial test matrix for all 24 rules...")
    register_all_tests(runner)

    total_tests = len(runner.results)
    passed_tests = sum(1 for r in runner.results if r.passed)
    failed_tests = total_tests - passed_tests
    total_fp = sum(len(s.false_positives) for s in runner.summaries.values())
    total_fn = sum(len(s.false_negatives) for s in runner.summaries.values())

    print(f"\n[*] Executed {total_tests} adversarial cases across 24 rules.")
    print(f"    Passed: {passed_tests} | Failed: {failed_tests} | False Positives: {total_fp} | False Negatives: {total_fn}")

    # Cross-rule tests
    print("\n[*] Running cross-rule interaction and co-occurrence tests...")
    run_cross_rule_tests(runner)

    # Output contract audit
    print("\n[*] Running output contract schema verification...")
    contract_ok, contract_errs = run_output_contract_audit(runner)
    if contract_ok:
        print("    [PASS] All findings strictly conform to Candidate Issue schema.")
    else:
        print(f"    [FAIL] Schema violations found: {len(contract_errs)}")
        for err in contract_errs[:5]:
            print(f"      - {err}")

    # Performance audit
    print("\n[*] Running performance & stress profiling...")
    perf_data = run_performance_audit(runner)
    for k, v in perf_data.items():
        print(f"    - {k}: {v:.4f}s")

    # Print Per-Rule Matrix
    print("\n" + "=" * 100)
    print(" PER-RULE AUDIT MATRIX (24 RULES)")
    print("=" * 100)
    header = f"| {'#':<2} | {'Rule ID':<18} | {'Lang':<10} | {'Pos':<5} | {'Neg':<5} | {'Edge':<5} | {'Adv':<5} | {'FP':<3} | {'FN':<3} | {'Status':<18} |"
    print(header)
    print("|" + "-" * 4 + "|" + "-" * 20 + "|" + "-" * 12 + "|" + "-" * 7 + "|" + "-" * 7 + "|" + "-" * 7 + "|" + "-" * 7 + "|" + "-" * 5 + "|" + "-" * 5 + "|" + "-" * 20 + "|")

    idx = 1
    for rule_id, summary in runner.summaries.items():
        pos_str = f"{summary.positive_passed}/{summary.positive_total}"
        neg_str = f"{summary.negative_passed}/{summary.negative_total}"
        edge_str = f"{summary.edge_passed}/{summary.edge_total}"
        adv_str = f"{summary.adversarial_passed}/{summary.adversarial_total}"
        fp_count = len(summary.false_positives)
        fn_count = len(summary.false_negatives)
        status = summary.status
        print(f"| {idx:<2} | {rule_id:<18} | {summary.language:<10} | {pos_str:<5} | {neg_str:<5} | {edge_str:<5} | {adv_str:<5} | {fp_count:<3} | {fn_count:<3} | {status:<18} |")
        idx += 1

    print("=" * 100)

    # Print Defects Details
    if total_fp > 0 or total_fn > 0 or failed_tests > 0:
        print("\n" + "=" * 80)
        print(" DETECTED DEFECTS & DISCREPANCIES")
        print("=" * 80)
        defect_idx = 1
        for res in runner.results:
            if not res.passed:
                print(f"\nFinding #{defect_idx}:")
                print(f"Rule: {res.rule_id} ({res.language})")
                print(f"Type: {'FALSE POSITIVE' if res.is_false_positive else ('FALSE NEGATIVE' if res.is_false_negative else 'LOGIC ERROR')}")
                print(f"Test Case: {res.name}")
                print(f"Failure Reason: {res.failure_reason}")
                print("Code:\n" + res.source_code.strip())
                defect_idx += 1


if __name__ == "__main__":
    main()
