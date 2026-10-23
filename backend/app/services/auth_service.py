"""Registration, authentication and token lifecycle."""

from __future__ import annotations

import logging
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy import select, update
from app.services.email_codes import EmailCodeService
from app.models.auth_session import RefreshSession

import jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.enums import OrganizationRole
from app.models.user import User
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenPair, UserRegisterRequest
from app.services.audit_service import record_audit_event

logger = logging.getLogger(__name__)
_settings = get_settings()


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.organizations = OrganizationRepository(db)

    # ── Registration ───────────────────────────────────────────
    def register(
        self,
        payload: UserRegisterRequest,
        *,
        ip_address: str | None = None,
    ) -> User:
        if self.users.get_by_email(payload.email) is not None:
            raise ConflictError("An account with this email already exists.")

        user = self.users.create(
            email=payload.email,
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name,
        )

        if payload.organization_name:
            organization = self.organizations.create(name=payload.organization_name)
            self.organizations.add_member(
                organization_id=organization.id,
                user_id=user.id,
                role=OrganizationRole.OWNER,
            )
            record_audit_event(
                self.db,
                action="organization.create",
                actor_user_id=user.id,
                organization_id=organization.id,
                resource_type="organization",
                resource_id=organization.id,
                metadata={"name": organization.name, "origin": "registration"},
                ip_address=ip_address,
            )

        record_audit_event(
            self.db,
            action="auth.register",
            actor_user_id=user.id,
            resource_type="user",
            resource_id=user.id,
            metadata={"email": user.email},
            ip_address=ip_address,
        )

        self.db.commit()
        self.db.refresh(user)
        EmailCodeService(self.db).send(user, "verify")
        logger.info("user_registered", extra={"user_id": str(user.id)})
        return user

    # ── Authentication ─────────────────────────────────────────
    def authenticate(self, *, email: str, password: str) -> User:
        user = self.users.get_by_email(email)
        # Always run a hash comparison to keep timing uniform for unknown users.
        dummy_hash = "$2b$12$" + "x" * 53
        stored_hash = user.hashed_password if user else dummy_hash

        if not verify_password(password, stored_hash) or user is None:
            raise AuthenticationError("Incorrect email or password.")
        if not user.is_active:
            raise AuthenticationError("This account is disabled.")
        if not user.email_verified_at:
            from app.core.exceptions import AuthorizationError
            raise AuthorizationError("Please verify your email with the six-digit code first.")

        return user

    def mark_login(self, user: User, *, ip_address: str | None = None) -> None:
        from datetime import datetime, timezone

        user.last_login_at = datetime.now(timezone.utc)
        record_audit_event(
            self.db,
            action="auth.login",
            actor_user_id=user.id,
            resource_type="user",
            resource_id=user.id,
            ip_address=ip_address,
        )
        self.db.commit()

    # ── Tokens ─────────────────────────────────────────────────
    def issue_tokens(self, user: User) -> TokenPair:
        access_token = create_access_token(str(user.id), {"pv": user.password_version})
        refresh_token = create_refresh_token(str(user.id))
        claims = decode_token(refresh_token, expected_type="refresh")
        self.db.add(RefreshSession(
            jti=claims["jti"], user_id=user.id,
            expires_at=datetime.fromtimestamp(claims["exp"], tz=timezone.utc),
        ))
        self.db.commit()
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=_settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    def refresh(self, refresh_token: str) -> tuple[User, TokenPair]:
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("Refresh token has expired.") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthenticationError("Invalid refresh token.") from exc
        try:
            user_id = UUID(payload["sub"])
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise AuthenticationError("Invalid refresh token.") from exc
        user = self.users.get_by_id(user_id)
        if user is None or not user.is_active or not user.email_verified_at:
            raise AuthenticationError("Account is no longer valid.")
        now = datetime.now(timezone.utc)
        result = self.db.execute(
            update(RefreshSession).where(
                RefreshSession.jti == payload["jti"],
                RefreshSession.user_id == user.id,
                RefreshSession.revoked_at.is_(None),
                RefreshSession.expires_at > now,
            ).values(revoked_at=now)
        )
        if result.rowcount != 1:
            self.db.rollback()
            raise AuthenticationError("Refresh token has been used or revoked.")
        self.db.commit()
        return user, self.issue_tokens(user)

    def revoke_refresh(self, refresh_token: str, *, user: User) -> None:
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
            if payload["sub"] != str(user.id):
                raise AuthenticationError("Refresh token does not belong to this account.")
        except jwt.InvalidTokenError as exc:
            raise AuthenticationError("Invalid refresh token.") from exc
        session = self.db.get(RefreshSession, payload["jti"])
        if session is None or session.user_id != user.id:
            raise AuthenticationError("Refresh token not recognized.")
        session.revoked_at = datetime.now(timezone.utc)
        self.db.commit()
