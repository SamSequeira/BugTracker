"""Smoke tests for the authentication database and API wiring."""

import asyncio
import os
import sys
import tempfile
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def test_authentication_flow() -> None:
    database_path = Path(tempfile.gettempdir()) / "bugtracker-auth-test.db"
    database_path.unlink(missing_ok=True)
    os.environ["DATABASE_URL"] = (
        f"sqlite+aiosqlite:///{database_path.as_posix()}"
    )
    os.environ["JWT_SECRET_KEY"] = "integration-test-secret-with-32-bytes"

    from app.main import app
    from app.models.user import User  # noqa: F401 - registers the table
    from app.services.auth_service import login_user, signup_user
    from data.dbconnection.base import Base
    from data.dbconnection.session import AsyncSessionLocal, engine

    async def check() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with AsyncSessionLocal() as db:
            user = await signup_user(
                db, "Test User", "Test@Example.com", "correct-password"
            )
            token = await login_user(
                db, "test@example.com", "correct-password"
            )
            assert user.email == "test@example.com"
            assert token

            try:
                await signup_user(
                    db, "Duplicate", "TEST@example.com", "correct-password"
                )
            except ValueError:
                pass
            else:
                raise AssertionError("duplicate email was accepted")

        await engine.dispose()

    try:
        paths = app.openapi()["paths"]
        assert "/api/v1/auth/signup" in paths
        assert "/api/v1/auth/login" in paths
        asyncio.run(check())
    finally:
        database_path.unlink(missing_ok=True)

"""Smoke tests for the authentication database and API wiring."""

import asyncio
import os
import sys
import tempfile
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def test_authentication_flow() -> None:
    database_path = Path(tempfile.gettempdir()) / "bugtracker-auth-test.db"
    database_path.unlink(missing_ok=True)
    os.environ["DATABASE_URL"] = (
        f"sqlite+aiosqlite:///{database_path.as_posix()}"
    )
    os.environ["JWT_SECRET_KEY"] = "integration-test-secret-with-32-bytes"

    from app.main import app
    from app.models.user import User  # noqa: F401 - registers the table
    from app.services.auth_service import login_user, signup_user
    from data.dbconnection.base import Base
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

    test_engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    test_session_maker = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def check() -> None:
        async with test_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with test_session_maker() as db:
            user = await signup_user(
                db, "Test User", "Test@Example.com", "correct-password"
            )
            token = await login_user(
                db, "test@example.com", "correct-password"
            )
            assert user.email == "test@example.com"
            assert token

            try:
                await signup_user(
                    db, "Duplicate", "TEST@example.com", "correct-password"
                )
            except ValueError:
                pass
            else:
                raise AssertionError("duplicate email was accepted")

        await test_engine.dispose()

    try:
        paths = app.openapi()["paths"]
        assert "/api/v1/auth/signup" in paths
        assert "/api/v1/auth/login" in paths
        asyncio.run(check())
    finally:
        database_path.unlink(missing_ok=True)
