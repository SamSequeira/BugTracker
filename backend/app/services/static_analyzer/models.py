"""
models.py
---------
Standardized data structures for static analysis output.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CandidateIssue:
    """
    A single potential code issue detected by a static analysis rule.

    Fields
    ------
    rule_id       : Unique identifier for the rule that produced this issue.
                    Format: <LANGUAGE>_<CATEGORY>_NNN  e.g. PY_DIV_001
    issue_type    : Short category label.  e.g. "division_by_zero"
    message       : Human-readable description of what was detected and why
                    it may be a problem.
    file_path     : Path to the source file being analyzed.
    line_number   : 1-based line number where the issue starts.
    column        : 0-based column where the issue starts.
    code_snippet  : The exact source text of the offending node.
    evidence      : Machine-readable detail dict that explains how the rule
                    reached this conclusion.  Keyed by rule-specific fields
                    (e.g. {"operator": "/", "right_operand": "b"}).
    severity      : "high" | "medium" | "low"
    confidence    : "high" | "medium" | "low"
    """

    rule_id: str
    issue_type: str
    message: str
    file_path: str
    line_number: int
    column: int
    code_snippet: str
    evidence: dict = field(default_factory=dict)
    severity: str = "medium"
    confidence: str = "medium"  # "high" | "medium" | "low"

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "issue_type": self.issue_type,
            "message": self.message,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column": self.column,
            "code_snippet": self.code_snippet,
            "evidence": self.evidence,
            "severity": self.severity,
            "confidence": self.confidence,
        }

