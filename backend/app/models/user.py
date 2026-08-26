from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data.dbconnection.base import Base

if TYPE_CHECKING:
    from app.models.candidate_issues import CandidateIssue
    from app.models.issue_status import IssueStatus
    from app.models.repository import Repository


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String,
        unique=True,
        index=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    repositories: Mapped[List["Repository"]] = relationship(
        "Repository",
        back_populates="user",
    )

    assigned_issues: Mapped[List["CandidateIssue"]] = relationship(
        "CandidateIssue",
        back_populates="assigned_to",
    )

    resolved_issue_statuses: Mapped[List["IssueStatus"]] = relationship(
        "IssueStatus",
        back_populates="resolved_by",
    )
