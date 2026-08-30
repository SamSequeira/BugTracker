"""
candidate_issue_mapper.py
-------------------------
Translates Static Analyzer output (dataclass or dict) into
PostgreSQL ORM model instances (CandidateIssue & IssueStatus).
"""

import uuid
from typing import Any, Dict, List, Tuple, Union

from app.models.candidate_issues import CandidateIssue as CandidateIssueORM
from app.models.issue_status import IssueStatus as IssueStatusORM
from app.services.static_analyzer.models import CandidateIssue as CandidateIssueDataclass


class CandidateIssueMapper:
    """Maps static analysis findings into database ORM entities."""

    @staticmethod
    def _compute_urgency(severity: str) -> str:
        sev = severity.lower()
        if sev in ("critical", "high"):
            return "high"
        elif sev == "low":
            return "low"
        return "medium"

    @staticmethod
    def _format_title(issue_type: str, rule_id: str) -> str:
        clean_type = issue_type.replace("_", " ").title()
        if rule_id:
            return f"{clean_type} ({rule_id})"
        return clean_type

    @staticmethod
    def _format_description(message: str, code_snippet: str | None = None) -> str:
        description = message.strip()
        if code_snippet and code_snippet.strip():
            description += f"\n\nCode Snippet:\n{code_snippet.strip()}"
        return description

    def to_orm(
        self,
        finding: Union[CandidateIssueDataclass, Dict[str, Any]],
        analysis_run_id: str,
    ) -> Tuple[CandidateIssueORM, IssueStatusORM]:
        """
        Convert a single finding (dataclass or dict) into a pair of
        (CandidateIssueORM, IssueStatusORM) objects.
        """
        if isinstance(finding, CandidateIssueDataclass):
            rule_id = finding.rule_id
            issue_type = finding.issue_type
            message = finding.message
            file_path = finding.file_path
            line_number = finding.line_number
            column = finding.column
            code_snippet = finding.code_snippet
            evidence = finding.evidence
            severity = finding.severity
            language = getattr(finding, "language", None)
        else:
            rule_id = finding.get("rule_id", "")
            issue_type = finding.get("issue_type", "unknown_issue")
            message = finding.get("message", "")
            file_path = finding.get("file_path", "")
            line_number = finding.get("line_number")
            column = finding.get("column")
            code_snippet = finding.get("code_snippet")
            evidence = finding.get("evidence")
            severity = finding.get("severity", "medium")
            language = finding.get("language")

        if not language or language == "Unknown":
            r_id = rule_id.upper() if rule_id else ""
            f_p = file_path.lower() if file_path else ""
            if r_id.startswith("PY_") or f_p.endswith(".py"):
                language = "Python"
            elif r_id.startswith("JS_") or f_p.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs")):
                language = "JavaScript"
            elif r_id.startswith("JAVA_") or f_p.endswith(".java"):
                language = "Java"
            else:
                language = "Unknown"

        issue_id = str(uuid.uuid4())
        title = self._format_title(issue_type, rule_id)
        description = self._format_description(message, code_snippet)
        urgency = self._compute_urgency(severity)

        candidate_issue_orm = CandidateIssueORM(
            id=issue_id,
            analysis_run_id=analysis_run_id,
            title=title,
            description=description,
            file_path=file_path,
            line_number=line_number,
            column=column,
            rule_id=rule_id,
            issue_type=issue_type,
            message=message,
            code_snippet=code_snippet,
            evidence=evidence,
            language=language,
            severity=severity,  # Preserved original detector severity
            urgency=urgency,
            verified_severity=None,  # Not verified yet; ground truth assigned separately
            verified_priority=None,  # Not verified yet; ground truth assigned separately
            verified_at=None,
            verification_notes=None,
        )

        status_id = str(uuid.uuid4())
        issue_status_orm = IssueStatusORM(
            id=status_id,
            candidate_issue_id=issue_id,
            status="open",
        )

        return candidate_issue_orm, issue_status_orm

    def to_orm_bulk(
        self,
        findings: List[Union[CandidateIssueDataclass, Dict[str, Any]]],
        analysis_run_id: str,
    ) -> Tuple[List[CandidateIssueORM], List[IssueStatusORM]]:
        """
        Convert a list of findings into lists of CandidateIssueORM and IssueStatusORM.
        """
        issues: List[CandidateIssueORM] = []
        statuses: List[IssueStatusORM] = []

        for finding in findings:
            issue_orm, status_orm = self.to_orm(finding, analysis_run_id)
            issues.append(issue_orm)
            statuses.append(status_orm)

        return issues, statuses


candidate_issue_mapper = CandidateIssueMapper()
