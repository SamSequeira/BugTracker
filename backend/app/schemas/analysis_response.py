"""
analysis_response.py
---------------------
Pydantic response schema for the repository analysis endpoint.

These schemas describe the exact shape of the JSON returned by
POST /api/v1/repositories/analyze/{repository_id} so that FastAPI
can generate a valid OpenAPI spec and Swagger UI can render the response.
"""

from typing import Any, Dict, List
from pydantic import BaseModel


class CandidateIssueFinding(BaseModel):
    """A single static-analysis finding as returned by the analyzer.
    Matches CandidateIssue.to_dict() in app/services/static_analyzer/models.py.
    """
    rule_id: str
    issue_type: str
    message: str
    file_path: str
    line_number: int
    column: int
    code_snippet: str
    evidence: Dict[str, Any] = {}
    severity: str


class AstSummary(BaseModel):
    """Matches the 'summary' key produced by _format_analysis_result().
    languages is a dict mapping language name -> file count,
    e.g. {"Python": 72, "JavaScript": 17}.
    Sourced from ast_generator.generate_ast_for_repository()['languages_detected'].
    """
    total_files: int
    supported_files: int
    languages: Dict[str, int]


class AstAnalysis(BaseModel):
    """Matches the 'ast_analysis' key produced by _format_analysis_result().
    Contains repository-level AST summary metrics without dumping raw AST trees.
    """
    summary: AstSummary


class AnalysisResult(BaseModel):
    """Matches the dict returned by RepositoryAnalysisService.analyze_repository()."""
    repository_path: str
    ast_analysis: AstAnalysis
    candidate_issues: List[CandidateIssueFinding]
    total_candidate_issues: int


class AnalyzeRepositoryResponse(BaseModel):
    """Top-level response for POST /api/v1/repositories/analyze/{repository_id}."""
    repository_id: str
    analysis_run_id: str
    message: str
    analysis: AnalysisResult
