"""User-facing schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr

from app.schemas.common import ORMModel


class UserRead(ORMModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    is_active: bool
    email_verified: bool = False

    @__import__("pydantic").model_validator(mode="before")
    @classmethod
    def _verified(cls, value):
        if isinstance(value, dict):
            return {**value, "email_verified": bool(value.get("email_verified_at", value.get("email_verified", False)))}
        return {"id": value.id, "email": value.email, "full_name": value.full_name, "is_active": value.is_active, "email_verified": bool(value.email_verified_at), "created_at": value.created_at}
    created_at: datetime