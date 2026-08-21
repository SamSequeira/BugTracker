"""
Repository Analysis Service - Orchestrates the complete analysis pipeline.
"""

import asyncio
from pathlib import Path
from typing import Dict, Any

from app.services.ast_generator import ast_generator
from app.services.language_detector import detect_language
from app.services.candidate_issue_service import (
    candidate_issue_service
)

class RepositoryAnalysisService:
    """Orchestrates repository analysis: language detection + AST generation."""

    async def analyze_repository(self, repo_path: str) -> Dict[str, Any]:
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
        # Step 1: Generate AST
        ast_result = await asyncio.to_thread(
            ast_generator.generate_ast_for_repository,
            str(repo_path)
        )

        # Step 2: Run Static Analysis
        candidate_result = await asyncio.to_thread(
            candidate_issue_service.generate_from_repository,
            ast_result
        )

        return {
            "repository_path": str(repo_path),
            "ast_analysis": self._format_analysis_result(ast_result),
            "candidate_issues": candidate_result["candidate_issues"],
            "total_candidate_issues": candidate_result["total_candidate_issues"],
        }

    def _format_analysis_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Format AST generation results for API response."""
        return {
            "repository_path": result["repository_path"],
            "summary": {
                "total_files": result["total_files"],
                "supported_files": result["supported_files"],
                "languages": result["languages_detected"],
            },
            "files": result["files_analyzed"],
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
