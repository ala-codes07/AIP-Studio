"""Best-effort audit logging."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


def record_audit_event(
    db: Session,
    *,
    action: str,
    actor_user_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """Persist an audit event.

    Never pass secrets, tokens or passwords in ``metadata``.
    """
    try:
        db.add(
            AuditLog(
                action=action,
                actor_user_id=actor_user_id,
                organization_id=organization_id,
                resource_type=resource_type,
                resource_id=resource_id,
                event_metadata=metadata or {},
                ip_address=ip_address,
            )
        )
    except Exception:  # pragma: no cover - auditing must never break the request
        logger.exception("audit_event_failed", extra={"action": action})