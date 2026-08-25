"""
PY_EXC_001 — Python Exception Handling Unit & Boundary Tests
=============================================================
Tests for bare except and overbroad BaseException catches.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.py_bare_except import PythonBareExcept
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, node, leaf,
)


def run_tests() -> bool:
    rule = PythonBareExcept()
    r = RuleTestRunner("PY_EXC_001 — Unit & Boundary Tests")

    def ec(*ch):
        return node("except_clause", "except:", children=list(ch))

    # --- 1. BARE EXCEPT & BASEEXCEPTION (MUST FLAG) ---
    r.must_flag("bare except: (minimal)", rule, module(ec(leaf("except", "except"), leaf(":", ":"))))

    r.must_flag(
        "except BaseException: (direct)",
        rule,
        module(ec(leaf("except", "except"), node("identifier", "BaseException"), leaf(":", ":"))),
    )

    # W09 Regression: BaseException inside tuple
    r.must_flag(
        "except (IOError, BaseException): (tuple with BaseException)",
        rule,
        module(ec(leaf("except", "except"), node("tuple", "(IOError, BaseException)", children=[
            node("identifier", "IOError"), node("identifier", "BaseException")
        ]), leaf(":", ":"))),
    )

    r.must_flag(
        "except (BaseException,): (single-element tuple)",
        rule,
        module(ec(leaf("except", "except"), node("tuple", "(BaseException,)", children=[
            node("identifier", "BaseException")
        ]), leaf(":", ":"))),
    )

    # W10 Regression: except BaseException as e
    r.must_flag(
        "except BaseException as e: (aliased as_pattern)",
        rule,
        module(ec(leaf("except", "except"), node("as_pattern", "BaseException as e", children=[
            node("identifier", "BaseException"), leaf("as", "as"), node("identifier", "e")
        ]), leaf(":", ":"))),
    )

    # --- 2. SAFE / SPECIFIC EXCEPTIONS (MUST NOT FLAG) ---
    r.must_not_flag(
        "except Exception: (standard root)",
        rule,
        module(ec(leaf("except", "except"), node("identifier", "Exception"), leaf(":", ":"))),
    )

    r.must_not_flag(
        "except ValueError: (specific exception)",
        rule,
        module(ec(leaf("except", "except"), node("identifier", "ValueError"), leaf(":", ":"))),
    )

    r.must_not_flag(
        "except (OSError, ValueError): (safe tuple)",
        rule,
        module(ec(leaf("except", "except"), node("tuple", "(OSError, ValueError)", children=[
            node("identifier", "OSError"), node("identifier", "ValueError")
        ]), leaf(":", ":"))),
    )

    r.must_not_flag(
        "except Exception as e: (safe aliased)",
        rule,
        module(ec(leaf("except", "except"), node("as_pattern", "Exception as e", children=[
            node("identifier", "Exception"), leaf("as", "as"), node("identifier", "e")
        ]), leaf(":", ":"))),
    )

    # --- 3. MULTI-EXCEPT TRY BLOCKS ---
    bare = ec(leaf("except", "except"), leaf(":", ":"))
    typed = ec(leaf("except", "except"), node("identifier", "ValueError"), leaf(":", ":"))
    issues = list(rule.analyze(module(bare, typed), "f.py", []))
    if len(issues) == 1:
        r._passes += 1
        print("  OK   [multi-except  ] exactly 1 issue for bare clause in multi-except block")
    else:
        r._failures.append(f"  FAIL [multi-except  ] expected 1 issue, got {len(issues)}")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
