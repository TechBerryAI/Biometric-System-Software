"""JWT authentication APIs with refresh rotation, cookies, and MFA."""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.csrf import generate_csrf_token, set_csrf_cookie
from app.core.database import get_db
from app.core.operator_access import user_capabilities
from app.core.security import Permission, get_current_user, require_permissions
from app.domains.audit.services.audit_service import record_audit_event
from app.domains.auth.models.user import User
from app.domains.auth.schemas import (
    AuthTokens,
    CurrentUserResponse,
    LoginChallengeResponse,
    LoginRequest,
    LogoutRequest,
    MfaEnrollResponse,
    MfaLoginVerifyRequest,
    MfaVerifyRequest,
    PasswordChangeRequest,
    ProfileUpdateRequest,
    RefreshRequest,
    UserCreateRequest,
)
from app.domains.auth.services.auth_service import (
    LoginRateLimiter,
    authenticate_user,
    change_user_password,
    create_or_update_user,
    ensure_bootstrap_admin,
    issue_session_tokens,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.domains.auth.services.cookie_auth_service import (
    clear_auth_cookies,
    resolve_refresh_token,
    set_auth_cookies,
    should_omit_token_body,
)
from app.domains.auth.services.mfa_service import (
    MfaChallengeStore,
    confirm_mfa_enrollment,
    enroll_mfa,
    user_requires_mfa,
    verify_mfa_code,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _current_user_response(user: User) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_uuid=user.user_uuid,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        active=user.active,
        mfa_enabled=user.mfa_enabled,
        capabilities=user_capabilities(user),
    )


def _auth_tokens_response(
    *,
    user: User,
    access_token: str,
    refresh_token: str,
    refresh_expiry,
) -> AuthTokens:
    settings = get_settings()
    omit_body = should_omit_token_body(settings)
    return AuthTokens(
        access_token=None if omit_body else access_token,
        refresh_token=None if omit_body else refresh_token,
        refresh_expires_at=None if omit_body else refresh_expiry,
        role=user.role,
    )


def _apply_session_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
) -> None:
    settings = get_settings()
    set_auth_cookies(response, access_token=access_token, refresh_token=refresh_token, settings=settings)
    if settings.csrf_enabled:
        set_csrf_cookie(response, generate_csrf_token(), secure=settings.environment == "production")


@router.post("/bootstrap-admin", response_model=CurrentUserResponse)
def bootstrap_admin(db: Session = Depends(get_db)) -> CurrentUserResponse:
    user = ensure_bootstrap_admin(db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bootstrap admin credentials are not configured.",
        )
    return _current_user_response(user)


@router.post("/login", response_model=Union[AuthTokens, LoginChallengeResponse])
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthTokens | LoginChallengeResponse:
    limiter = LoginRateLimiter()
    email = payload.email.strip().lower()
    if limiter.is_blocked(email):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts")

    user = authenticate_user(db, email=email, password=payload.password)
    if user is None:
        limiter.register_failure(email)
        record_audit_event(
            db,
            action="auth.login",
            resource_type="user",
            resource_id=email,
            outcome="failure",
            request=request,
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if user_requires_mfa(user):
        if not payload.mfa_code:
            challenge_store = MfaChallengeStore()
            challenge_token = challenge_store.create_challenge(user.id)
            if challenge_token is None:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="MFA challenge store unavailable; include mfa_code in login request.",
                )
            limiter.register_success(email)
            db.commit()
            return LoginChallengeResponse(challenge_token=challenge_token, role=user.role)

        if not verify_mfa_code(user, payload.mfa_code):
            limiter.register_failure(email)
            record_audit_event(db, action="auth.mfa_verify", actor=user, outcome="failure", request=request)
            db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")

    limiter.register_success(email)
    access_token, refresh_token, refresh_expiry = issue_session_tokens(db, user)
    _apply_session_cookies(response, access_token=access_token, refresh_token=refresh_token)
    record_audit_event(db, action="auth.login", actor=user, request=request)
    db.commit()
    return _auth_tokens_response(
        user=user,
        access_token=access_token,
        refresh_token=refresh_token,
        refresh_expiry=refresh_expiry,
    )


@router.post("/mfa/verify", response_model=AuthTokens)
def verify_mfa_login(
    payload: MfaLoginVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthTokens:
    challenge_store = MfaChallengeStore()
    user_id = challenge_store.consume_challenge(payload.challenge_token)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired MFA challenge")

    user = db.get(User, user_id)
    if user is None or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive or missing")

    if not verify_mfa_code(user, payload.mfa_code):
        record_audit_event(db, action="auth.mfa_verify", actor=user, outcome="failure", request=request)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")

    access_token, refresh_token, refresh_expiry = issue_session_tokens(db, user)
    _apply_session_cookies(response, access_token=access_token, refresh_token=refresh_token)
    record_audit_event(db, action="auth.mfa_verify", actor=user, request=request)
    db.commit()
    return _auth_tokens_response(
        user=user,
        access_token=access_token,
        refresh_token=refresh_token,
        refresh_expiry=refresh_expiry,
    )


@router.post("/mfa/enroll", response_model=MfaEnrollResponse)
def mfa_enroll(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MfaEnrollResponse:
    secret, provisioning_uri = enroll_mfa(db, user)
    db.commit()
    return MfaEnrollResponse(provisioning_uri=provisioning_uri, secret=secret)


@router.post("/mfa/enroll/confirm", response_model=CurrentUserResponse)
def mfa_enroll_confirm(
    payload: MfaVerifyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CurrentUserResponse:
    if not confirm_mfa_enrollment(db, user, payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid MFA code")
    db.commit()
    db.refresh(user)
    return _current_user_response(user)


@router.post("/refresh", response_model=AuthTokens)
def refresh(
    payload: RefreshRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthTokens:
    raw_refresh = resolve_refresh_token(request, payload.refresh_token)
    if not raw_refresh:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")

    rotated = rotate_refresh_token(db, raw_refresh)
    if rotated is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user, access_token, refresh_token, refresh_expiry = rotated
    _apply_session_cookies(response, access_token=access_token, refresh_token=refresh_token)
    db.commit()
    return _auth_tokens_response(
        user=user,
        access_token=access_token,
        refresh_token=refresh_token,
        refresh_expiry=refresh_expiry,
    )


@router.post("/logout")
def logout(
    payload: LogoutRequest,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    raw_refresh = resolve_refresh_token(request, payload.refresh_token)
    if raw_refresh:
        revoke_refresh_token(db, raw_refresh)
    clear_auth_cookies(response)
    record_audit_event(db, action="auth.logout", actor=user, request=request)
    db.commit()
    return {"status": "ok"}


@router.get("/me", response_model=CurrentUserResponse)
def me(user: User = Depends(get_current_user)) -> CurrentUserResponse:
    return _current_user_response(user)


@router.put("/me", response_model=CurrentUserResponse)
def update_me(
    payload: ProfileUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CurrentUserResponse:
    user.full_name = payload.full_name.strip()
    db.commit()
    db.refresh(user)
    return _current_user_response(user)


@router.post("/me/password", response_model=AuthTokens)
def change_my_password(
    payload: PasswordChangeRequest,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuthTokens:
    if not change_user_password(db, user, payload.current_password, payload.new_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")

    access_token, refresh_token, refresh_expiry = issue_session_tokens(db, user)
    _apply_session_cookies(response, access_token=access_token, refresh_token=refresh_token)
    db.commit()
    return _auth_tokens_response(
        user=user,
        access_token=access_token,
        refresh_token=refresh_token,
        refresh_expiry=refresh_expiry,
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
