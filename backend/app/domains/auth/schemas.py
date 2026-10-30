"""Schemas for authentication and RBAC-aware session APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    mfa_code: str | None = Field(default=None, min_length=6, max_length=8)


class RefreshRequest(BaseModel):
    refresh_token: str | None = Field(default=None, min_length=20, max_length=512)


class AuthTokens(BaseModel):
    access_token: str | None = None
    token_type: str = "bearer"
    refresh_token: str | None = None
    refresh_expires_at: datetime | None = None
    role: str
    mfa_required: bool = False


class LoginChallengeResponse(BaseModel):
    mfa_required: bool = True
    challenge_token: str
    role: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, min_length=20, max_length=512)


class UserCapabilities(BaseModel):
    attendance_adjust: bool = False
    forensic_audit: bool = False


class CurrentUserResponse(BaseModel):
    user_uuid: str
    email: str
    full_name: str | None = None
    role: str
    active: bool
    mfa_enabled: bool = False
    capabilities: UserCapabilities = Field(default_factory=UserCapabilities)


class MfaEnrollResponse(BaseModel):
    provisioning_uri: str
    secret: str


class MfaVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class MfaLoginVerifyRequest(BaseModel):
    challenge_token: str = Field(min_length=20, max_length=128)
    mfa_code: str = Field(min_length=6, max_length=8)


class UserCreateRequest(BaseModel):
    email: EmailStr
    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(pattern="^(HR_ADMIN|IT_ADMIN)$")
    active: bool = True


class ProfileUpdateRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=160)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_passwords(self) -> PasswordChangeRequest:
        if self.new_password != self.confirm_password:
            raise ValueError("New password and confirmation do not match")
        if self.new_password == self.current_password:
            raise ValueError("New password must differ from current password")
        return self


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_passwords(self) -> PasswordResetConfirmRequest:
        if self.new_password != self.confirm_password:
            raise ValueError("New password and confirmation do not match")
        return self
