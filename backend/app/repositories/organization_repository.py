"""Data access for organizations and memberships."""

from __future__ import annotations

import re
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import OrganizationRole
from app.models.organization import Organization, OrganizationMember
from app.repositories.base import BaseRepository

_SLUG_SAFE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Produce a URL-safe slug from an arbitrary name."""
    slug = _SLUG_SAFE.sub("-", value.strip().lower()).strip("-")
    return slug or "org"


class OrganizationRepository(BaseRepository[Organization]):
    model = Organization

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    # ── Organizations ──────────────────────────────────────────
    def get_by_slug(self, slug: str) -> Organization | None:
        stmt = select(Organization).where(Organization.slug == slug)
        return self.db.execute(stmt).scalar_one_or_none()

    def _generate_unique_slug(self, name: str) -> str:
        base = slugify(name)
        candidate = base
        while self.get_by_slug(candidate) is not None:
            candidate = f"{base}-{secrets.token_hex(3)}"
        return candidate

    def create(self, *, name: str, plan: str = "free") -> Organization:
        organization = Organization(
            name=name.strip(),
            slug=self._generate_unique_slug(name),
            plan=plan,
        )
        return self.add(organization)

    def list_for_user(self, user_id: uuid.UUID) -> list[Organization]:
        stmt = (
            select(Organization)
            .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
            .where(OrganizationMember.user_id == user_id)
            .order_by(Organization.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    # ── Memberships ────────────────────────────────────────────
    def get_membership(
        self, *, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> OrganizationMember | None:
        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def add_member(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        role: OrganizationRole = OrganizationRole.MEMBER,
    ) -> OrganizationMember:
        member = OrganizationMember(
            organization_id=organization_id,
            user_id=user_id,
            role=role,
        )
        return self.add(member)

    def list_members(self, organization_id: uuid.UUID) -> list[OrganizationMember]:
        stmt = (
            select(OrganizationMember)
            .options(selectinload(OrganizationMember.user))
            .where(OrganizationMember.organization_id == organization_id)
            .order_by(OrganizationMember.created_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())