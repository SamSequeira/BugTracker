from datetime import datetime
from typing import Any, Dict, Optional

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
from sqlalchemy.orm import Mapped, mapped_column

from data.dbconnection.base import Base


class CandidateIssue(Base):
    __tablename__ = "candidate_issues"

    __table_args__ = (
        CheckConstraint(
            "verified_severity IS NULL OR verified_severity IN ('critical', 'high', 'medium', 'low')",
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
    )

    # Human-readable title and description (legacy / UI compatibility)
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
    )

    line_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    column: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Static analysis metadata
    rule_id: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        index=True,
    )

    issue_type: Mapped[str | None] = mapped_column(
        String,
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

    language: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        index=True,
    )

    # Detector prediction (original static analyzer severity)
    severity: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    urgency: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    # Verified ground-truth labels (assigned manually)
    verified_severity: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    verified_priority: Mapped[str | None] = mapped_column(
        String,
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