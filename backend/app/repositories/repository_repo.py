"""
repository_repo.py
-------------------
Data Access Layer (DAL) repository for Repository entity.
"""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repository import Repository


class RepositoryRepository:
    """Encapsulates database access queries for Repository ORM model."""

    async def create(
        self,
        db: AsyncSession,
        repository: Repository,
    ) -> Repository:
        """
        Add a Repository ORM instance to the session and flush.
        Does NOT commit internally, preserving transaction ownership for the service.
        """
        db.add(repository)
        await db.flush()
        return repository

    async def get_by_id(
        self,
        db: AsyncSession,
        repository_id: str,
    ) -> Optional[Repository]:
        """Retrieve a Repository by its primary key ID."""
        return await db.get(Repository, repository_id)

    async def list_all(
        self,
        db: AsyncSession,
    ) -> List[Repository]:
        """Retrieve all repositories ordered by creation timestamp."""
        stmt = select(Repository).order_by(Repository.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())


repository_repository = RepositoryRepository()
