"""
architecture_summary_repo.py
----------------------------
Data Access Layer (DAL) repository for ArchitectureSummary entity.
"""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.architecture_summary import ArchitectureSummary


class ArchitectureSummaryRepository:
    """Encapsulates database access queries for ArchitectureSummary ORM model."""

    async def create_or_update(
        self,
        db: AsyncSession,
        summary: ArchitectureSummary,
    ) -> ArchitectureSummary:
        """
        Add or update an ArchitectureSummary ORM instance in the session and flush.
        Does NOT commit internally, preserving transaction ownership for the caller.
        """
        existing = await self.get_by_analysis_run_id(db, summary.analysis_run_id)
        if existing:
            existing.intent = summary.intent
            existing.architecture_overview = summary.architecture_overview
            existing.health_assessment = summary.health_assessment
            existing.parser_version = summary.parser_version
            await db.flush()
            return existing

        db.add(summary)
        await db.flush()
        return summary

    async def get_by_analysis_run_id(
        self,
        db: AsyncSession,
        analysis_run_id: str,
    ) -> Optional[ArchitectureSummary]:
        """Retrieve the ArchitectureSummary for a specific analysis run."""
        stmt = select(ArchitectureSummary).where(
            ArchitectureSummary.analysis_run_id == analysis_run_id
        )
        result = await db.execute(stmt)
        return result.scalars().first()


architecture_summary_repository = ArchitectureSummaryRepository()
