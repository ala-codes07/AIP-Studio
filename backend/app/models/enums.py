"""Shared enumerations used across ORM models and schemas."""

from __future__ import annotations

import enum


class OrganizationRole(str, enum.Enum):
    """Role of a user inside an organization."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


# Higher number ⇒ more privileges. Used by the authorization dependency.
ROLE_RANK: dict[OrganizationRole, int] = {
    OrganizationRole.VIEWER: 10,
    OrganizationRole.MEMBER: 20,
    OrganizationRole.ADMIN: 30,
    OrganizationRole.OWNER: 40,
}


def role_at_least(actual: OrganizationRole, required: OrganizationRole) -> bool:
    """Return True when ``actual`` grants at least the privileges of ``required``."""
    return ROLE_RANK[actual] >= ROLE_RANK[required]