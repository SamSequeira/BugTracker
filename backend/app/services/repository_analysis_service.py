"""
Repository Analysis Service - Orchestrates the complete analysis pipeline.
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from app.services.ast_generator import ast_generator
from app.services.bug_similarity_service import BugSimilarityService
from app.services.language_detector import detect_language
from app.services.static_analyzer.analyzer import StaticAnalyzer, static_analyzer


logger = logging.getLogger(__name__)


class RepositoryAnalysisService:
    """Orchestrates repository analysis: language detection + AST generation."""

    def __init__(
        self,
        static_analyzer_instance: StaticAnalyzer = static_analyzer,
        similarity_service: Optional[BugSimilarityService] = None,
    ) -> None:
        self._static_analyzer = static_analyzer_instance
        self._similarity_service = similarity_service

    async def analyze_repository(
        self, repo_path: str, repository_id: str
    ) -> Dict[str, Any]:
        """
        Analyze a repository for language detection and AST generation.
        
        Args:
            repo_path: Path to the repository
            
        Returns:
            Comprehensive analysis results
        """
        repo_path = Path(repo_path)
        if not repo_path.exists():
            raise ValueError(f"Repository path not found: {repo_path}")

        # Run analysis in thread pool to avoid blocking
        analysis_result = await asyncio.to_thread(
            ast_generator.generate_ast_for_repository,
            str(repo_path)
        )

        static_analysis = await asyncio.to_thread(
            self._analyze_static_issues,
            analysis_result,
            repository_id,
        )

        return self._format_analysis_result(analysis_result, static_analysis)

    def _analyze_static_issues(
        self, ast_result: Dict[str, Any], repository_id: str
    ) -> Dict[str, Any]:
        """Run synchronous static and similarity analysis outside the event loop."""
        similarity_service = self._similarity_service
        if similarity_service is None:
            try:
                similarity_service = BugSimilarityService()
                self._similarity_service = similarity_service
            except Exception:  # noqa: BLE001 - static findings remain available
                logger.warning(
                    "Similarity service initialization failed for repository=%s",
                    repository_id,
                    exc_info=True,
                )

        return self._static_analyzer.analyze_repository(
            ast_result,
            repository_id=repository_id,
            similarity_service=similarity_service,
        )

    def _format_analysis_result(
        self,
        result: Dict[str, Any],
        static_analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Format analysis results for the API without exposing raw ASTs."""
        return {
            "repository_path": result["repository_path"],
            "summary": {
                "total_files": result["total_files"],
                "supported_files": result["supported_files"],
                "languages": result["languages_detected"],
            },
            "files": [
                {key: value for key, value in file_result.items() if key != "ast"}
                for file_result in result["files_analyzed"]
            ],
            "static_analysis": static_analysis,
        }

    async def analyze_file(self, file_path: str) -> Dict[str, Any]:
        """
        Analyze a single file for language detection and AST generation.
        
        Args:
            file_path: Path to the code file
            
        Returns:
            Analysis results for the file
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


# Global instance
repository_analysis_service = RepositoryAnalysisService()
