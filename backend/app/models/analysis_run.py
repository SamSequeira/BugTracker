from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data.dbconnection.base import Base

if TYPE_CHECKING:
    from app.models.analysis_technology import AnalysisTechnology
    from app.models.architecture_component import ArchitectureComponent
    from app.models.architecture_summary import ArchitectureSummary
    from app.models.candidate_issues import CandidateIssue
    from app.models.repository import Repository
    from app.models.source_file import SourceFile


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )

    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="pending",
    )

    total_files: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    supported_files: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    candidate_issues_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    repository: Mapped["Repository"] = relationship(
        "Repository",
        back_populates="analysis_runs",
    )

    candidate_issues: Mapped[List["CandidateIssue"]] = relationship(
        "CandidateIssue",
        back_populates="analysis_run",
        cascade="all, delete-orphan",
    )

    architecture_summary: Mapped[Optional["ArchitectureSummary"]] = relationship(
        "ArchitectureSummary",
        back_populates="analysis_run",
        uselist=False,
        cascade="all, delete-orphan",
    )

    technologies: Mapped[List["AnalysisTechnology"]] = relationship(
        "AnalysisTechnology",
        back_populates="analysis_run",
        cascade="all, delete-orphan",
    )

    components: Mapped[List["ArchitectureComponent"]] = relationship(
        "ArchitectureComponent",
        back_populates="analysis_run",
        cascade="all, delete-orphan",
    )

    source_files: Mapped[List["SourceFile"]] = relationship(
        "SourceFile",
        back_populates="analysis_run",
        cascade="all, delete-orphan",
    )