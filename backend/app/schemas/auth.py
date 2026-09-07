from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr


class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=6)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: EmailStr


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class AuthResponse(TokenResponse):
    user: UserResponse
    user: Optional[UserResponse] = None
