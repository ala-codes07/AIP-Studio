"""Organization and membership schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import OrganizationRole
from app.schemas.common import ORMModel


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)


class OrganizationRead(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    plan: str
    created_at: datetime


class OrganizationMemberRead(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    role: OrganizationRole
    created_at: datetime


class OrganizationMemberInvite(BaseModel):
    email: EmailStr
    role: OrganizationRole = OrganizationRole.MEMBER


class OrganizationMemberUpdate(BaseModel):
    role: OrganizationRole