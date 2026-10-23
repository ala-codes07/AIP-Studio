"""Reusable FastAPI dependencies: DB session, current user, org authorization."""

from __future__ import annotations

import uuid
from collections.abc import Callable

import jwt
from fastapi import Depends, Path
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, AuthorizationError, NotFoundError
from app.core.logging import organization_id_ctx, user_id_ctx
from app.core.security import decode_token
from app.db.session import get_db
from app.models.enums import OrganizationRole, role_at_least
from app.models.organization import Organization, OrganizationMember
from app.models.user import User
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository

_settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{_settings.API_V1_PREFIX}/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from a bearer access token."""
    try:
        payload = decode_token(token, expected_type="access")
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Invalid access token.") from exc

    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, TypeError, AttributeError) as exc:
        raise AuthenticationError("Invalid access token subject.") from exc

    user = UserRepository(db).get_by_id(user_id)
    if user is None:
        raise AuthenticationError("Account no longer exists.")
    if not user.is_active:
        raise AuthenticationError("Account is disabled.")

    if payload.get("pv", 0) != user.password_version:
        raise AuthenticationError("Your security credentials changed. Please sign in again.")
    user_id_ctx.set(str(user.id))
    return user


def require_organization(min_role: OrganizationRole = OrganizationRole.VIEWER) -> Callable:
    """Build a dependency that authorizes the caller against ``{organization_id}``."""

    def dependency(
        organization_id: uuid.UUID = Path(..., alias="organization_id"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> tuple[Organization, OrganizationMember]:
        repo = OrganizationRepository(db)
        organization = repo.get(organization_id)
        if organization is None:
            raise NotFoundError("Organization not found.")

        membership = repo.get_membership(
            organization_id=organization_id, user_id=current_user.id
        )
        if membership is None:
            # Deliberately 404 to avoid leaking tenant existence.
            raise NotFoundError("Organization not found.")

        if not role_at_least(membership.role, min_role):
            raise AuthorizationError(
                f"This action requires the '{min_role.value}' role or higher."
            )

        organization_id_ctx.set(str(organization.id))
        return organization, membership

    return dependency