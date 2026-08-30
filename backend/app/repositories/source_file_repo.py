"""
source_file_repo.py
-------------------
Data Access Layer (DAL) repository for SourceFile entity.
"""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source_file import SourceFile


class SourceFileRepository:
    """Encapsulates database access queries for SourceFile ORM model."""

    async def create_bulk(
        self,
        db: AsyncSession,
        source_files: List[SourceFile],
    ) -> List[SourceFile]:
        """
        Add a list of SourceFile ORM instances to the session and flush.
        Does NOT commit internally, preserving transaction ownership for the service.
        """
        if not source_files:
            return []

        db.add_all(source_files)
        await db.flush()
        return source_files

    async def get_by_id(
        self,
        db: AsyncSession,
        source_file_id: str,
    ) -> Optional[SourceFile]:
        """Retrieve a SourceFile by its primary key ID."""
        return await db.get(SourceFile, source_file_id)

    async def list_by_analysis_run_id(
        self,
        db: AsyncSession,
        analysis_run_id: str,
    ) -> List[SourceFile]:
        """Retrieve all SourceFiles associated with a specific analysis run."""
        stmt = (
            select(SourceFile)
            .where(SourceFile.analysis_run_id == analysis_run_id)
            .order_by(SourceFile.file_path.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_run_and_path(
        self,
        db: AsyncSession,
        analysis_run_id: str,
        file_path: str,
    ) -> Optional[SourceFile]:
        """Retrieve a SourceFile by its analysis_run_id and file_path."""
        stmt = (
            select(SourceFile)
            .where(
                SourceFile.analysis_run_id == analysis_run_id,
                SourceFile.file_path == file_path,
            )
        )
        result = await db.execute(stmt)
        return result.scalars().first()


source_file_repository = SourceFileRepository()
