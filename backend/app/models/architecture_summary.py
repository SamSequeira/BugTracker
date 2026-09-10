from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data.dbconnection.base import Base

if TYPE_CHECKING:
    from app.models.analysis_run import AnalysisRun


class ArchitectureSummary(Base):
    __tablename__ = "architecture_summaries"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )

    analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    intent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    architecture_overview: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    health_assessment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    parser_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    analysis_run: Mapped["AnalysisRun"] = relationship(
        "AnalysisRun",
        back_populates="architecture_summary",
    )
