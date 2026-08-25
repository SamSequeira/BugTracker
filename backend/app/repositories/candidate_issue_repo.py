"""
candidate_issue_repo.py
------------------------
Data Access Layer (DAL) repository for CandidateIssue entity.
"""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate_issues import CandidateIssue


class CandidateIssueRepository:
    """Encapsulates database access queries for CandidateIssue ORM model."""

    async def create_bulk(
        self,
        db: AsyncSession,
        issues: List[CandidateIssue],
    ) -> List[CandidateIssue]:
        """
        Add a list of CandidateIssue ORM instances to the session and flush/commit.
        """
        if not issues:
            return []

        db.add_all(issues)
        await db.flush()
        return issues

    async def get_by_id(
        self,
        db: AsyncSession,
        issue_id: str,
    ) -> Optional[CandidateIssue]:
        """Retrieve a CandidateIssue by its primary key ID."""
        return await db.get(CandidateIssue, issue_id)

    async def list_by_analysis_run_id(
        self,
        db: AsyncSession,
        analysis_run_id: str,
    ) -> List[CandidateIssue]:
        """Retrieve all CandidateIssues associated with a specific analysis run."""
        stmt = (
            select(CandidateIssue)
            .where(CandidateIssue.analysis_run_id == analysis_run_id)
            .order_by(CandidateIssue.created_at.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


candidate_issue_repository = CandidateIssueRepository()
