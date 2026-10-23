"""Liveness and readiness probes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])
_settings = get_settings()


@router.get("/health", summary="Liveness probe")
def health() -> dict[str, str]:
    return {"status": "ok", "app": _settings.APP_NAME, "env": _settings.APP_ENV}


@router.get("/health/ready", summary="Readiness probe (checks the database)")
def readiness(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}