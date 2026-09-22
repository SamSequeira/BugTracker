from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data.dbconnection.base import Base

if TYPE_CHECKING:
    from app.models.analysis_run import AnalysisRun
    from app.models.issue_recommendation import IssueRecommendation
    from app.models.issue_similarity import IssueSimilarity
    from app.models.issue_status import IssueStatus


class CandidateIssue(Base):
    __tablename__ = "candidate_issues"

    __table_args__ = (
        CheckConstraint(
            "verified_severity IS NULL OR verified_severity IN ('high', 'medium', 'low')",
            name="ck_candidate_issues_verified_severity",
        ),
        CheckConstraint(
            "verified_priority IS NULL OR verified_priority IN ('p1', 'p2', 'p3', 'p4')",
            name="ck_candidate_issues_verified_priority",
        ),
        Index(
            "ix_candidate_issues_verified_labels",
            "verified_severity",
            "verified_priority",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )

    analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_runs.id"),
        nullable=False,
        index=True,
    )

    source_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_files.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    file_path: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
    )

    line_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    column: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    severity: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
    )

    urgency: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    rule_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    issue_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    code_snippet: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    evidence: Mapped[Dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    issue_key: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    security_impact: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    assigned_to_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    language: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    # Verified ground-truth labels (assigned manually)
    verified_severity: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    verified_priority: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    verification_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    analysis_run: Mapped["AnalysisRun"] = relationship(
        "AnalysisRun",
        back_populates="candidate_issues",
    )

    status: Mapped[Optional["IssueStatus"]] = relationship(
        "IssueStatus",
        back_populates="candidate_issue",
        uselist=False,
        cascade="all, delete-orphan",
    )

    recommendations: Mapped[List["IssueRecommendation"]] = relationship(
        "IssueRecommendation",
        back_populates="candidate_issue",
        cascade="all, delete-orphan",
    )

    similar_issues_from: Mapped[List["IssueSimilarity"]] = relationship(
        "IssueSimilarity",
        foreign_keys="[IssueSimilarity.candidate_issue_id]",
        back_populates="candidate_issue",
        cascade="all, delete-orphan",
    )

    similar_issues_to: Mapped[List["IssueSimilarity"]] = relationship(
        "IssueSimilarity",
        foreign_keys="[IssueSimilarity.similar_issue_id]",
        back_populates="similar_issue",
        cascade="all, delete-orphan",
    )