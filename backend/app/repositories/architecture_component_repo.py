"""
architecture_component_repo.py
------------------------------
Data Access Layer (DAL) repository for ArchitectureComponent entity.
"""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.architecture_component import ArchitectureComponent


class ArchitectureComponentRepository:
    """Encapsulates database access queries for ArchitectureComponent ORM model."""

    async def create_bulk(
        self,
        db: AsyncSession,
        components: List[ArchitectureComponent],
    ) -> List[ArchitectureComponent]:
        """
        Add a list of ArchitectureComponent ORM instances to the session and flush.
        Does NOT commit internally, preserving transaction ownership for the caller.
        """
        if not components:
            return []

        db.add_all(components)
        await db.flush()
        return components

    async def get_by_id(
        self,
        db: AsyncSession,
        component_id: str,
    ) -> Optional[ArchitectureComponent]:
        """Retrieve an ArchitectureComponent by its primary key ID."""
        return await db.get(ArchitectureComponent, component_id)

    async def list_by_analysis_run_id(
        self,
        db: AsyncSession,
        analysis_run_id: str,
    ) -> List[ArchitectureComponent]:
        """Retrieve all ArchitectureComponents associated with a specific analysis run."""
        stmt = (
            select(ArchitectureComponent)
            .where(ArchitectureComponent.analysis_run_id == analysis_run_id)
            .order_by(ArchitectureComponent.name.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


architecture_component_repository = ArchitectureComponentRepository()
