"""
issue_status_repo.py
--------------------
Data Access Layer (DAL) repository for IssueStatus entity.
"""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.issue_status import IssueStatus


class IssueStatusRepository:
    """Encapsulates database access queries for IssueStatus ORM model."""

    async def create_bulk(
        self,
        db: AsyncSession,
        statuses: List[IssueStatus],
    ) -> List[IssueStatus]:
        """
        Add a list of IssueStatus ORM instances to the session and flush.
        Does NOT commit internally, preserving transaction ownership for the service.
        """
        if not statuses:
            return []

        db.add_all(statuses)
        await db.flush()

        return statuses

    async def get_by_candidate_issue_id(
        self,
        db: AsyncSession,
        candidate_issue_id: str,
    ) -> Optional[IssueStatus]:
        """Retrieve the IssueStatus for a specific CandidateIssue ID."""
        stmt = select(IssueStatus).where(
            IssueStatus.candidate_issue_id == candidate_issue_id
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def update_status(
        self,
        db: AsyncSession,
        candidate_issue_id: str,
        new_status: str,
    ) -> Optional[IssueStatus]:
        """Update the lifecycle status of a candidate issue."""
        issue_status = await self.get_by_candidate_issue_id(db, candidate_issue_id)
        if issue_status is None:
            return None

        issue_status.status = new_status
        await db.flush()
        return issue_status


issue_status_repository = IssueStatusRepository()
