from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.auth import (
    SignupRequest,
    LoginRequest,
    UserResponse,
    TokenResponse,
)
from app.services.auth_service import (
    signup_user,
    authenticate_user,
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
        token, user = await authenticate_user(
            db=db,
            email=user_data.email,
            password=user_data.password,
        )
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": user,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
        )


@router.get(
    "/me",
    response_model=UserResponse,
)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve active authenticated user profile based on Bearer token.
    """
    return current_user


@router.post(
    "/logout",
)
async def logout():
    """
    Stateless JWT logout endpoint.
    """
    return {"message": "Logged out successfully"}
