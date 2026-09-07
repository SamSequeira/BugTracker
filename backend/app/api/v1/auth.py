import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.auth import (
    SignupRequest,
    LoginRequest,
    UserResponse,
    TokenResponse,
    AuthResponse,
)
from app.services.auth_service import (
    signup_user,
    login_user,
    authenticate_user,
    get_user_by_id,
    authenticate_user,
)
from app.core.security import create_access_token, decode_access_token

from data.dbconnection.session import get_db


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)
bearer_scheme = HTTPBearer(auto_error=False)


@router.post(
    "/signup",
    response_model=AuthResponse,
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

        return {
            "access_token": create_access_token(user.id),
            "token_type": "bearer",
            "user": user,
        }

        return user
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@router.post(
    "/login",
    response_model=AuthResponse,
)
async def login(
    user_data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    try:

        user = await authenticate_user(
        token, user = await authenticate_user(
            db=db,
            email=user_data.email,
            password=user_data.password,
        )
        return {
            "access_token": create_access_token(user.id),
            "token_type": "bearer",
            "user": user,
            "user": user,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        user_id = decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


@router.get("/me", response_model=UserResponse)
async def me(current_user=Depends(get_current_user)):
    return current_user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout():
    # JWTs are stateless; the client invalidates its local session and token.
    return None


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
