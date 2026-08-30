"""
JAVA_EXC_001 — Empty catch block (Java)
----------------------------------------
Detects `catch_clause` blocks whose body contains no meaningful statements,
silently swallowing exceptions in production code.

Suppression criteria (provably safe / intentional):
- Intentionally named exception variables: `expected`, `ignored`, `unused`, `_`, `ex_ignored`
- Intentional inline comments inside catch body: `// expected`, `/* ignore */`, `// ignore`, `// intentional`
- Standard JUnit expected exception test patterns (e.g. `try { fail(); } catch (ExpectedException e) {}`)

Confidence calibration:
- HIGH: Broad exception types (`Exception`, `Throwable`, `RuntimeException`) silently swallowed in production code.
- MEDIUM: Narrower checked exception silently swallowed without explanation.
- LOW: Test file catch block or catch followed by immediate fallback return.
"""

import re
from typing import Iterator, List, Optional, Set

from ..base_rule import BaseRule
from ..models import CandidateIssue

_STATEMENT_TYPES: Set[str] = {
    "expression_statement", "return_statement", "throw_statement",
    "local_variable_declaration", "if_statement", "for_statement",
    "while_statement", "do_statement", "try_statement", "block",
    "enhanced_for_statement", "labeled_statement", "switch_statement",
    "synchronized_statement", "assert_statement", "break_statement",
    "continue_statement",
}

_INTENTIONAL_PARAM_NAMES: Set[str] = {
    "expected", "ignored", "unused", "_", "ex_ignored", "e_ignored",
    "expectedexception", "ignore", "donotcare",
}

_INTENTIONAL_COMMENT_RE = re.compile(
    r'(?://|/\*)\s*(?:expected|ignored?|intentional|fallback|do\s+nothing|suppress|no-op)',
    re.IGNORECASE,
)

_BROAD_EXCEPTION_TYPES: Set[str] = {
    "Exception", "Throwable", "RuntimeException", "java.lang.Exception",
    "java.lang.Throwable", "java.lang.RuntimeException",
}


def _extract_catch_param(node: dict) -> tuple[str, str]:
    """Returns (param_name, exception_type)."""
    param = next((c for c in node.get("children", []) if c.get("type") == "catch_formal_parameter"), None)
    if not param:
        return ("e", "Exception")

    param_name = "e"
    ex_type = "Exception"

    for child in param.get("children", []):
        ctype = child.get("type", "")
        if ctype in ("type_identifier", "scoped_type_identifier"):
            ex_type = (child.get("text") or "Exception").strip()
        elif ctype == "identifier":
            param_name = (child.get("text") or "e").strip()

    return (param_name, ex_type)


def _has_intentional_comment(block_node: dict, source_lines: List[str]) -> bool:
    """Check if catch block contains comments indicating intentional swallowing."""
    text = block_node.get("text") or ""
    if _INTENTIONAL_COMMENT_RE.search(text):
        return True

    # Also check source lines in block line range
    start = block_node.get("start", {}).get("line", 0)
    end = block_node.get("end", {}).get("line", start)
    for line_idx in range(start, min(end + 1, len(source_lines))):
        if _INTENTIONAL_COMMENT_RE.search(source_lines[line_idx]):
            return True

    return False


def _is_junit_test_catch(node: dict, parent_map: dict) -> bool:
    """Check if catch is inside a test try { ... fail(); } catch (...) {} pattern."""
    curr = node
    while id(curr) in parent_map:
        curr = parent_map[id(curr)]
        if curr.get("type") == "try_statement":
            try_text = (curr.get("text") or "").lower()
            if "fail(" in try_text or "assert" in try_text:
                return True
        if curr.get("type") == "method_declaration":
            m_text = (curr.get("text") or "").lower()
            if "@test" in m_text or m_text.startswith("public void test"):
                return True
    return False


class JavaEmptyCatch(BaseRule):

    LANGUAGES = ["Java"]

    @property
    def rule_id(self) -> str:
        return "JAVA_EXC_001"

    @property
    def issue_type(self) -> str:
        return "empty_catch_block"

    @property
    def severity(self) -> str:
        return "high"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        parent_map: dict = {}
        self._build_parent_map(ast, parent_map)
        is_test = self._is_test_file(file_path)

        for node in self._walk(ast):
            if node.get("type") != "catch_clause":
                continue

            block = next((c for c in node.get("children", []) if c.get("type") == "block"), None)
            if block is None:
                continue

            statements = [c for c in block.get("children", []) if c.get("type") in _STATEMENT_TYPES]
            if statements:
                continue

            self.record_syntax_match()

            param_name, ex_type = _extract_catch_param(node)

            # 1. Intentional parameter naming (expected, ignored, unused)
            if param_name.lower() in _INTENTIONAL_PARAM_NAMES:
                self.record_suppression(f"intentional_parameter_name_{param_name}")
                continue

            # 2. Intentional comments inside catch block
            if _has_intentional_comment(block, source_lines):
                self.record_suppression("intentional_comment_in_catch")
                continue

            # 3. JUnit test expected exception pattern
            if is_test and _is_junit_test_catch(node, parent_map):
                self.record_suppression("junit_expected_exception_test_pattern")
                continue

            is_broad = ex_type in _BROAD_EXCEPTION_TYPES
            confidence = "high" if is_broad and not is_test else ("low" if is_test else "medium")

            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"Empty catch block silently ignores `{ex_type}` without logging, "
                    f"recovery, or rethrowing."
                ),
                evidence={
                    "exception_type": ex_type,
                    "catch_parameter": param_name,
                    "is_broad_exception": is_broad,
                    "confidence": confidence,
                    "reason": f"Catch block for `{ex_type} {param_name}` contains no statements or documented intent.",
                },
                confidence=confidence,
            )

