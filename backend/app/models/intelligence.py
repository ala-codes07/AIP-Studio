"""Persisted tenant-scoped websites, audits and evidence-backed issues."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, UUIDPrimaryKeyMixin, TimestampMixin

class Website(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "websites"
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    audits: Mapped[list["WebsiteAudit"]] = relationship(back_populates="website", cascade="all, delete-orphan")

class WebsiteAudit(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "website_audits"
    website_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("websites.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="completed")
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_scanned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    issues_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    website: Mapped[Website] = relationship(back_populates="audits")
    findings: Mapped[list["AuditFinding"]] = relationship(back_populates="audit", cascade="all, delete-orphan")

class AuditFinding(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "audit_findings"
    audit_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("website_audits.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    rule: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    page_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    audit: Mapped[WebsiteAudit] = relationship(back_populates="findings")
