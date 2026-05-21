"""Schemas for authentication and RBAC-aware session APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=512)


class AuthTokens(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str
    refresh_expires_at: datetime
    role: str


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=512)


class CurrentUserResponse(BaseModel):
    user_uuid: str
    email: str
    full_name: str | None = None
    role: str
    active: bool


class UserCreateRequest(BaseModel):
    email: EmailStr
    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(pattern="^(SUPER_ADMIN|HR_ADMIN|IT_ADMIN|CEO)$")
    active: bool = True


class ProfileUpdateRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=160)
