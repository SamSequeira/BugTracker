"""
JAVA_UNREACH_001 — Unreachable Code (Java)
-------------------------------------------
Detects statements that are structurally unreachable because they follow
an unconditional `return`, `throw`, `break`, or `continue` in the same block.
"""

from __future__ import annotations

from typing import Iterator, List

from ..analysis.reachability_analyzer import ReachabilityAnalyzer
from ..base_rule import BaseRule
from ..models import CandidateIssue


class JavaUnreachableCode(BaseRule):

    LANGUAGES = ["Java"]

    @property
    def rule_id(self) -> str:
        return "JAVA_UNREACH_001"

    @property
    def issue_type(self) -> str:
        return "unreachable_code"

    @property
    def severity(self) -> str:
        return "low"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        for node in self._walk(ast):
            ntype = node.get("type", "")
            if ntype in ("block", "constructor_body", "switch_block_statement_group"):
                for unreachable_stmt, terminator in ReachabilityAnalyzer.find_unreachable_statements(node):
                    stmt_snippet = self._snippet(unreachable_stmt, source_lines)
                    term_snippet = self._snippet(terminator, source_lines)

                    self.record_syntax_match()
                    yield self._make_issue(
                        node=unreachable_stmt,
                        file_path=file_path,
                        source_lines=source_lines,
                        message=f"Unreachable statement `{stmt_snippet}` follows unconditional `{term_snippet}`.",
                        evidence={
                            "statement": stmt_snippet,
                            "preceding_terminator": term_snippet,
                            "confidence": "high",
                        },
                        confidence="high",
                    )
