"""
PY_ASS_001 — assert used for input validation (Python)
-------------------------------------------------------
Detects assert_statement nodes outside test files.
Python's -O flag strips assert statements at runtime, so using assert
for validation or access-control checks is unsafe in production code.

AST pattern (Python):
  assert_statement
    └─ "assert"
"""

from typing import Iterator, List

from ..base_rule import BaseRule
from ..models import CandidateIssue

_TEST_FILE_MARKERS = ("test_", "_test", "spec_", "_spec")


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

        # Skip test files — assert is expected there
        basename = file_path.lower().replace("\\", "/").split("/")[-1]
        if any(basename.startswith(m) or basename.endswith(m + ".py")
               for m in _TEST_FILE_MARKERS):
            return

        for node in self._walk(ast):
            if node["type"] != "assert_statement":
                continue

            snippet = self._snippet(node, source_lines)
            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    "assert statement found in production code.  "
                    "assert is removed when Python runs with -O; "
                    "use an explicit if/raise for validation."
                ),
                evidence={"statement": snippet},
            )

"""
PY_ASS_001 — assert used for runtime validation (Python)
---------------------------------------------------------
Detects `assert` statements used for runtime input validation, authorization,
or security checks in production code. Because Python's `-O` (optimized) flag
strips all `assert` statements at compile/bytecode time, relying on `assert`
for data integrity or access control creates security and runtime hazards.

Suppression criteria (provably safe / intentional):
- Standard test assertions in test files
- Type narrowing / internal state invariants (e.g. `assert cls is not None`,
  `assert isinstance(x, T)`, `assert len(internals) > 0`)

Confidence calibration:
- HIGH: Security, authorization, authentication, or external input assertions
  (e.g. `assert user.is_admin`, `assert token is not None`, `assert request.is_authenticated`).
- MEDIUM: Public function argument validation using assert.
- LOW: Ambiguous assertions in utility modules.
"""

import re
from typing import Iterator, List, Optional, Set

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
]



def _is_security_or_auth_check(snippet: str) -> bool:
    lower = snippet.lower()
    return any(re.search(rf'\b{kw}\b', lower) for kw in _SECURITY_AUTH_KEYWORDS)


def _is_internal_invariant(snippet: str) -> bool:
    clean = snippet.strip()
    # Security/authorization checks must NEVER be suppressed as internal invariants
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

        is_test = self._is_test_file(file_path)

        for node in self._walk(ast):
            if node.get("type") != "assert_statement":
                continue

            self.record_syntax_match()

            snippet = self._snippet(node, source_lines).strip()

            # 1. Assertions in test files -> suppress
            if is_test:
                self.record_suppression("test_file_assertion")
                continue

            # 2. Internal type-narrowing and state invariants -> suppress
            if _is_internal_invariant(snippet):
                self.record_suppression("internal_type_or_state_invariant")
                continue

            # 3. Security / Authorization / Input validation checks
            if _is_security_or_auth_check(snippet):
                confidence = "high"
                category = "security/authorization validation"
            else:
                confidence = "medium"
                category = "runtime state validation"

            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"assert used for {category}. Python removes `assert` with -O optimization flag; "
                    f"use explicit `if not ...: raise ValueError(...)` instead."
                ),
                evidence={
                    "statement": snippet,
                    "validation_category": category,
                    "confidence": confidence,
                    "reason": f"Production assertion ({snippet}) could be bypassed in optimized Python execution (-O).",
                },
                confidence=confidence,
            )

