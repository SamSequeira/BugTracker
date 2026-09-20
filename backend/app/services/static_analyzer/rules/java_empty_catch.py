"""
JAVA_EXC_001 — Empty / Swallowed Catch Block (Java)
----------------------------------------------------
Detects `catch_clause` blocks whose body contains no meaningful statements,
silently swallowing exceptions in production code.

High-confidence detection criteria:
- Empty catch blocks: `catch (Exception e) {}`
- Catch blocks containing only empty semicolons `; ;` or non-intentional comments.
- Broad exceptions (`Exception`, `Throwable`, `RuntimeException`) swallowed without logging or re-raising.

Suppression criteria (provably safe / intentional):
- Intentionally named exception variables: `expected`, `ignored`, `unused`, `_`, `ex_ignored`
- Intentional inline comments: `// expected`, `/* ignore */`, `// ignore`, `// intentional`
- Standard rethrowing: `throw e;`
- Meaningful logging: `log.error(...)`, `logger.warn(...)`, `System.err.println(...)`, `e.printStackTrace()`
"""

from __future__ import annotations

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

_LOGGING_RE = re.compile(
    r'\b(?:log|logger|LOGGER|LOG|System\.err)\.(?:error|warn|warning|info|trace|debug|println|print)\b|\bprintStackTrace\s*\(',
    re.IGNORECASE,
)


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
        return "medium"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        for node in self._walk(ast):
            if node.get("type") != "catch_clause":
                continue

            block = next((c for c in node.get("children", []) if c.get("type") == "block"), None)
            if block is None:
                continue

            param = next((c for c in node.get("children", []) if c.get("type") == "catch_formal_parameter"), None)
            param_text = param.get("text", "e") if param else "e"
            param_name = param_text.split()[-1].strip() if param_text else "e"

            # Check intentional parameter names: catch (Exception ignored)
            if param_name.lower() in _INTENTIONAL_PARAM_NAMES:
                self.record_suppression("intentional_param_name")
                continue

            block_text = block.get("text") or ""

            # Check intentional comments inside catch body: /* ignore */, // intentional, // expected
            if _INTENTIONAL_COMMENT_RE.search(block_text):
                self.record_suppression("intentional_comment")
                continue

            # Check statements inside block
            statements = [
                c for c in block.get("children", [])
                if c.get("type") in _STATEMENT_TYPES
            ]

            # 1. Completely empty catch block or only empty semicolons
            if not statements:
                self.record_syntax_match()
                yield self._make_issue(
                    node=node,
                    file_path=file_path,
                    source_lines=source_lines,
                    message=f"Empty catch block for `{param_name}` silently swallows exceptions.",
                    evidence={
                        "catch_parameter": param_name,
                        "reason": "empty_block",
                        "confidence": "high",
                    },
                    confidence="high",
                )
                continue

            # 2. Check if body rethrows or logs
            has_throw = any(s.get("type") == "throw_statement" for s in self._walk(block))
            has_logging = bool(_LOGGING_RE.search(block_text))

            if not has_throw and not has_logging and len(statements) == 1 and statements[0].get("type") == "empty_statement":
                self.record_syntax_match()
                yield self._make_issue(
                    node=node,
                    file_path=file_path,
                    source_lines=source_lines,
                    message=f"Empty catch block for `{param_name}` silently swallows exceptions.",
                    evidence={
                        "catch_parameter": param_name,
                        "reason": "empty_statement_only",
                        "confidence": "high",
                    },
                    confidence="high",
                )
                continue

            self.record_suppression("handled_catch_block")
