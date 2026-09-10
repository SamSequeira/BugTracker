from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data.dbconnection.base import Base

if TYPE_CHECKING:
    from app.models.candidate_issues import CandidateIssue


class IssueSimilarity(Base):
    __tablename__ = "issue_similarities"

    __table_args__ = (
        UniqueConstraint(
            "candidate_issue_id",
            "similar_issue_id",
            name="uq_issue_similarities_pair",
        ),
        CheckConstraint(
            "candidate_issue_id < similar_issue_id",
            name="ck_issue_similarities_canonical_pair",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )

    candidate_issue_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_issues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    similar_issue_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_issues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    similarity_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    similarity_reason: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    candidate_issue: Mapped["CandidateIssue"] = relationship(
        "CandidateIssue",
        foreign_keys=[candidate_issue_id],
        back_populates="similar_issues_from",
    )

    similar_issue: Mapped["CandidateIssue"] = relationship(
        "CandidateIssue",
        foreign_keys=[similar_issue_id],
        back_populates="similar_issues_to",
    )
