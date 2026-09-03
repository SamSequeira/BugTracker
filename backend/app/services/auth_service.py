from typing import Tuple
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

    normalized_email = email.lower().strip()

    result = await db.execute(
        select(User).where(User.email == normalized_email)
    )

    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise ValueError("Email already registered")

    new_user = User(
        id=str(uuid4()),
        name=name,
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


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> Tuple[str, User]:

    result = await db.execute(
        select(User).where(
            User.email == email.lower().strip()
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

    token = create_access_token(user.id)
    return token, user


async def login_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> str:
    token, _ = await authenticate_user(db, email, password)
    return token
