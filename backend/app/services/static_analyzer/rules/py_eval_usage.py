"""
PY_EVAL_001 — Dangerous Dynamic Execution (Python)
---------------------------------------------------
Detects calls to `eval()` or `exec()` with dynamic, non-constant arguments.
Dynamic evaluation of untrusted or variable strings is a major security vulnerability (arbitrary code execution).

Exemptions:
- Static literal string expressions (e.g. `eval("1 + 1")` or `eval("{'a': 1}")` in controlled test fixtures).
"""

from __future__ import annotations

from typing import Iterator, List

from ..analysis.constant_evaluator import evaluate_constant
from ..base_rule import BaseRule
from ..models import CandidateIssue

_DANGEROUS_FUNCS = {"eval", "exec"}


class PythonEvalUsage(BaseRule):

    LANGUAGES = ["Python"]

    @property
    def rule_id(self) -> str:
        return "PY_EVAL_001"

    @property
    def issue_type(self) -> str:
        return "dangerous_eval_exec"

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
            if node.get("type") != "call":
                continue

            children = node.get("children", [])
            if not children:
                continue

            func_node = children[0]
            func_name = (func_node.get("text") or "").strip()

            if func_name not in _DANGEROUS_FUNCS:
                continue

            # Check arguments
            args_node = next((c for c in children if c.get("type") == "argument_list"), None)
            if not args_node:
                continue

            arg_children = [
                c for c in args_node.get("children", [])
                if c.get("text", "") not in ("(", ")", ",")
            ]

            if not arg_children:
                continue

            first_arg = arg_children[0]
            first_arg_text = (first_arg.get("text") or "").strip()

            # Check if argument is a constant literal string
            const_val = evaluate_constant(first_arg)
            if isinstance(const_val, str) and not any(kw in first_arg_text for kw in ("input(", "request", "param", "__", "os.")):
                self.record_suppression("constant_literal_argument")
                continue

            snippet = self._snippet(node, source_lines)
            self.record_syntax_match()
            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=f"Dynamic `{func_name}()` execution detected with dynamic argument `{first_arg_text}`.",
                evidence={
                    "function": func_name,
                    "argument": first_arg_text,
                    "call_expression": snippet,
                    "confidence": "high",
                },
                confidence="high",
            )
