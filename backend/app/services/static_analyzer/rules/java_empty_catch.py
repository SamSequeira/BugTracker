"""
JAVA_EXC_001 — Empty catch block (Java)
----------------------------------------
Detects catch_clause nodes whose body block contains no *meaningful*
statements.  Silently swallowing exceptions hides failures and makes
debugging extremely difficult.

Java AST pattern (tree-sitter):
  catch_clause
    ├─ "catch"
    ├─ catch_formal_parameter
    └─ block          ← flagged when block has no meaningful statement children

Root-cause note (F-02)
----------------------
The original rule included "empty_statement" (a bare semicolon `;`) in
_STATEMENT_TYPES, so `catch (E e) { ; }` was treated as non-empty and
not flagged.  A lone semicolon carries no meaningful action — it must be
excluded from the set of "real" statements.
"""

from typing import Iterator, List

from ..base_rule import BaseRule
from ..models import CandidateIssue

# Node types that represent MEANINGFUL statements / declarations.
# Deliberately excludes:
#   "empty_statement"  — a bare `;` is not meaningful
#   "{" / "}"          — block delimiters
#   line_comment / block_comment — comments provide no runtime action
_STATEMENT_TYPES = {
    "expression_statement", "return_statement", "throw_statement",
    "local_variable_declaration", "if_statement", "for_statement",
    "while_statement", "do_statement", "try_statement", "block",
    "enhanced_for_statement", "labeled_statement", "switch_statement",
    "synchronized_statement", "assert_statement", "break_statement",
    "continue_statement",
    # NOTE: "empty_statement" intentionally removed (F-02 fix)
}


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
        return "high"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        for node in self._walk(ast):
            if node["type"] != "catch_clause":
                continue

            # Find the block child
            block = next(
                (c for c in node.get("children", []) if c["type"] == "block"),
                None,
            )
            if block is None:
                continue

            # Block is empty if it has no statement-type children
            statements = [
                c for c in block.get("children", [])
                if c["type"] in _STATEMENT_TYPES
            ]
            if statements:
                continue

            # Get exception variable name for the message
            param = next(
                (c for c in node.get("children", [])
                 if c["type"] == "catch_formal_parameter"),
                None,
            )
            param_text = param.get("text", "e") if param else "e"

            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"Empty catch block for `{param_text}` silently ignores "
                    f"the exception. At minimum log the error or rethrow it."
                ),
                evidence={"catch_parameter": param_text},
            )
