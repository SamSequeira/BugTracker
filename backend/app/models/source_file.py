from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data.dbconnection.base import Base

if TYPE_CHECKING:
    from app.models.analysis_run import AnalysisRun
    from app.models.architecture_component import ArchitectureComponent


class SourceFile(Base):
    __tablename__ = "source_files"

    __table_args__ = (
        UniqueConstraint(
            "analysis_run_id",
            "file_path",
            name="uq_source_files_run_file_path",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )

    analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    component_id: Mapped[str | None] = mapped_column(
        ForeignKey("architecture_components.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    file_path: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
    )

    file_name: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    extension: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    language: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    line_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    role: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    intent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_supported: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    analysis_run: Mapped["AnalysisRun"] = relationship(
        "AnalysisRun",
        back_populates="source_files",
    )

    component: Mapped[Optional["ArchitectureComponent"]] = relationship(
        "ArchitectureComponent",
        back_populates="source_files",
    )
