from collections.abc import AsyncGenerator

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


# Keep route discovery (and therefore /docs) available when local PostgreSQL
# configuration has not been supplied yet. Database-backed endpoints return a
# clear 503 until DATABASE_URL is configured and the server is restarted.
try:
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
except RuntimeError:
    engine = None
    AsyncSessionLocal = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield one database session per request and always close it."""
    if AsyncSessionLocal is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured. Set DATABASE_URL in backend/.env and restart the server.",
        )
    async with AsyncSessionLocal() as session:
        yield session
