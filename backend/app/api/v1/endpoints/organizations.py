"""Organization and membership endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_organization
from app.db.session import get_db
from app.models.enums import OrganizationRole
from app.models.organization import Organization, OrganizationMember
from app.models.user import User
from app.schemas.common import Message
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationMemberInvite,
    OrganizationMemberRead,
    OrganizationRead,
    OrganizationUpdate,
)
from app.services.organization_service import OrganizationService

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("", response_model=list[OrganizationRead], summary="List my organizations")
def list_organizations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Organization]:
    return OrganizationService(db).list_for_user(current_user)


@router.post(
    "",
    response_model=OrganizationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an organization",
)
def create_organization(
    payload: OrganizationCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Organization:
    return OrganizationService(db).create_for_user(
        name=payload.name,
        owner=current_user,
        ip_address=request.client.host if request.client else None,
    )


@router.get(
    "/{organization_id}",
    response_model=OrganizationRead,
    summary="Get an organization",
)
def get_organization(
    context: tuple[Organization, OrganizationMember] = Depends(require_organization()),
) -> Organization:
    organization, _ = context
    return organization


@router.patch(
    "/{organization_id}",
    response_model=OrganizationRead,
    summary="Rename an organization (admin+)",
)
def update_organization(
    payload: OrganizationUpdate,
    context: tuple[Organization, OrganizationMember] = Depends(
        require_organization(OrganizationRole.ADMIN)
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Organization:
    organization, _ = context
    if payload.name is None:
        return organization
    return OrganizationService(db).rename(
        organization_id=organization.id, name=payload.name, actor=current_user
    )


@router.get(
    "/{organization_id}/members",
    response_model=list[OrganizationMemberRead],
    summary="List organization members",
)
def list_members(
    context: tuple[Organization, OrganizationMember] = Depends(require_organization()),
    db: Session = Depends(get_db),
) -> list[OrganizationMember]:
    organization, _ = context
    from app.repositories.organization_repository import OrganizationRepository

    return OrganizationRepository(db).list_members(organization.id)


@router.post(
    "/{organization_id}/members",
    response_model=Message,
    status_code=status.HTTP_201_CREATED,
    summary="Add an existing user to the organization (admin+)",
)
def add_member(
    payload: OrganizationMemberInvite,
    context: tuple[Organization, OrganizationMember] = Depends(
        require_organization(OrganizationRole.ADMIN)
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Message:
    organization, _ = context
    OrganizationService(db).add_member_by_email(
        organization_id=organization.id,
        email=payload.email,
        role=payload.role,
        actor=current_user,
    )
    return Message(detail="Member added.")