from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data.dbconnection.base import Base

if TYPE_CHECKING:
    from app.models.candidate_issues import CandidateIssue


class IssueRecommendation(Base):
    __tablename__ = "issue_recommendations"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )

    candidate_issue_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_issues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    recommendation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    diff_remove: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    diff_add: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    priority_order: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    fix_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    candidate_issue: Mapped["CandidateIssue"] = relationship(
        "CandidateIssue",
        back_populates="recommendations",
    )
