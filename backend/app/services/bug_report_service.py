"""
bug_report_service.py
---------------------
Bug Report Service - High-level orchestrator for generating complete,
enriched bug reports, computing summary metrics, and formatting output
for API endpoints and frontend dashboards.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from app.schemas.bug_report import (
    BugReportSummaryStats,
    EnrichedBugReport,
    RepositoryBugReportResponse,
)
from app.services.bug_enrichment_service import (
    BugEnrichmentService,
    bug_enrichment_service,
)
from app.services.candidate_issue_generator import generate_candidate_issues
from app.services.candidate_issue_service import candidate_issue_service
from app.services.issue_classifier.service import issue_classification_service

logger = logging.getLogger(__name__)


class BugReportService:
    """
    Orchestrates the enrichment and report generation stage after
    AST generation, static analysis, and issue classification.
    """

    def __init__(
        self,
        enrichment_service: Optional[BugEnrichmentService] = None,
    ) -> None:
        self.enrichment_service = enrichment_service or bug_enrichment_service

    def generate_reports_from_candidate_issues(
        self,
        candidate_issues: List[Dict[str, Any]],
        ast_for_repository: Optional[Dict[str, Any]] = None,
        repository_id: Optional[str] = None,
        repository_path: Optional[str] = None,
        source_files: Optional[Dict[str, str]] = None,
    ) -> List[EnrichedBugReport]:
        """
        Takes raw candidate issues, runs ML classification (if model is available),
        and applies enrichment to produce a list of EnrichedBugReport models.
        """
        if not candidate_issues:
            return []

        # Step 1: Attempt ML classification (with graceful fallback if model weights not loaded)
        classified_issues = []
        try:
            classified_issues = issue_classification_service.classify_candidate_issues(
                candidate_issues
            )
        except Exception as exc:
            logger.info("ML classification bypassed (using static rule attributes): %s", exc)
            classified_issues = candidate_issues

        # Step 2: Read source file contents for surrounding code windows if possible
        loaded_sources: Dict[str, str] = source_files or {}
        if not loaded_sources:
            for issue in classified_issues:
                fpath = issue.get("file_path", "")
                if fpath and fpath not in loaded_sources:
                    try:
                        p = Path(fpath)
                        if p.exists() and p.is_file():
                            loaded_sources[fpath] = p.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        pass

        # Step 3: Run batch enrichment
        reports = self.enrichment_service.enrich_issues_batch(
            issues=classified_issues,
            ast_for_repository=ast_for_repository,
            source_files=loaded_sources,
            repository_id=repository_id,
            repository_path=repository_path,
        )

        return reports

    def generate_repository_reports(
        self,
        ast_result: Dict[str, Any],
        candidate_result: Optional[Dict[str, Any]] = None,
        repository_id: Optional[str] = None,
        repository_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Complete end-to-end report generation for an analyzed repository.
        Consumes AST results, runs static analysis, candidate issue generation,
        classification, and enrichment, and calculates comprehensive summary statistics.
        """
        repo_path = repository_path or ast_result.get("repository_path", "")

        # 1. Candidate Issue generation if not already provided
        if candidate_result is None:
            candidate_result = candidate_issue_service.generate_from_repository(ast_result)

        raw_candidate_issues = candidate_result.get("candidate_issues", [])

        # 2. Enrich candidate issues into complete Bug Reports
        reports = self.generate_reports_from_candidate_issues(
            candidate_issues=raw_candidate_issues,
            ast_for_repository=ast_result,
            repository_id=repository_id,
            repository_path=repo_path,
        )

        # 3. Compute Summary Statistics
        total_files = ast_result.get("total_files", len(ast_result.get("files_analyzed", [])))
        summary_stats = self.compute_summary_stats(reports, total_files=total_files)

        # 4. Build output dictionary
        serialized_reports = [r.model_dump(mode="json") for r in reports]

        return {
            "repository_id": repository_id,
            "repository_path": repo_path,
            "summary_stats": summary_stats.model_dump(mode="json"),
            "ast_analysis": {
                "repository_path": repo_path,
                "summary": {
                    "total_files": ast_result.get("total_files", 0),
                    "supported_files": ast_result.get("supported_files", 0),
                    "languages": ast_result.get("languages_detected", {}),
                },
                "files": [
                    {k: v for k, v in f.items() if k != "ast"}
                    for f in ast_result.get("files_analyzed", [])
                ] if "files_analyzed" in ast_result else [],
            },
            "candidate_issues": raw_candidate_issues,
            "total_candidate_issues": len(raw_candidate_issues),
            "bug_reports": serialized_reports,
            "total_reports": len(serialized_reports),
        }

    @staticmethod
    def compute_summary_stats(
        reports: List[EnrichedBugReport],
        total_files: int = 0,
    ) -> BugReportSummaryStats:
        """Compute aggregated severity, priority, category, and duplicate counts."""
        stats = BugReportSummaryStats(
            total_bugs=len(reports),
            total_files_analyzed=total_files,
        )

        for report in reports:
            sev = report.severity.lower()
            if sev == "critical":
                stats.critical += 1
            elif sev == "high":
                stats.high += 1
            elif sev == "medium":
                stats.medium += 1
            elif sev == "low":
                stats.low += 1

            prio = report.priority.lower()
            if prio == "p1":
                stats.priority_p1 += 1
            elif prio == "p2":
                stats.priority_p2 += 1
            elif prio == "p3":
                stats.priority_p3 += 1
            elif prio == "p4":
                stats.priority_p4 += 1

            if report.similarity.is_duplicate:
                stats.duplicates_count += 1

            cat = report.category
            stats.categories[cat] = stats.categories.get(cat, 0) + 1

        return stats

    def export_reports(
        self,
        reports: List[Union[Dict[str, Any], Any]],
        format_type: str = "pdf",
        summary_stats: Optional[Dict[str, Any]] = None,
        repo_info: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bytes, str, str]:
        """
        Export bug reports to specified format (PDF, CSV, JSON, Markdown, HTML).
        Returns (content_bytes, media_type, filename).
        """
        from app.services.report_exporter import report_exporter

        return report_exporter.export(
            reports=reports,
            format_type=format_type,
            summary_stats=summary_stats,
            repo_info=repo_info,
        )


# Global singleton instance
bug_report_service = BugReportService()

"""
bug_report_service.py
---------------------
Bug Report Service - High-level orchestrator for generating complete,
enriched bug reports, computing summary metrics, and formatting output
for API endpoints and frontend dashboards.
"""
