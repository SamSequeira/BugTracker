from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


VerifiedSeverityType = Literal["critical", "high", "medium", "low"]
VerifiedPriorityType = Literal["p1", "p2", "p3", "p4"]
VerificationStatusFilter = Literal["all", "unverified", "partial", "verified"]


class CandidateIssueLabelUpdate(BaseModel):
    """
    Schema for manually assigning or updating verified ground-truth labels.
    Supports partial updates (only severity, only priority, or both) and explicit false positive marking.
    """
    verified_severity: Optional[VerifiedSeverityType] = Field(
        default=None,
        description="Ground-truth verified severity: critical, high, medium, low",
    )
    verified_priority: Optional[VerifiedPriorityType] = Field(
        default=None,
        description="Ground-truth verified priority: p1, p2, p3, p4",
    )
    verification_notes: Optional[str] = Field(
        default=None,
        description="Optional human reviewer notes explaining the verification rationale",
    )
    is_false_positive: Optional[bool] = Field(
        default=None,
        description="Explicit flag to mark candidate issue as a false positive without assigning training labels",
    )

    @model_validator(mode="after")
    def validate_false_positive_and_labels(self) -> CandidateIssueLabelUpdate:
        if self.is_false_positive:
            if self.verified_severity is not None or self.verified_priority is not None:
                raise ValueError("False positive candidate issues must NOT have verified_severity or verified_priority assigned.")
        return self


class ReviewBatchRequest(BaseModel):
    """Configuration for deterministic review sampling across languages, repositories, and rules."""
    target_size: int = Field(default=200, ge=10, le=1000, description="Target number of diverse review candidates")
    random_seed: int = Field(default=42, description="Random seed for deterministic sampling")
    max_per_rule_per_repo: int = Field(default=25, ge=1, le=100, description="Max items from any single (repo, rule) stratum")


class ReviewBatchItem(BaseModel):
    """Contextual item in a review batch for human evaluation."""
    id: str
    analysis_run_id: str
    repository_id: str
    repository_name: str
    language: str
    rule_id: str
    issue_type: str
    file_path: str
    line_number: Optional[int] = None
    column: Optional[int] = None
    code_snippet: Optional[str] = None
    message: str
    description: str
    evidence: Dict[str, Any]
    severity: str  # Baseline detector prediction
    urgency: str   # Baseline detector urgency
    confidence: Optional[str] = "medium"  # Static rule confidence: high, medium, low
    verified_severity: Optional[str] = None
    verified_priority: Optional[str] = None
    verified_at: Optional[datetime] = None
    verification_notes: Optional[str] = None


class ReviewBatchResponse(BaseModel):
    """Response containing deterministically sampled review batch and diversity metrics."""
    total_available_unverified_real: int
    sampled_count: int
    seed: int
    strata_count: int
    repositories_distribution: Dict[str, int]
    languages_distribution: Dict[str, int]
    rules_distribution: Dict[str, int]
    issue_types_distribution: Dict[str, int]
    items: List[ReviewBatchItem]


class CandidateIssueResponse(BaseModel):
    """
    Full representation of a Candidate Issue entity.
    Maintains strict separation between detector prediction (severity) and verified ground truth.
    """
    id: str
    analysis_run_id: str

    title: str
    description: str

    file_path: str
    line_number: Optional[int] = None
    column: Optional[int] = None

    rule_id: Optional[str] = None
    issue_type: Optional[str] = None
    message: Optional[str] = None
    code_snippet: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None
    confidence: Optional[str] = "medium"
    language: Optional[str] = None

    # Static analyzer detector prediction (baseline)
    severity: str
    urgency: str

    # Manually verified ground truth
    verified_severity: Optional[str] = None
    verified_priority: Optional[str] = None
    verified_at: Optional[datetime] = None
    verification_notes: Optional[str] = None

    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )



