"""
issue_recommendation_repo.py
----------------------------
Data Access Layer (DAL) repository for IssueRecommendation entity.
"""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.issue_recommendation import IssueRecommendation


class IssueRecommendationRepository:
    """Encapsulates database access queries for IssueRecommendation ORM model."""

    async def create_bulk(
        self,
        db: AsyncSession,
        recommendations: List[IssueRecommendation],
    ) -> List[IssueRecommendation]:
        """
        Add a list of IssueRecommendation ORM instances to the session and flush.
        Does NOT commit internally, preserving transaction ownership for the service.
        """
        if not recommendations:
            return []

        db.add_all(recommendations)
        await db.flush()
        return recommendations

    async def get_by_id(
        self,
        db: AsyncSession,
        recommendation_id: str,
    ) -> Optional[IssueRecommendation]:
        """Retrieve an IssueRecommendation by its primary key ID."""
        return await db.get(IssueRecommendation, recommendation_id)

    async def list_by_candidate_issue_id(
        self,
        db: AsyncSession,
        candidate_issue_id: str,
    ) -> List[IssueRecommendation]:
        """Retrieve all recommendations for a candidate issue ordered by priority."""
        stmt = (
            select(IssueRecommendation)
            .where(IssueRecommendation.candidate_issue_id == candidate_issue_id)
            .order_by(IssueRecommendation.priority_order.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


issue_recommendation_repository = IssueRecommendationRepository()
