"""
base_rule.py
------------
Abstract base class that every analysis rule must implement.

A rule is a self-contained, stateless object that:
  - declares which language(s) it applies to
  - receives the full AST dict and the raw source lines
  - yields zero or more CandidateIssue instances

Adding a new rule means:
  1. Create a subclass of BaseRule in the rules/ directory.
  2. Register it in rules/__init__.py.
  No other file needs to change.
"""

from abc import ABC, abstractmethod
from typing import Iterator, List

from .models import CandidateIssue


class BaseRule(ABC):
    """Abstract base for all static analysis rules."""

    # Languages this rule applies to.  Use the same strings as ASTGenerator:
    # "Python", "JavaScript", "Java"
    LANGUAGES: List[str] = []

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Unique rule identifier, e.g. 'PY_DIV_001'."""

    @property
    @abstractmethod
    def issue_type(self) -> str:
        """Short category label, e.g. 'division_by_zero'."""

    @property
    @abstractmethod
    def severity(self) -> str:
        """'critical' | 'high' | 'medium' | 'low'"""

    @abstractmethod
    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:
        """
        Traverse *ast* and yield a CandidateIssue for every violation found.

        Parameters
        ----------
        ast          : The normalized AST dict produced by ASTGenerator.
        file_path    : Path of the file being analyzed (for issue reporting).
        source_lines : The original source split by line (0-indexed), used
                       to populate code_snippet without re-reading the file.
        """

    # ------------------------------------------------------------------
    # Shared traversal helper — available to every rule subclass
    # ------------------------------------------------------------------

    def _walk(self, node: dict) -> Iterator[dict]:
        """
        Depth-first pre-order traversal of the normalized AST dict.
        Yields every node (including the root).
        """
        yield node
        for child in node.get("children", []):
            yield from self._walk(child)

    def _snippet(self, node: dict, source_lines: List[str]) -> str:
        """
        Return the source text for *node* using source_lines as a fallback
        when node["text"] is empty or spans multiple lines ambiguously.
        """
        raw_text = node.get("text")
        text = str(raw_text).strip() if raw_text is not None else ""
        if text:
            # Prefer the embedded text; trim to first line for brevity
            first_line = text.split("\n")[0].strip()
            return first_line if first_line else text
        # Fallback: pull from source_lines
        start = node.get("start") or {}
        line_idx = start.get("line", 0)
        if 0 <= line_idx < len(source_lines):
            return source_lines[line_idx].rstrip()
        return ""

    def _make_issue(
        self,
        node: dict,
        file_path: str,
        source_lines: List[str],
        message: str,
        evidence: dict,
    ) -> CandidateIssue:
        """Convenience factory — builds a CandidateIssue from a node."""
        start = node.get("start") or {}
        line_num = start.get("line", 0) + 1
        col_num = start.get("column", 0)
        return CandidateIssue(
            rule_id=self.rule_id,
            issue_type=self.issue_type,
            message=message,
            file_path=file_path,
            line_number=line_num,   # convert to 1-based
            column=col_num,
            code_snippet=self._snippet(node, source_lines),
            evidence=evidence,
            severity=self.severity,
        )
