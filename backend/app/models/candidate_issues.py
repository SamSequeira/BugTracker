from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data.dbconnection.base import Base

if TYPE_CHECKING:
    from app.models.analysis_run import AnalysisRun
    from app.models.issue_recommendation import IssueRecommendation
    from app.models.issue_similarity import IssueSimilarity
    from app.models.issue_status import IssueStatus
    from app.models.source_file import SourceFile
    from app.models.user import User


class CandidateIssue(Base):
    __tablename__ = "candidate_issues"

    __table_args__ = (
        UniqueConstraint(
            "analysis_run_id",
            "issue_key",
            name="uq_candidate_issues_run_issue_key",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )

    issue_key: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    rule_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
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

    assigned_to_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
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

    security_impact: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    code_snippet: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
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

    severity: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
    )

    urgency: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    analysis_run: Mapped["AnalysisRun"] = relationship(
        "AnalysisRun",
        back_populates="candidate_issues",
    )

    source_file: Mapped[Optional["SourceFile"]] = relationship(
        "SourceFile",
        back_populates="candidate_issues",
    )

    assigned_to: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="assigned_issues",
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