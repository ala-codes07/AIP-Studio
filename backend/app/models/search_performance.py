"""User-uploaded Search Console export; website/organization authorization is enforced at API edge."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, UUIDPrimaryKeyMixin

class SearchPerformanceImport(Base, UUIDPrimaryKeyMixin):
    __tablename__ = 'search_performance_imports'
    website_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey('websites.id', ondelete='CASCADE'), nullable=False, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_clicks: Mapped[int] = mapped_column(Integer, nullable=False)
    total_impressions: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
