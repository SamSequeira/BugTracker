from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
)


async def signup_user(
    db: AsyncSession,
    name: str,
    email: str,
    password: str,
) -> User:

    normalized_name = name.strip()
    normalized_email = email.lower().strip()

    if len(normalized_name) < 2:
        raise ValueError("Name must be at least 2 characters")

    result = await db.execute(
        select(User).where(User.email == normalized_email)
    )

    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise ValueError("Email already registered")

    new_user = User(
        id=str(uuid4()),
        name=normalized_name,
        email=normalized_email,
        password_hash=hash_password(password),
    )

    db.add(new_user)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ValueError("Email already registered") from exc
    await db.refresh(new_user)

    return new_user


async def login_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> str:

    user = await authenticate_user(db, email, password)
    return create_access_token(user.id)


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> User:
    result = await db.execute(
        select(User).where(
            User.email == email.lower()
        )
    )

    user = result.scalar_one_or_none()

    if not user:
        raise ValueError("Invalid email or password")

    if not verify_password(
        password,
        user.password_hash,
    ):
        raise ValueError("Invalid email or password")

    return user


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
