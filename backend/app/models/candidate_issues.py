from datetime import datetime

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from data.dbconnection.base import Base


class CandidateIssue(Base):
    __tablename__ = "candidate_issues"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )

    analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_runs.id"),
        nullable=False,
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
    )

    line_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    severity: Mapped[str] = mapped_column(
    String,
    nullable=False,
    )

    urgency: Mapped[str] = mapped_column(
    String,
    nullable=False,
)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )