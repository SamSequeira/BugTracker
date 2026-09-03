"""
candidate_issue_mapper.py
-------------------------
Translates Static Analyzer output (dataclass or dict) into
PostgreSQL ORM model instances (CandidateIssue, IssueStatus, and IssueRecommendation).
"""

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from app.models.candidate_issues import CandidateIssue as CandidateIssueORM
from app.models.issue_recommendation import IssueRecommendation as IssueRecommendationORM
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

    @staticmethod
    def _resolve_source_file_id(
        file_path: str,
        source_file_map: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """Resolve source_file_id from file_path against lookup map."""
        if not source_file_map or not file_path:
            return None

        # 1. Direct exact lookup
        if file_path in source_file_map:
            return source_file_map[file_path]

        # 2. Normalized POSIX path lookup
        norm_posix = Path(file_path).as_posix()
        if norm_posix in source_file_map:
            return source_file_map[norm_posix]

        # 3. Path with backslashes replaced
        alt_path = file_path.replace("\\", "/")
        if alt_path in source_file_map:
            return source_file_map[alt_path]

        # 4. Filename-only suffix match as fallback
        file_name = Path(file_path).name
        for mapped_path, sf_id in source_file_map.items():
            if mapped_path.endswith(file_name) or norm_posix.endswith(mapped_path):
                return sf_id

        return None

    def extract_recommendations(
        self,
        finding: Union[CandidateIssueDataclass, Dict[str, Any]],
        candidate_issue_id: str,
    ) -> List[IssueRecommendationORM]:
        """Extract and instantiate IssueRecommendationORM objects for a finding."""
        recommendations: List[IssueRecommendationORM] = []

        if isinstance(finding, CandidateIssueDataclass):
            return recommendations

        # 1. Check for list of recommendations
        raw_recs = finding.get("recommendations")
        if isinstance(raw_recs, list) and raw_recs:
            for idx, rec in enumerate(raw_recs, start=1):
                if isinstance(rec, dict):
                    rec_text = rec.get("recommendation") or rec.get("text") or rec.get("message") or ""
                    if rec_text:
                        recommendations.append(
                            IssueRecommendationORM(
                                id=str(uuid.uuid4()),
                                candidate_issue_id=candidate_issue_id,
                                recommendation=rec_text,
                                diff_remove=rec.get("diff_remove"),
                                diff_add=rec.get("diff_add"),
                                priority_order=rec.get("priority_order", idx),
                                fix_type=rec.get("fix_type", "suggestion"),
                            )
                        )
                elif isinstance(rec, str) and rec.strip():
                    recommendations.append(
                        IssueRecommendationORM(
                            id=str(uuid.uuid4()),
                            candidate_issue_id=candidate_issue_id,
                            recommendation=rec.strip(),
                            priority_order=idx,
                            fix_type="suggestion",
                        )
                    )

        # 2. Check for single recommendation / diff attributes on finding directly
        elif finding.get("recommendation") or finding.get("diff_add") or finding.get("suggested_fix"):
            rec_text = str(finding.get("recommendation") or finding.get("suggested_fix") or "Apply code patch")
            recommendations.append(
                IssueRecommendationORM(
                    id=str(uuid.uuid4()),
                    candidate_issue_id=candidate_issue_id,
                    recommendation=rec_text,
                    diff_remove=finding.get("diff_remove"),
                    diff_add=finding.get("diff_add"),
                    priority_order=1,
                    fix_type=finding.get("fix_type", "code_patch" if finding.get("diff_add") else "suggestion"),
                )
            )

        # 3. Fallback: generate default recommendation from evidence or message
        if not recommendations:
            msg = finding.get("message") or "Remediate static analysis finding"
            ev = finding.get("evidence") if isinstance(finding.get("evidence"), dict) else {}
            suggested = ev.get("suggested") or f"Review and fix {finding.get('rule_id', 'issue')}: {msg}"
            recommendations.append(
                IssueRecommendationORM(
                    id=str(uuid.uuid4()),
                    candidate_issue_id=candidate_issue_id,
                    recommendation=suggested,
                    priority_order=1,
                    fix_type="suggestion",
                )
            )

        return recommendations

    def to_orm(
        self,
        finding: Union[CandidateIssueDataclass, Dict[str, Any]],
        analysis_run_id: str,
        source_file_id: Optional[str] = None,
        **kwargs: Any,
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
            if source_file_id is None:
                source_file_id = finding.get("source_file_id")

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
            source_file_id=source_file_id,
            title=title,
            description=description,
            file_path=file_path,
            line_number=line_number,
            column=column,
            rule_id=rule_id if rule_id else None,
            issue_type=issue_type,
            message=message,
            code_snippet=code_snippet,
            evidence=evidence,
            language=language,
            severity=severity,  # Preserved original detector severity
            urgency=urgency,
            verified_severity=None,
            verified_priority=None,
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
        source_file_map: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Tuple[List[CandidateIssueORM], List[IssueStatusORM]]:
        """
        Convert a list of findings into lists of CandidateIssueORM and IssueStatusORM,
        resolving source_file_id from source_file_map if provided.
        """
        issues: List[CandidateIssueORM] = []
        statuses: List[IssueStatusORM] = []

        for finding in findings:
            fpath = finding.file_path if isinstance(finding, CandidateIssueDataclass) else finding.get("file_path", "")
            sf_id = self._resolve_source_file_id(fpath, source_file_map)

            issue_orm, status_orm = self.to_orm(
                finding,
                analysis_run_id,
                source_file_id=sf_id,
            )
            issues.append(issue_orm)
            statuses.append(status_orm)

        return issues, statuses

    def to_orm_bulk_with_relations(
        self,
        findings: List[Union[CandidateIssueDataclass, Dict[str, Any]]],
        analysis_run_id: str,
        source_file_map: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Tuple[List[CandidateIssueORM], List[IssueStatusORM], List[IssueRecommendationORM]]:
        """
        Convert a list of findings into CandidateIssueORM, IssueStatusORM, and
        extracted IssueRecommendationORM lists, with SourceFile linking.
        """
        issues: List[CandidateIssueORM] = []
        statuses: List[IssueStatusORM] = []
        recommendations: List[IssueRecommendationORM] = []

        for finding in findings:
            fpath = finding.file_path if isinstance(finding, CandidateIssueDataclass) else finding.get("file_path", "")
            sf_id = self._resolve_source_file_id(fpath, source_file_map)

            issue_orm, status_orm = self.to_orm(
                finding,
                analysis_run_id,
                source_file_id=sf_id,
            )
            recs = self.extract_recommendations(finding, issue_orm.id)

            issues.append(issue_orm)
            statuses.append(status_orm)
            recommendations.extend(recs)

        return issues, statuses, recommendations


candidate_issue_mapper = CandidateIssueMapper()
