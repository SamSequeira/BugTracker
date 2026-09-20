"""
JS_EVAL_001 — Dangerous eval() Execution (JavaScript)
-----------------------------------------------------
Detects dynamic calls to `eval()` or `window.eval()` with non-constant arguments.
Dynamic execution allows arbitrary JavaScript code execution and bypasses security boundaries.
"""

from __future__ import annotations

from typing import Iterator, List

from ..analysis.constant_evaluator import evaluate_constant
from ..base_rule import BaseRule
from ..models import CandidateIssue


class JavaScriptEvalUsage(BaseRule):

    LANGUAGES = ["JavaScript"]

    @property
    def rule_id(self) -> str:
        return "JS_EVAL_001"

    @property
    def issue_type(self) -> str:
        return "dangerous_eval"

    @property
    def severity(self) -> str:
        return "high"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        for node in self._walk(ast):
            if node.get("type") not in ("call_expression", "call"):
                continue

            children = node.get("children", [])
            if not children:
                continue

            func_node = children[0]
            func_text = (func_node.get("text") or "").strip()

            if func_text not in ("eval", "window.eval", "global.eval", "globalThis.eval"):
                continue

            args_node = next((c for c in children if c.get("type") in ("arguments", "argument_list")), None)
            if not args_node:
                continue

            arg_kids = [c for c in args_node.get("children", []) if c.get("text", "") not in ("(", ")", ",")]
            if not arg_kids:
                continue

            first_arg = arg_kids[0]
            first_arg_text = (first_arg.get("text") or "").strip()

            # Check if static string literal
            const_val = evaluate_constant(first_arg)
            if isinstance(const_val, str) and not any(k in first_arg_text for k in ("req", "res", "param", "input", "window")):
                self.record_suppression("constant_literal_eval")
                continue

            snippet = self._snippet(node, source_lines)
            self.record_syntax_match()
            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=f"Dangerous `eval()` call with dynamic argument `{first_arg_text}`.",
                evidence={
                    "expression": snippet,
                    "argument": first_arg_text,
                    "confidence": "high",
                },
                confidence="high",
            )
