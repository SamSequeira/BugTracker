"""
bug_report.py
-------------
Pydantic data schemas for Bug Enrichment and Complete Bug Report Generation.
Standardizes representation across Static Analysis, AST evidence, ML Classification,
Similarity/Deduplication, and API/UI outputs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class EvidenceItem(BaseModel):
    """A single structured piece of supporting evidence from the pipeline."""
    type: str = Field(..., description="Type of evidence: static_analysis, source, ast, classification, similarity")
    description: str = Field(..., description="Human-readable description of this piece of evidence")
    data: Dict[str, Any] = Field(default_factory=dict, description="Structured attributes supporting the claim")

    model_config = ConfigDict(extra="ignore")


class LocationInfo(BaseModel):
    """Precise source code location coordinates."""
    line: int = Field(..., description="1-based line number")
    column: Optional[int] = Field(0, description="0-based column number")
    start_byte: Optional[int] = Field(None, description="Start byte offset")
    end_byte: Optional[int] = Field(None, description="End byte offset")
    start_line: Optional[int] = Field(None, description="0-based or 1-based start line")
    end_line: Optional[int] = Field(None, description="0-based or 1-based end line")

    model_config = ConfigDict(extra="ignore")


class CodeLine(BaseModel):
    """Line of code formatted for UI snippet rendering."""
    num: int = Field(..., description="Line number")
    text: str = Field(..., description="Source code text of line")
    isErr: bool = Field(False, description="Whether this line is flagged as having the error")

    model_config = ConfigDict(extra="ignore")


class CodeContext(BaseModel):
    """Enriched source context including enclosing symbols and surrounding lines."""
    file_path: str = Field(..., description="Relative or absolute file path")
    language: str = Field("Unknown", description="Programming language")
    function_name: Optional[str] = Field(None, description="Enclosing function or method name")
    class_name: Optional[str] = Field(None, description="Enclosing class name")
    snippet: str = Field("", description="Exact code snippet where issue was detected")
    surrounding_code: List[CodeLine] = Field(default_factory=list, description="Surrounding code window")

    model_config = ConfigDict(extra="ignore")


class StaticAnalysisFinding(BaseModel):
    """Preserved static analysis finding information."""
    rule_id: str = Field(..., description="Unique rule ID (e.g. PY_DIV_001)")
    rule_name: Optional[str] = Field(None, description="Human-readable rule name")
    issue_type: str = Field(..., description="Category label")
    message: str = Field(..., description="Analyzer message")
    severity: str = Field("medium", description="Static rule severity")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="AST evidence collected by rule")
    code_snippet: str = Field("", description="Extracted code snippet")

    model_config = ConfigDict(extra="ignore")


class ClassificationResult(BaseModel):
    """Preserved ML classification predictions."""
    category: str = Field(..., description="Predicted bug category/label")
    confidence: float = Field(..., description="Prediction confidence score between 0.0 and 1.0")
    severity_prediction: Dict[str, Any] = Field(default_factory=dict, description="Predicted severity and probabilities")
    priority_prediction: Dict[str, Any] = Field(default_factory=dict, description="Predicted priority and probabilities")
    needs_review: bool = Field(False, description="Flag indicating low confidence below threshold")

    model_config = ConfigDict(extra="ignore")


class SimilarBugMatch(BaseModel):
    """A matched similar or duplicate issue."""
    issue_id: str = Field(..., description="Identifier of the similar issue")
    repository_id: Optional[str] = Field(None, description="Repository identifier")
    similarity: float = Field(0.0, description="Similarity score (0.0 - 1.0)")
    issue_type: Optional[str] = Field(None, description="Issue type / category of match")
    message: Optional[str] = Field(None, description="Message of match")
    file_path: Optional[str] = Field(None, description="File path of match")
    line_number: Optional[int] = Field(None, description="Line number of match")

    model_config = ConfigDict(extra="ignore")


class SimilarityInfo(BaseModel):
    """Similarity and deduplication information."""
    is_duplicate: bool = Field(False, description="Whether this issue is deemed a duplicate")
    duplicate_of: Optional[str] = Field(None, description="ID of primary issue if duplicate")
    highest_similarity: float = Field(0.0, description="Highest similarity score observed")
    relationship_type: str = Field("independent", description="Relationship: duplicate, similar, related, or independent")
    similar_issues: List[SimilarBugMatch] = Field(default_factory=list, description="List of similar bug matches")

    model_config = ConfigDict(extra="ignore")


class SuggestedFix(BaseModel):
    """Remediation and fix suggestion."""
    remove: Optional[str] = Field(None, description="Code lines to remove/replace")
    add: Optional[str] = Field(None, description="Code lines to add")
    note: str = Field("", description="Remediation explanation / guidance")

    model_config = ConfigDict(extra="ignore")


class BugExplanation(BaseModel):
    """Structured human-readable explanation answering all 8 key triage questions."""
    what: str = Field(..., description="1. What is the issue?")
    where: str = Field(..., description="2. Where is it located?")
    why: str = Field(..., description="3. Why was it detected?")
    evidence_summary: str = Field(..., description="4. What evidence supports it?")
    category: str = Field(..., description="5. What category does it belong to?")
    severity_assessment: str = Field(..., description="6. How severe is it?")
    importance_assessment: str = Field(..., description="7. How important is it to fix?")
    similarity_or_duplicate: str = Field(..., description="8. Is it similar or duplicate to another issue?")
    full_text: str = Field("", description="Complete synthesized explanation narrative")

    model_config = ConfigDict(extra="ignore")


class EnrichedBugReport(BaseModel):
    """
    Complete Enriched Bug Report.
    Combines AST context, Static Analysis, Candidate Issue, ML Classification,
    Severity, Priority, Similarity/Deduplication, Evidence Collection, Suggested Fixes,
    and Structured Human-Readable Explanations into a unified model.
    """
    id: str = Field(..., description="Unique bug report identifier")
    issue_id: str = Field(..., description="Stable issue identifier matching ID")
    title: str = Field(..., description="Human-friendly bug report title")
    description: str = Field(..., description="Detailed description of the issue")
    repository: Dict[str, Any] = Field(default_factory=dict, description="Repository identifier and metadata")
    
    file_path: str = Field(..., description="Path to the file containing the bug")
    file: str = Field(..., description="Frontend-friendly alias for file_path")
    line: int = Field(..., description="1-based line number")
    location: LocationInfo = Field(..., description="Structured coordinates")
    language: str = Field("Unknown", description="Programming language")
    
    function_name: Optional[str] = Field(None, description="Enclosing function or method")
    class_name: Optional[str] = Field(None, description="Enclosing class or struct")
    
    category: str = Field(..., description="Bug category")
    severity: str = Field("medium", description="Severity level: critical, high, medium, low")
    priority: str = Field("p3", description="Priority level: p1, p2, p3, p4")
    priority_formatted: str = Field("P3 • Backlog", description="UI display priority (e.g. P1 • Fix now)")
    confidence: float = Field(1.0, description="Overall confidence score (0.0 - 1.0)")
    status: str = Field("Open", description="Lifecycle status: Open, In Review, Resolved, Closed")
    
    static_analysis: StaticAnalysisFinding = Field(..., description="Original static analysis finding")
    candidate_issue: Dict[str, Any] = Field(default_factory=dict, description="Original candidate issue dictionary")
    classification: Optional[ClassificationResult] = Field(None, description="ML classification details if available")
    
    evidence: List[EvidenceItem] = Field(default_factory=list, description="Aggregated structured evidence list")
    similarity: SimilarityInfo = Field(default_factory=SimilarityInfo, description="Similarity & deduplication info")
    similar_issues: List[Dict[str, Any]] = Field(default_factory=list, description="List of similar issue dicts")
    duplicate_of: Optional[str] = Field(None, description="Primary bug ID if this is a duplicate")
    
    codeSnippet: List[CodeLine] = Field(default_factory=list, description="Surrounding code snippet formatted for UI")
    suggestedFix: Optional[SuggestedFix] = Field(None, description="Suggested remediation snippet and diff")
    
    explanation: BugExplanation = Field(..., description="Structured human-readable explanation answering 8 criteria")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")

    model_config = ConfigDict(extra="ignore")


class BugReportSummaryStats(BaseModel):
    """Aggregated summary statistics for a collection of bug reports."""
    total_bugs: int = 0
    total_files_analyzed: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    priority_p1: int = 0
    priority_p2: int = 0
    priority_p3: int = 0
    priority_p4: int = 0
    duplicates_count: int = 0
    categories: Dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class RepositoryBugReportResponse(BaseModel):
    """Complete API response for repository analysis with enriched reports."""
    repository_id: Optional[str] = None
    repository_path: str = ""
    summary_stats: BugReportSummaryStats = Field(default_factory=BugReportSummaryStats)
    ast_analysis: Optional[Dict[str, Any]] = None
    candidate_issues: List[Dict[str, Any]] = Field(default_factory=list)
    total_candidate_issues: int = 0
    bug_reports: List[EnrichedBugReport] = Field(default_factory=list)
    total_reports: int = 0

    model_config = ConfigDict(extra="ignore")
