"""Organization management use cases."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.enums import OrganizationRole
from app.models.organization import Organization
from app.models.user import User
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_service import record_audit_event


class OrganizationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.organizations = OrganizationRepository(db)
        self.users = UserRepository(db)

    def create_for_user(
        self, *, name: str, owner: User, ip_address: str | None = None
    ) -> Organization:
        organization = self.organizations.create(name=name)
        self.organizations.add_member(
            organization_id=organization.id,
            user_id=owner.id,
            role=OrganizationRole.OWNER,
        )
        record_audit_event(
            self.db,
            action="organization.create",
            actor_user_id=owner.id,
            organization_id=organization.id,
            resource_type="organization",
            resource_id=organization.id,
            metadata={"name": organization.name},
            ip_address=ip_address,
        )
        self.db.commit()
        self.db.refresh(organization)
        return organization

    def list_for_user(self, user: User) -> list[Organization]:
        return self.organizations.list_for_user(user.id)

    def get_for_user(self, organization_id: uuid.UUID, user: User) -> Organization:
        organization = self.organizations.get(organization_id)
        if organization is None:
            raise NotFoundError("Organization not found.")
        if self.organizations.get_membership(
            organization_id=organization_id, user_id=user.id
        ) is None:
            # Do not leak existence of other tenants' organizations.
            raise NotFoundError("Organization not found.")
        return organization

    def rename(
        self, *, organization_id: uuid.UUID, name: str, actor: User
    ) -> Organization:
        organization = self.get_for_user(organization_id, actor)
        organization.name = name.strip()
        record_audit_event(
            self.db,
            action="organization.rename",
            actor_user_id=actor.id,
            organization_id=organization.id,
            resource_type="organization",
            resource_id=organization.id,
            metadata={"name": organization.name},
        )
        self.db.commit()
        self.db.refresh(organization)
        return organization

    def add_member_by_email(
        self,
        *,
        organization_id: uuid.UUID,
        email: str,
        role: OrganizationRole,
        actor: User,
    ) -> None:
        organization = self.get_for_user(organization_id, actor)

        if role == OrganizationRole.OWNER:
            raise ValidationError("Ownership transfer is not supported in V1.")

        invitee = self.users.get_by_email(email)
        if invitee is None:
            raise NotFoundError("No user account exists with that email address.")

        if self.organizations.get_membership(
            organization_id=organization.id, user_id=invitee.id
        ) is not None:
            raise ConflictError("This user is already a member of the organization.")

        self.organizations.add_member(
            organization_id=organization.id, user_id=invitee.id, role=role
        )
        record_audit_event(
            self.db,
            action="organization.member_add",
            actor_user_id=actor.id,
            organization_id=organization.id,
            resource_type="user",
            resource_id=invitee.id,
            metadata={"role": role.value},
        )
        self.db.commit()