class VerifiedTrainingRecord(BaseModel):
    """
    Export record explicitly formatted for DistilBERT training.
    - 'severity' maps to verified_severity (ground truth target)
    - 'priority' maps to verified_priority (ground truth target)
    - 'detector_severity' preserves original analyzer output for evaluation/comparison
    """
    id: str
    analysis_run_id: str
    language: str
    rule_id: str
    issue_type: str
    message: str
    file_path: str
    line_number: Optional[int] = None
    column: Optional[int] = None
    code_snippet: str
    evidence: Dict[str, Any]

    detector_severity: str
    severity: str  # Ground-truth target (from verified_severity)
    priority: str  # Ground-truth target (from verified_priority)

    verified_at: Optional[datetime] = None
    verification_notes: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True
    )


class CandidateIssueListResponse(BaseModel):
    total: int
    items: List[CandidateIssueResponse]


class VerifiedDatasetResponse(BaseModel):
    total: int
    records: List[VerifiedTrainingRecord]


class DatasetStatsResponse(BaseModel):
    """
    Dataset collection and labeling progress statistics.
    Severity and priority distributions count ONLY fully verified records.
    """
    total_candidate_issues: int
    unverified: int
    false_positives: Optional[int] = 0
    partially_verified: int
    fully_verified: int
    severity_distribution: Dict[str, int]
    priority_distribution: Dict[str, int]
    provenance_breakdown: Optional[Dict[str, int]] = None
    diversity_counts: Optional[Dict[str, int]] = None
    crosstab: Optional[Dict[str, int]] = None
    readiness_summary: Optional[Dict[str, Any]] = None


class DatasetReadinessResponse(BaseModel):
    """
    Full readiness evaluation scorecard against DistilBERT training prerequisites.
    """
    total_candidate_issues_in_db: int
    unique_verified_records: int
    readiness: Dict[str, Any]
    provenance_breakdown: Dict[str, int]
    missingness_statistics: Dict[str, int]
    severity_distribution: Dict[str, Any]
    priority_distribution: Dict[str, Any]


class DuplicateGroup(BaseModel):
    """
    Cluster of candidate issues sharing identical signature (rule_id, file_path, line_number, code_snippet).
    """
    rule_id: Optional[str] = None
    file_path: str
    line_number: Optional[int] = None
    code_snippet: Optional[str] = None
    count: int
    issue_ids: List[str]
    issues: List[CandidateIssueResponse]


class DuplicateIssuesResponse(BaseModel):
    """Response model for potential duplicate candidate issues check."""
    total_duplicate_groups: int
    total_duplicate_issues: int
    groups: List[DuplicateGroup]


class DatasetPrepareRequest(BaseModel):
    """
    Configuration for dataset quality validation, deduplication, feature building,
    and stratified group splitting.
    """
    dataset_version: str = Field(default="dataset_v1", description="Unique version identifier for the dataset")
    random_seed: int = Field(default=42, description="Random seed for reproducible splitting")
    train_ratio: float = Field(default=0.70, ge=0.1, le=0.9, description="Ratio for training set")
    validation_ratio: float = Field(default=0.15, ge=0.05, le=0.5, description="Ratio for validation set")
    test_ratio: float = Field(default=0.15, ge=0.05, le=0.5, description="Ratio for test set")
    min_samples_per_class: int = Field(default=1, ge=1, description="Minimum samples threshold for class warnings")
    export_dir: Optional[str] = Field(default=None, description="Custom export directory, defaults to data/prepared/{dataset_version}")
    overwrite: bool = Field(default=False, description="Whether to overwrite existing dataset version if it already exists")


class DatasetPrepareResponse(BaseModel):
    """
    Response returned upon dataset preparation and export.
    """
    dataset_version: str
    status: str
    export_directory: str
    total_verified_records: int
    records_after_deduplication: int
    train_records: int
    validation_records: int
    test_records: int
    quality_report: Dict[str, Any]
    metadata: Dict[str, Any]


class SourceContextLine(BaseModel):
    line_number: int
    content: str
    is_target: bool


class SourceContextResponse(BaseModel):
    """
    Structured response for source context surrounding a candidate issue.
    """
    issue_id: str
    found: bool
    message: str
    formatted_text: str
    file_path: str
    line_number: Optional[int] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    total_lines: Optional[int] = None
    lines: List[SourceContextLine] = Field(default_factory=list)
