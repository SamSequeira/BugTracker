from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data.dbconnection.base import Base

if TYPE_CHECKING:
    from app.models.candidate_issues import CandidateIssue
    from app.models.user import User


class IssueStatus(Base):
    __tablename__ = "issue_statuses"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )

    candidate_issue_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_issues.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="open",
    )

    remarks: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    resolved_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    candidate_issue: Mapped["CandidateIssue"] = relationship(
        "CandidateIssue",
        back_populates="status",
    )

    resolved_by: Mapped[Optional["User"]] = relationship(
        "User",
    )