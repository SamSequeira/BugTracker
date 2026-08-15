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
