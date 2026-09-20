"""
PY_CONSTCOND_001 — Constant Branch Condition (Python)
------------------------------------------------------
Detects `if` statements or boolean branch expressions with compile-time constant conditions (e.g. `if True:`, `if False:`, `if 1 == 2:`).
Constant conditions indicate dead branches, leftover debugging flags, or logic errors.

Exemptions:
- Idiomatic entrypoint check: `if __name__ == '__main__':`
- Type checking imports guard: `if TYPE_CHECKING:`
- Intentional loops: `while True:` (handled by loop analyzer).
"""

from __future__ import annotations

from typing import Iterator, List

from ..analysis.constant_evaluator import evaluate_constant
from ..analysis.guard_analyzer import GuardAnalyzer
from ..base_rule import BaseRule
from ..models import CandidateIssue


class PythonConstantCondition(BaseRule):

    LANGUAGES = ["Python"]

    @property
    def rule_id(self) -> str:
        return "PY_CONSTCOND_001"

    @property
    def issue_type(self) -> str:
        return "constant_condition"

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

            if ntype == "if_statement":
                # Find condition child
                children = node.get("children", [])
                cond_node = next(
                    (c for c in children if c.get("type") not in ("if", "elif", ":", "block", "else_clause", "elif_clause")),
                    None,
                )
                if not cond_node:
                    continue

                if GuardAnalyzer.is_idiomatic_non_constant(cond_node):
                    self.record_suppression("idiomatic_entrypoint_or_type_checking")
                    continue

                const_val = evaluate_constant(cond_node)
                if const_val is not None:
                    cond_snippet = self._snippet(cond_node, source_lines)
                    self.record_syntax_match()
                    yield self._make_issue(
                        node=cond_node,
                        file_path=file_path,
                        source_lines=source_lines,
                        message=f"`if` condition `{cond_snippet}` is constant `{const_val}`.",
                        evidence={
                            "condition": cond_snippet,
                            "constant_value": const_val,
                            "confidence": "high",
                        },
                        confidence="high",
                    )
            elif ntype == "while_statement":
                # Only flag while False:, not while True: (which is intentional infinite loop pattern)
                children = node.get("children", [])
                cond_node = next(
                    (c for c in children if c.get("type") not in ("while", ":", "block")),
                    None,
                )
                if cond_node:
                    const_val = evaluate_constant(cond_node)
                    if const_val is False or const_val == 0:
                        cond_snippet = self._snippet(cond_node, source_lines)
                        self.record_syntax_match()
                        yield self._make_issue(
                            node=cond_node,
                            file_path=file_path,
                            source_lines=source_lines,
                            message=f"`while` condition `{cond_snippet}` is constantly false (loop body never executes).",
                            evidence={
                                "condition": cond_snippet,
                                "constant_value": False,
                                "confidence": "high",
                            },
                            confidence="high",
                        )
