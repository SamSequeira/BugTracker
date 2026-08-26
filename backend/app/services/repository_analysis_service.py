"""
Repository Analysis Service - Orchestrates the complete analysis pipeline.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_run import AnalysisRun
from app.repositories.candidate_issue_repo import candidate_issue_repository
from app.repositories.issue_status_repo import issue_status_repository
from app.services.ast_generator import ast_generator
from app.services.candidate_issue_mapper import candidate_issue_mapper
from app.services.candidate_issue_service import (
    candidate_issue_service
)
from app.services.language_detector import detect_language


class RepositoryAnalysisService:
    """Orchestrates repository analysis: language detection + AST + Static Analysis + Bug Enrichment."""

    def __init__(self, similarity_service: Any = None) -> None:
        self.similarity_service = similarity_service

    @staticmethod
    def get_local_repository_path(repository_id: str, repository_name: str) -> Path:
        """Resolve a server-managed workspace path without trusting client input."""
        return Path("repositories") / f"{repository_id}-{repository_name}"

    async def analyze_repository(self, repo_path: str) -> Dict[str, Any]:
        """
        Analyze a repository for language detection, AST generation,
        static analysis, candidate issues, and enriched bug reports.
        
        Args:
            repo_path: Path to the repository
            repository_id: Optional repository identifier
            
        Returns:
            Comprehensive analysis results with enriched bug reports
        """
        from app.services.bug_report_service import bug_report_service

        repo_path = Path(repo_path)
        if not repo_path.exists():
            raise ValueError(f"Repository path not found: {repo_path}")

        # Run analysis in thread pool to avoid blocking
        # Step 1: Generate AST for all files in repository
        ast_result = await asyncio.to_thread(
            ast_generator.generate_ast_for_repository,
            str(repo_path)
        )

        # Step 2: Run Static Analysis on the complete AST result
        candidate_result = await asyncio.to_thread(
            candidate_issue_service.generate_from_repository,
            ast_result
        )

        # Step 3: Return clean response without dumping massive AST hierarchies
        return {
            "repository_id": repository_id,
            "repository_path": str(repo_path),
            "summary": formatted_ast["summary"],
            "files": formatted_ast["files"],
            "ast_analysis": formatted_ast,
            "static_analysis": static_analysis_result,
            "candidate_issues": candidate_result["candidate_issues"],
            "total_candidate_issues": candidate_result["total_candidate_issues"],
            "bug_reports": report_data["bug_reports"],
            "total_reports": report_data["total_reports"],
            "summary_stats": report_data["summary_stats"],
        }

    def _format_analysis_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Format AST generation summary for API response without raw AST file trees."""
        return {
            "summary": {
                "total_files": result["total_files"],
                "supported_files": result["supported_files"],
                "languages": result["languages_detected"],
            },
        }

    async def analyze_file(self, file_path: str) -> Dict[str, Any]:
        """
        Analyze a single file for language detection and AST generation.
        
        Args:
            file_path: Path to the code file
            
        Returns:
            Analysis results for the file including full AST
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise ValueError(f"File not found: {file_path}")

        language = detect_language(file_path.name)
        if not language or language == "Unsupported":
            return {
                "file": str(file_path),
                "language": language or "Unknown",
                "supported": False,
                "error": "Language not supported",
            }

        # Generate AST in thread pool
        result = await asyncio.to_thread(
            ast_generator.generate_ast,
            str(file_path),
            language
        )

        return result

    async def complete_analysis_run(
        self,
        db: AsyncSession,
        analysis_run_id: str,
        analysis_result: Dict[str, Any],
    ) -> AnalysisRun:
        """
        Persist generated findings (CandidateIssue and IssueStatus rows) and
        update AnalysisRun metrics in a single atomic database transaction.
        """
        try:
            raw_findings = analysis_result.get("candidate_issues", [])

            # Map findings to CandidateIssue & IssueStatus ORM objects inside try block
            issues, statuses = candidate_issue_mapper.to_orm_bulk(
                raw_findings,
                analysis_run_id,
            )

            # Flush CandidateIssue rows to DB session (no internal commit)
            if issues:
                await candidate_issue_repository.create_bulk(db, issues)

            # Flush IssueStatus rows to DB session (no internal commit)
            if statuses:
                await issue_status_repository.create_bulk(db, statuses)

            # Fetch & update AnalysisRun metrics and completion state
            analysis_run = await db.get(AnalysisRun, analysis_run_id)
            if analysis_run is None:
                raise ValueError(f"AnalysisRun not found: {analysis_run_id}")

            ast_summary = analysis_result.get("ast_analysis", {}).get("summary", {})
            total_files = ast_summary.get("total_files")
            supported_files = ast_summary.get("supported_files")
            candidate_issues_count = len(issues)

            analysis_run.status = "completed"
            analysis_run.total_files = total_files
            analysis_run.supported_files = supported_files
            analysis_run.candidate_issues_count = candidate_issues_count
            analysis_run.completed_at = datetime.now(timezone.utc)

            # ONE atomic commit for findings + statuses + analysis_run updates
            await db.commit()
            return analysis_run

        except Exception as error:
            # Rollback uncommitted CandidateIssue / IssueStatus / AnalysisRun edits
            await db.rollback()
            # Mark AnalysisRun as failed in a new clean transaction
            await self.record_analysis_failure(
                db,
                analysis_run_id,
                f"Persistence error: {str(error)}",
            )
            raise

    async def record_analysis_failure(
        self,
        db: AsyncSession,
        analysis_run_id: str,
        error_message: str,
    ) -> Optional[AnalysisRun]:
        """
        Record an AnalysisRun failure state in a separate database transaction.
        """
        try:
            await db.rollback()
        except Exception:
            pass

        try:
            analysis_run = await db.get(AnalysisRun, analysis_run_id)
            if analysis_run:
                analysis_run.status = "failed"
                analysis_run.error_message = error_message
                analysis_run.completed_at = datetime.now(timezone.utc)
                await db.commit()
                return analysis_run
        except Exception:
            await db.rollback()
            raise

        return None


# Global instance
repository_analysis_service = RepositoryAnalysisService()
