"""JWT authentication APIs with refresh rotation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import Permission, get_current_user, require_permissions
from app.models.user import User
from app.schemas.auth import (
    AuthTokens,
    CurrentUserResponse,
    LoginRequest,
    LogoutRequest,
    PasswordChangeRequest,
    ProfileUpdateRequest,
    RefreshRequest,
    UserCreateRequest,
)
from app.services.auth_service import (
    LoginRateLimiter,
    authenticate_user,
    change_user_password,
    create_or_update_user,
    ensure_bootstrap_admin,
    issue_session_tokens,
    revoke_refresh_token,
    rotate_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])
from app.core.operator_access import user_capabilities


def _current_user_response(user: User) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_uuid=user.user_uuid,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        active=user.active,
        capabilities=user_capabilities(user),
    )


@router.post("/bootstrap-admin", response_model=CurrentUserResponse)
def bootstrap_admin(db: Session = Depends(get_db)) -> CurrentUserResponse:
    user = ensure_bootstrap_admin(db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bootstrap admin credentials are not configured.",
        )
    return _current_user_response(user)


@router.post("/login", response_model=AuthTokens)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> AuthTokens:
    limiter = LoginRateLimiter()
    email = payload.email.strip().lower()
    if limiter.is_blocked(email):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts")

    user = authenticate_user(db, email=email, password=payload.password)
    if user is None:
        limiter.register_failure(email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    limiter.register_success(email)
    access_token, refresh_token, refresh_expiry = issue_session_tokens(db, user)
    db.commit()
    return AuthTokens(
        access_token=access_token,
        refresh_token=refresh_token,
        refresh_expires_at=refresh_expiry,
        role=user.role,
    )


@router.post("/refresh", response_model=AuthTokens)
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)) -> AuthTokens:
    rotated = rotate_refresh_token(db, payload.refresh_token)
    if rotated is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user, access_token, refresh_token, refresh_expiry = rotated
    db.commit()
    return AuthTokens(
        access_token=access_token,
        refresh_token=refresh_token,
        refresh_expires_at=refresh_expiry,
        role=user.role,
    )


@router.post("/logout")
def logout(payload: LogoutRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    revoke_refresh_token(db, payload.refresh_token)
    db.commit()
    return {"status": "ok"}


@router.get("/me", response_model=CurrentUserResponse)
def me(user: User = Depends(get_current_user)) -> CurrentUserResponse:
    return _current_user_response(user)


@router.put("/me", response_model=CurrentUserResponse)
def update_me(payload: ProfileUpdateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> CurrentUserResponse:
    user.full_name = payload.full_name.strip()
    db.commit()
    db.refresh(user)
    return _current_user_response(user)


@router.post("/me/password", response_model=AuthTokens)
def change_my_password(
    payload: PasswordChangeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuthTokens:
    if not change_user_password(db, user, payload.current_password, payload.new_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")

    access_token, refresh_token, refresh_expiry = issue_session_tokens(db, user)
    db.commit()
    return AuthTokens(
        access_token=access_token,
        refresh_token=refresh_token,
        refresh_expires_at=refresh_expiry,
        role=user.role,
    )


@router.post("/users", response_model=CurrentUserResponse)
def create_user(
    payload: UserCreateRequest,
    actor: User = Depends(require_permissions(Permission.USER_MANAGE)),
    db: Session = Depends(get_db),
) -> CurrentUserResponse:
    del actor  # authorization only
    normalized_email = str(payload.email).strip().lower()
    selected_role = str(payload.role).strip().upper()

    if selected_role == "SUPER_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This role cannot be assigned from Add Account.",
        )

    user = create_or_update_user(
        db,
        email=normalized_email,
        full_name=payload.full_name,
        password=payload.password,
        role=selected_role,
        active=payload.active,
    )
    db.commit()
    db.refresh(user)
    return _current_user_response(user)
