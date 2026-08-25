from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from data.dbconnection.base import Base


class IssueStatus(Base):
    __tablename__ = "issue_statuses"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )

    candidate_issue_id: Mapped[str] = mapped_column(
        ForeignKey("candidate_issues.id"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="open",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )