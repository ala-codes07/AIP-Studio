"""Persisted scan queue: durable across API requests, processed by a separate worker."""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, UUIDPrimaryKeyMixin

class ScanJob(Base, UUIDPrimaryKeyMixin):
    __tablename__ = 'scan_jobs'
    website_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey('websites.id', ondelete='CASCADE'), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='queued', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    audit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey('website_audits.id', ondelete='SET NULL'), nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=False, default='')
