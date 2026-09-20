"""
JS_CONSTCOND_001 — Constant Branch Condition (JavaScript)
----------------------------------------------------------
Detects `if` statements or ternary expressions with compile-time constant boolean conditions
such as `if (true)`, `if (false)`, `if (1 === 2)`.
"""

from __future__ import annotations

from typing import Iterator, List

from ..analysis.constant_evaluator import evaluate_constant
from ..base_rule import BaseRule
from ..models import CandidateIssue


class JavaScriptConstantCondition(BaseRule):

    LANGUAGES = ["JavaScript"]

    @property
    def rule_id(self) -> str:
        return "JS_CONSTCOND_001"

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
                children = node.get("children", [])
                cond_node = next((c for c in children if c.get("type") == "parenthesized_expression"), None)
                if not cond_node:
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
                # Only flag while (false), not while (true)
                children = node.get("children", [])
                cond_node = next((c for c in children if c.get("type") == "parenthesized_expression"), None)
                if cond_node:
                    const_val = evaluate_constant(cond_node)
                    if const_val is False:
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
