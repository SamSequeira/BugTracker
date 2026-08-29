"""
technology_repo.py
------------------
Data Access Layer (DAL) repository for AnalysisTechnology entity.
"""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_technology import AnalysisTechnology


class AnalysisTechnologyRepository:
    """Encapsulates database access queries for AnalysisTechnology ORM model."""

    async def create_bulk(
        self,
        db: AsyncSession,
        technologies: List[AnalysisTechnology],
    ) -> List[AnalysisTechnology]:
        """
        Add a list of AnalysisTechnology ORM instances to the session and flush.
        Does NOT commit internally, preserving transaction ownership for the caller.
        """
        if not technologies:
            return []

        db.add_all(technologies)
        await db.flush()
        return technologies

    async def list_by_analysis_run_id(
        self,
        db: AsyncSession,
        analysis_run_id: str,
    ) -> List[AnalysisTechnology]:
        """Retrieve all AnalysisTechnology records associated with a specific analysis run."""
        stmt = (
            select(AnalysisTechnology)
            .where(AnalysisTechnology.analysis_run_id == analysis_run_id)
            .order_by(AnalysisTechnology.category.asc(), AnalysisTechnology.name.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


technology_repository = AnalysisTechnologyRepository()
