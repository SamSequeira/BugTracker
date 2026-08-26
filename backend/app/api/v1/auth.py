from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.auth import (
    SignupRequest,
    LoginRequest,
    UserResponse,
    TokenResponse,
)

from app.services.auth_service import (
    signup_user,
    login_user,
)

from data.dbconnection.session import get_db


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/signup",
    response_model=UserResponse,
)
async def signup(
    user_data: SignupRequest,
    db: AsyncSession = Depends(get_db),
):

    try:

        user = await signup_user(
            db=db,
            name=user_data.name,
            email=user_data.email,
            password=user_data.password,
        )

        return user

    except ValueError as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@router.post(
    "/login",
    response_model=TokenResponse,
)
async def login(
    user_data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):

    try:

        token = await login_user(
            db=db,
            email=user_data.email,
            password=user_data.password,
        )

        return {
            "access_token": token,
            "token_type": "bearer",
        }

    except ValueError as e:

        raise HTTPException(
            status_code=401,
            detail=str(e),
        )
