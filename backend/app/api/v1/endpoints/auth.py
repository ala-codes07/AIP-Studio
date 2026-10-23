"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (RefreshRequest, TokenPair, UserRegisterRequest,
    EmailCodeRequest, EmailOnlyRequest, ResetPasswordRequest, ChangePasswordRequest)
from app.schemas.common import Message
from app.schemas.user import UserRead
from app.services.auth_service import AuthService
from app.services.email_codes import EmailCodeService
from app.core.security import hash_password, verify_password
from app.core.exceptions import AuthenticationError, ValidationError, AuthorizationError
from app.models.auth_session import RefreshSession
from app.repositories.user_repository import UserRepository
from datetime import datetime, timezone
from sqlalchemy import update

router = APIRouter(prefix="/auth", tags=["auth"])


def registration_invited(email: str, allowed: str) -> bool:
    """Early public beta: registration must be allowlisted server-side."""
    permitted = {v.strip().casefold() for v in allowed.split(',') if v.strip()}
    return email.strip().casefold() in permitted



def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new account (optionally with an initial organization)",
)
def register(
    payload: UserRegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    from app.core.config import get_settings
    settings = get_settings()
    if settings.is_production and not registration_invited(str(payload.email), settings.BETA_ALLOWED_EMAILS):
        raise AuthorizationError('Registration is invite-only for the current beta.')
    _check_password_length(payload.password)
    return AuthService(db).register(payload, ip_address=_client_ip(request))


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Exchange credentials for an access/refresh token pair",
)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenPair:
    service = AuthService(db)
    user = service.authenticate(email=form_data.username, password=form_data.password)
    service.mark_login(user, ip_address=_client_ip(request))
    return service.issue_tokens(user)


@router.post("/refresh", response_model=TokenPair, summary="Rotate a refresh token; old refresh token becomes invalid")
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenPair:
    _, tokens = AuthService(db).refresh(payload.refresh_token)
    return tokens


@router.post("/logout", response_model=Message, summary="Revoke a refresh token and end the client session")
def logout(
    payload: RefreshRequest | None = Body(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Message:
    if payload is not None:
        AuthService(db).revoke_refresh(payload.refresh_token, user=current_user)
    return Message(detail="Session ended. Access JWTs remain valid until their short expiry.")


@router.get("/me", response_model=UserRead, summary="Return the current user")
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user

def _check_password_length(value: str) -> None:
    if len(value.encode('utf-8')) > 72:
        raise ValidationError('Password must not exceed 72 UTF-8 bytes.')


@router.post('/verify-email', response_model=Message, summary='Confirm new account using a six-digit email code')
def verify_email(payload: EmailCodeRequest, db: Session = Depends(get_db)) -> Message:
    user = UserRepository(db).get_by_email(str(payload.email))
    if user is None or user.email_verified_at:
        raise ValidationError('Verification code is invalid or unavailable.')
    EmailCodeService(db).consume(user, 'verify', payload.code)
    user.email_verified_at = datetime.now(timezone.utc)
    db.commit()
    return Message(detail='Email verified. You can now sign in.')


@router.post('/resend-verification', response_model=Message)
def resend_verification(payload: EmailOnlyRequest, db: Session = Depends(get_db)) -> Message:
    user = UserRepository(db).get_by_email(str(payload.email))
    if user is not None and not user.email_verified_at:
        EmailCodeService(db).send(user, 'verify')
    return Message(detail='If your email is awaiting verification, a code has been sent.')


@router.post('/forgot-password', response_model=Message)
def forgot_password(payload: EmailOnlyRequest, db: Session = Depends(get_db)) -> Message:
    user = UserRepository(db).get_by_email(str(payload.email))
    if user is not None and user.is_active and user.email_verified_at:
        EmailCodeService(db).send(user, 'reset')
    return Message(detail='If an eligible account exists, a reset code has been sent.')


@router.post('/reset-password', response_model=Message)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> Message:
    _check_password_length(payload.new_password)
    user = UserRepository(db).get_by_email(str(payload.email))
    if user is None or not user.is_active or not user.email_verified_at:
        raise ValidationError('Reset code is invalid or unavailable.')
    EmailCodeService(db).consume(user, 'reset', payload.code)
    user.hashed_password = hash_password(payload.new_password)
    user.password_version += 1
    db.execute(update(RefreshSession).where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None)).values(revoked_at=datetime.now(timezone.utc)))
    db.commit()
    return Message(detail='Password updated. Sign in with your new password.')


@router.post('/change-password', response_model=Message)
def change_password(payload: ChangePasswordRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Message:
    _check_password_length(payload.new_password)
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise AuthenticationError('Current password is incorrect.')
    current_user.hashed_password = hash_password(payload.new_password)
    current_user.password_version += 1
    db.execute(update(RefreshSession).where(RefreshSession.user_id == current_user.id, RefreshSession.revoked_at.is_(None)).values(revoked_at=datetime.now(timezone.utc)))
    db.commit()
    return Message(detail='Password changed. All sessions have been invalidated; sign in again.')
