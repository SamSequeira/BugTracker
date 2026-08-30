"""
normalizer.py — Standardized text normalization for Candidate Issues.
====================================================================
Transforms structured candidate issue objects or dictionaries into
clean, predictable text representations for tokenization and model ingestion.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from .config import NormalizationConfig


class IssueNormalizer:
    """
    Transforms CandidateIssue instances or raw issue dicts into normalized text.

    Supports ablation modes (e.g. omitting rule_id) to verify that the
    model is learning issue semantics rather than simple rule-id mapping.
    """

    def __init__(self, config: Optional[NormalizationConfig] = None) -> None:
        self.config = config or NormalizationConfig()

    def normalize(
        self,
        issue: Union[Dict[str, Any], Any],
        language: Optional[str] = None,
    ) -> str:
        """
        Normalize a single issue into a formatted string.

        Parameters
        ----------
        issue : dict or CandidateIssue
            The issue data containing rule_id, issue_type, message, etc.
        language : str, optional
            The source language (e.g. 'Python', 'Java', 'JavaScript').
            If not passed, extracted from issue['language'] if present.

        Returns
        -------
        str : The formatted, normalized text representation.
        """
        # Convert object to dict if necessary
        if hasattr(issue, "to_dict"):
            data = issue.to_dict()
        elif isinstance(issue, dict):
            data = issue
        else:
            data = getattr(issue, "__dict__", {})

        lang = language or data.get("language") or "Unknown"
        rule_id = data.get("rule_id", "").strip()
        issue_type = data.get("issue_type", "").strip()
        message = data.get("message", "").strip()
        code_snippet = data.get("code_snippet", "").strip()
        evidence = data.get("evidence", {}) or {}

        sections: List[str] = []

        if self.config.include_language and lang:
            sections.append(f"Language: {lang}")

        if self.config.include_rule_id and rule_id:
            sections.append(f"Rule ID: {rule_id}")

        if self.config.include_issue_type and issue_type:
            sections.append(f"Issue Type: {issue_type}")

        if self.config.include_message and message:
            sections.append(f"Message: {message}")

        if self.config.include_code_snippet and code_snippet:
            sections.append(f"Code: {code_snippet}")

        if self.config.include_evidence and isinstance(evidence, dict) and evidence:
            evidence_lines = ["Evidence:"]
            for key in sorted(evidence.keys()):
                val = evidence[key]
                # Format key from snake_case to Title Case
                formatted_key = key.replace("_", " ").title()
                evidence_lines.append(f"{formatted_key}: {val}")
            sections.append("\n".join(evidence_lines))

        return "\n".join(sections).strip()

    def normalize_batch(
        self,
        issues: List[Union[Dict[str, Any], Any]],
        language: Optional[str] = None,
    ) -> List[str]:
        """Normalize a collection of issues."""
        return [self.normalize(i, language=language) for i in issues]
