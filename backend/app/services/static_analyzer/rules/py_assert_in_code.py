"""
PY_ASS_001 — assert used in production code (Python)
-----------------------------------------------------
Detects `assert_statement` nodes in production source files.
Python's `-O` (optimized) flag strips all `assert` statements at bytecode compile time,
so relying on `assert` for runtime validation, access control, or authorization
creates severe security and logic vulnerabilities.

Suppression criteria:
- Test and specification files (`test_*.py`, `*_test.py`, `spec_*.py`, `*_spec.py`).
- Internal type-narrowing / structural invariants (e.g. `assert cls is not None`, `assert isinstance(x, T)`).

Confidence calibration:
- HIGH: Security, authorization, authentication, or token assertions (`assert user.is_admin`, `assert token is not None`).
- MEDIUM: General runtime logic assertions.
"""

from __future__ import annotations

import re
from typing import Iterator, List

from ..base_rule import BaseRule
from ..models import CandidateIssue

_SECURITY_AUTH_KEYWORDS = {
    "admin", "auth", "authenticated", "permission", "authorized", "role",
    "token", "secret", "password", "allowed", "valid_user", "is_admin",
}

_INTERNAL_INVARIANT_PATTERNS = [
    re.compile(r'assert\s+(?:cls|self\b|self\._\w+)', re.IGNORECASE),
    re.compile(r'assert\s+isinstance\s*\(', re.IGNORECASE),
    re.compile(r'assert\s+callable\s*\(', re.IGNORECASE),
    re.compile(r'assert\s+hasattr\s*\(', re.IGNORECASE),
    re.compile(r'assert\s+issubclass\s*\(', re.IGNORECASE),
    re.compile(r'assert\s+cls\s+is\s+not\s+None', re.IGNORECASE),
]


def _is_security_or_auth_check(snippet: str) -> bool:
    lower = snippet.lower()
    return any(re.search(rf'\b{kw}\b', lower) for kw in _SECURITY_AUTH_KEYWORDS)


def _is_internal_invariant(snippet: str) -> bool:
    clean = snippet.strip()
    if _is_security_or_auth_check(clean):
        return False
    return any(p.search(clean) for p in _INTERNAL_INVARIANT_PATTERNS)


class PythonAssertInCode(BaseRule):

    LANGUAGES = ["Python"]

    @property
    def rule_id(self) -> str:
        return "PY_ASS_001"

    @property
    def issue_type(self) -> str:
        return "assert_in_production_code"

    @property
    def severity(self) -> str:
        return "low"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        # Skip test and spec files
        if self._is_test_file(file_path):
            self.record_suppression("test_file")
            return

        for node in self._walk(ast):
            if node.get("type") != "assert_statement":
                continue

            snippet = self._snippet(node, source_lines)

            # Suppress internal invariants
            if _is_internal_invariant(snippet):
                self.record_suppression("internal_type_invariant")
                continue

            conf = "high" if _is_security_or_auth_check(snippet) else "medium"

            self.record_syntax_match()
            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    "`assert` statement found in production code. `assert` is removed "
                    "when Python runs with -O; use an explicit `if` and `raise` instead."
                ),
                evidence={"statement": snippet, "confidence": conf},
                confidence=conf,
            )
