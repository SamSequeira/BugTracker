"""
Repository Analysis Service - Orchestrates the complete analysis pipeline.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_run import AnalysisRun
from app.models.candidate_issues import CandidateIssue
from app.models.issue_recommendation import IssueRecommendation
from app.models.issue_status import IssueStatus
from app.models.source_file import SourceFile
from app.repositories.architecture_component_repo import architecture_component_repository
from app.repositories.architecture_summary_repo import architecture_summary_repository
from app.repositories.candidate_issue_repo import candidate_issue_repository
from app.repositories.issue_recommendation_repo import issue_recommendation_repository
from app.repositories.issue_status_repo import issue_status_repository
from app.repositories.source_file_repo import source_file_repository
from app.repositories.technology_repo import technology_repository
from app.services.architecture_detector import architecture_detector
from app.services.architecture_summary_generator import architecture_summary_generator
from app.services.ast_generator import ast_generator
from app.services.candidate_issue_mapper import candidate_issue_mapper
from app.services.candidate_issue_service import candidate_issue_service
from app.services.language_detector import detect_language
from app.services.technology_detector import technology_detector


class RepositoryAnalysisService:
    """Orchestrates repository analysis: language detection + AST + Static Analysis + Topology + Persistence."""

    def __init__(self, similarity_service: Any = None) -> None:
        self.similarity_service = similarity_service

    @staticmethod
    def get_local_repository_path(repository_id: str, repository_name: str) -> Path:
        """Resolve a server-managed workspace path without trusting client input."""
        return Path("repositories") / f"{repository_id}-{repository_name}"

    async def analyze_repository(
        self,
        repo_path: str,
        repository_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze a repository for language detection, AST generation,
        static analysis, candidate issues, and file metadata.
        
        Args:
            repo_path: Path to the repository
            repository_id: Optional repository identifier
            
        Returns:
            Comprehensive analysis results with AST metrics and candidate issues
        """
        from app.services.bug_report_service import bug_report_service
        from app.services.static_analyzer.analyzer import static_analyzer

        repo_path = Path(repo_path)
        if not repo_path.exists():
            raise ValueError(f"Repository path not found: {repo_path}")

        rep_id = repository_id or repo_path.name

        # Run analysis in thread pool to avoid blocking
        # Step 1: Generate AST for all files in repository
        ast_result = await asyncio.to_thread(
            ast_generator.generate_ast_for_repository,
            str(repo_path),
        )

        # Step 2: Run Static Analysis on the complete AST result (with similarity if configured)
        static_analysis_result = await asyncio.to_thread(
            static_analyzer.analyze_repository,
            ast_result,
            rep_id,
            self.similarity_service,
        )

        # Step 3: Run Candidate Issue generation on AST
        candidate_result = await asyncio.to_thread(
            candidate_issue_service.generate_from_repository,
            ast_result,
        )

        # Step 4: Generate Enriched Bug Reports
        reports_result = await asyncio.to_thread(
            bug_report_service.generate_repository_reports,
            ast_result=ast_result,
            candidate_result=candidate_result,
            repository_id=rep_id,
            repository_path=str(repo_path),
        )

        # Step 5: Format AST summary without dumping raw AST trees
        formatted_ast = self._format_analysis_result(ast_result)
        files_summary = [
            {k: v for k, v in f.items() if k != "ast"}
            for f in ast_result.get("files_analyzed", [])
        ]

        response_dict: Dict[str, Any] = {
            "repository_id": rep_id,
            "repository_path": str(repo_path),
            "summary": formatted_ast["summary"],
            "files": files_summary,
            "ast_analysis": formatted_ast,
            "static_analysis": static_analysis_result,
            "candidate_issues": candidate_result.get("candidate_issues", []),
            "total_candidate_issues": candidate_result.get("total_candidate_issues", 0),
            "bug_reports": reports_result.get("bug_reports", []),
            "total_reports": reports_result.get("total_reports", 0),
            "summary_stats": reports_result.get("summary_stats", {}),
            "_files_analyzed": ast_result.get("files_analyzed", []),
            "_ast_result": ast_result,
        }

        return response_dict

    def _format_analysis_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Format AST generation summary for API response without raw AST file trees."""
        return {
            "summary": {
                "total_files": result.get("total_files", 0),
                "supported_files": result.get("supported_files", 0),
                "languages": result.get("languages_detected", {}),
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
            language,
        )

        return result

    async def complete_analysis_run(
        self,
        db: AsyncSession,
        analysis_run_id: str,
        analysis_result: Dict[str, Any],
    ) -> AnalysisRun:
        """
        Persist generated findings across all architecture and topology entities:
        - Technologies (AnalysisTechnology)
        - Components (ArchitectureComponent)
        - SourceFiles (SourceFile with component_id, role, intent)
        - CandidateIssues (CandidateIssue with source_file_id)
        - IssueStatuses (IssueStatus)
        - IssueRecommendations (IssueRecommendation)
        - ArchitectureSummary (ArchitectureSummary)
        - AnalysisRun metrics
        All wrapped in a single atomic database transaction.
        """
        try:
            repo_path_str = analysis_result.get("repository_path", "")
            raw_files = (
                analysis_result.get("_files_analyzed")
                or analysis_result.get("files")
                or analysis_result.get("source_files")
                or []
            )
            if not raw_files and analysis_result.get("candidate_issues"):
                seen_f = set()
                raw_files = []
                for iss in analysis_result.get("candidate_issues", []):
                    fp = iss.get("file_path") or iss.get("file") if isinstance(iss, dict) else getattr(iss, "file_path", None)
                    if fp and fp not in seen_f:
                        seen_f.add(fp)
                        raw_files.append({"file_path": fp})

            # ----------------------------------------------------
            # 1. Technology Stack Detection & Persistence
            # ----------------------------------------------------
            ast_summary_raw = analysis_result.get("_ast_result") or analysis_result.get("ast_analysis", {}).get("summary")
            technologies = technology_detector.detect_technologies(
                repo_path=repo_path_str,
                analysis_run_id=analysis_run_id,
                ast_result=ast_summary_raw if isinstance(ast_summary_raw, dict) else None,
            )
            if technologies:
                await technology_repository.create_bulk(db, technologies)

            # ----------------------------------------------------
            # 2. Architecture Component Detection & Persistence
            # ----------------------------------------------------
            components, file_comp_meta = architecture_detector.detect_components(
                repo_path=repo_path_str,
                analysis_run_id=analysis_run_id,
                files_data=raw_files,
            )
            if components:
                await architecture_component_repository.create_bulk(db, components)

            # ----------------------------------------------------
            # 3. SourceFile Preservation & Component Linking
            # ----------------------------------------------------
            source_files: List[SourceFile] = []
            source_file_map: Dict[str, str] = {}
            seen_paths = set()

            for file_info in raw_files:
                if isinstance(file_info, SourceFile):
                    source_files.append(file_info)
                    source_file_map[file_info.file_path] = file_info.id
                    continue

                fpath = file_info.get("file") or file_info.get("file_path") or ""
                if not fpath or fpath in seen_paths:
                    continue

                seen_paths.add(fpath)
                sf_id = str(uuid.uuid4())
                p = Path(fpath)
                fname = file_info.get("file_name") or p.name
                ext = file_info.get("extension") or p.suffix or None
                lang = file_info.get("language") or "Unknown"
                line_count = file_info.get("line_count")
                is_supported = file_info.get("is_supported", file_info.get("success", True))

                # Lookup topology classification
                comp_info = file_comp_meta.get(fpath) or file_comp_meta.get(p.as_posix()) or {}
                component_id = file_info.get("component_id") or comp_info.get("component_id")
                role = file_info.get("role") or comp_info.get("role")
                intent = file_info.get("intent") or comp_info.get("intent")

                source_file = SourceFile(
                    id=sf_id,
                    analysis_run_id=analysis_run_id,
                    component_id=component_id,
                    file_path=fpath,
                    file_name=fname,
                    extension=ext,
                    language=lang,
                    line_count=line_count,
                    role=role,
                    intent=intent,
                    is_supported=is_supported,
                )
                source_files.append(source_file)

                # Populate path lookups for linking candidate issues
                source_file_map[fpath] = sf_id
                source_file_map[p.as_posix()] = sf_id
                source_file_map[fpath.replace("\\", "/")] = sf_id
                if repo_path_str:
                    try:
                        rel = p.relative_to(Path(repo_path_str)).as_posix()
                        source_file_map[rel] = sf_id
                    except Exception:
                        pass

            # Flush SourceFile rows
            if source_files:
                await source_file_repository.create_bulk(db, source_files)

            # ----------------------------------------------------
            # 4. CandidateIssue, IssueStatus, IssueRecommendation
            # ----------------------------------------------------
            raw_findings = analysis_result.get("candidate_issues", [])

            if hasattr(candidate_issue_mapper, "to_orm_bulk_with_relations"):
                issues, statuses, recommendations = candidate_issue_mapper.to_orm_bulk_with_relations(
                    raw_findings,
                    analysis_run_id,
                    source_file_map=source_file_map,
                )
            else:
                issues = []
                statuses = []
                recommendations = []
                for finding in raw_findings:
                    fpath = finding.file_path if hasattr(finding, "file_path") else finding.get("file_path", "")
                    sf_id = None
                    if source_file_map and fpath:
                        sf_id = (
                            source_file_map.get(fpath)
                            or source_file_map.get(Path(fpath).as_posix())
                            or source_file_map.get(fpath.replace("\\", "/"))
                        )
                    issue_id = str(uuid.uuid4())
                    rule_id = getattr(finding, "rule_id", None) or (finding.get("rule_id") if isinstance(finding, dict) else None)
                    issue_type = getattr(finding, "issue_type", "unknown_issue") if hasattr(finding, "issue_type") else (finding.get("issue_type", "unknown_issue") if isinstance(finding, dict) else "unknown_issue")
                    message = getattr(finding, "message", "") if hasattr(finding, "message") else (finding.get("message", "") if isinstance(finding, dict) else "")
                    code_snippet = getattr(finding, "code_snippet", None) if hasattr(finding, "code_snippet") else (finding.get("code_snippet") if isinstance(finding, dict) else None)
                    sev = (getattr(finding, "severity", "medium") or "medium").lower() if hasattr(finding, "severity") else ((finding.get("severity", "medium") or "medium").lower() if isinstance(finding, dict) else "medium")
                    urgency = "high" if sev == "high" else ("low" if sev == "low" else "medium")
                    title = f"{issue_type.replace('_', ' ').title()} ({rule_id})" if rule_id else issue_type.replace('_', ' ').title()
                    desc = f"{message}\n\nCode Snippet:\n{code_snippet}" if code_snippet else message

                    issue_orm = CandidateIssue(
                        id=issue_id,
                        analysis_run_id=analysis_run_id,
                        source_file_id=sf_id,
                        rule_id=rule_id,
                        title=title,
                        description=desc,
                        code_snippet=code_snippet,
                        file_path=fpath,
                        line_number=getattr(finding, "line_number", None) if hasattr(finding, "line_number") else (finding.get("line_number") if isinstance(finding, dict) else None),
                        severity=sev,
                        urgency=urgency,
                    )
                    status_orm = IssueStatus(
                        id=str(uuid.uuid4()),
                        candidate_issue_id=issue_id,
                        status="open",
                    )
                    issues.append(issue_orm)
                    statuses.append(status_orm)

                    # Extract recommendations if present
                    recs_data = finding.get("recommendations", []) if isinstance(finding, dict) else getattr(finding, "recommendations", [])
                    if recs_data:
                        for idx, r in enumerate(recs_data, 1):
                            r_text = r.get("recommendation") if isinstance(r, dict) else str(r)
                            diff_rem = r.get("diff_remove") if isinstance(r, dict) else None
                            diff_ad = r.get("diff_add") if isinstance(r, dict) else None
                            fix_tp = r.get("fix_type", "code_patch" if diff_ad else "suggestion") if isinstance(r, dict) else "suggestion"
                            p_order = r.get("priority_order", idx) if isinstance(r, dict) else idx
                            recommendations.append(
                                IssueRecommendation(
                                    id=str(uuid.uuid4()),
                                    candidate_issue_id=issue_id,
                                    recommendation=r_text,
                                    diff_remove=diff_rem,
                                    diff_add=diff_ad,
                                    priority_order=p_order,
                                    fix_type=fix_tp,
                                )
                            )
                    elif isinstance(finding, dict) and (finding.get("recommendation") or finding.get("diff_add") or finding.get("suggested_fix")):
                        rec_text = str(finding.get("recommendation") or finding.get("suggested_fix") or "Apply code patch")
                        recommendations.append(
                            IssueRecommendation(
                                id=str(uuid.uuid4()),
                                candidate_issue_id=issue_id,
                                recommendation=rec_text,
                                diff_remove=finding.get("diff_remove"),
                                diff_add=finding.get("diff_add"),
                                priority_order=1,
                                fix_type=finding.get("fix_type", "code_patch" if finding.get("diff_add") else "suggestion"),
                            )
                        )

            # Flush CandidateIssue rows
            if issues:
                await candidate_issue_repository.create_bulk(db, issues)

            # Flush IssueStatus rows
            if statuses:
                await issue_status_repository.create_bulk(db, statuses)

            # Flush IssueRecommendation rows
            if recommendations:
                await issue_recommendation_repository.create_bulk(db, recommendations)

            # ----------------------------------------------------
            # 5. Architecture Summary Generation & Persistence
            # ----------------------------------------------------
            arch_summary = architecture_summary_generator.generate_summary(
                analysis_run_id=analysis_run_id,
                technologies=technologies,
                components=components,
                source_files=source_files,
                candidate_issues=issues,
            )
            await architecture_summary_repository.create_or_update(
                db, arch_summary
            )

            # ----------------------------------------------------
            # 6. Update AnalysisRun Metrics
            # ----------------------------------------------------
            analysis_run = await db.get(AnalysisRun, analysis_run_id)
            if analysis_run is None:
                raise ValueError(f"AnalysisRun not found: {analysis_run_id}")

            ast_summary = (
                analysis_result.get("ast_analysis", {}).get("summary")
                or analysis_result.get("summary", {})
            )
            total_files = ast_summary.get("total_files") if ast_summary.get("total_files") is not None else len(source_files)
            supported_files = ast_summary.get("supported_files") if ast_summary.get("supported_files") is not None else sum(1 for sf in source_files if sf.is_supported)
            candidate_issues_count = len(issues)

            analysis_run.status = "completed"
            analysis_run.total_files = total_files
            analysis_run.supported_files = supported_files
            analysis_run.candidate_issues_count = candidate_issues_count
            analysis_run.completed_at = datetime.now(timezone.utc)

            # ONE atomic commit for all architecture, topology, findings, and analysis_run updates
            await db.commit()
            return analysis_run

        except Exception as error:
            # Rollback uncommitted entities on failure
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
