"""
JS_EQ_001 — Use of == instead of === (JavaScript)
--------------------------------------------------
Detects `binary_expression` nodes that use loose equality operators `==` or `!=`.
JavaScript's type coercion rules make loose equality prone to subtle runtime bugs.

Exemptions:
1. `x == null` or `null == x` (standard JS idiom for nullish checks).
2. `typeof x == 'string'` or `typeof x != '...'` (typeof always produces string).
"""

from __future__ import annotations

from typing import Iterator, List

from ..base_rule import BaseRule
from ..models import CandidateIssue

_LOOSE_OPS = {"==", "!="}


def _is_null_or_undefined(node: dict) -> bool:
    ntype = node.get("type", "")
    text = (node.get("text") or "").strip()
    return ntype in ("null", "null_literal") or text in ("null", "undefined")


def _is_typeof_expression(node: dict) -> bool:
    if node.get("type") != "unary_expression":
        return False
    children = node.get("children", [])
    return bool(children) and (children[0].get("text") or "").strip() == "typeof"


class JavaScriptTripleEquals(BaseRule):

    LANGUAGES = ["JavaScript"]

    @property
    def rule_id(self) -> str:
        return "JS_EQ_001"

    @property
    def issue_type(self) -> str:
        return "loose_equality"

    @property
    def severity(self) -> str:
        return "medium"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        for node in self._walk(ast):
            if node.get("type") != "binary_expression":
                continue

            children = node.get("children", [])
            if len(children) < 3:
                continue

            op = (children[1].get("text") or "").strip()
            if op not in _LOOSE_OPS:
                continue

            left = children[0]
            right = children[2]

            # 1. Exempt `x == null` and `null == x`
            if _is_null_or_undefined(left) or _is_null_or_undefined(right):
                self.record_suppression("null_or_undefined_idiom")
                continue

            # 2. Exempt `typeof x == '...'`
            if _is_typeof_expression(left) or _is_typeof_expression(right):
                self.record_suppression("typeof_idiom")
                continue

            strict_op = "===" if op == "==" else "!=="
            snippet = self._snippet(node, source_lines)

            self.record_syntax_match()
            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=f"Use strict equality `{strict_op}` instead of loose equality `{op}` to avoid unexpected type coercion.",
                evidence={
                    "operator": op,
                    "recommended_operator": strict_op,
                    "expression": snippet,
                    "confidence": "high",
                },
                confidence="high",
            )
