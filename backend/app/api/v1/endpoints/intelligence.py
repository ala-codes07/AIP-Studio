"""Tenant-isolated website management, bounded scans and evidence-backed reports."""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.exceptions import AuthorizationError, NotFoundError, RateLimitError, ValidationError
from app.db.session import get_db
from app.models.enums import OrganizationRole, role_at_least
from app.models.organization import OrganizationMember
from app.models.intelligence import Website, WebsiteAudit, AuditFinding
from app.models.user import User
from app.services.seo_engine import run_audit, validate_target
from app.core.config import get_settings

router = APIRouter(tags=["website intelligence"])

class WebsiteCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    url: str = Field(min_length=8, max_length=2048)

class WebsiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    url: str
    created_at: datetime

class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    website_id: uuid.UUID
    created_at: datetime
    score: int | None
    pages_scanned: int
    issues_count: int
    summary: dict
    status: str

    @model_validator(mode="after")
    def normalize_legacy_failed_scans(self):
        """Do not expose fabricated scores from historical fetch-only reports."""
        pages = self.summary.get("pages", []) if isinstance(self.summary, dict) else []
        if pages:
            good = sum(isinstance(page.get("status"), int) and 200 <= page["status"] < 400 for page in pages)
            if good == 0:
                self.status = "failed"
                self.pages_scanned = 0
                self.score = None
            elif good < len(pages):
                self.status = "partial"
                self.pages_scanned = good
        if self.status == "failed":
            self.score = None
            self.pages_scanned = 0
        return self

class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    audit_id: uuid.UUID
    category: str
    severity: str
    rule: str
    title: str
    description: str
    recommendation: str
    page_url: str
    evidence: str

class ReportRead(BaseModel):
    audit: AuditRead
    website: WebsiteRead
    findings: list[FindingRead]


def membership(db: Session, user: User, organization_id: uuid.UUID, minimum: OrganizationRole = OrganizationRole.VIEWER) -> None:
    role = db.scalar(select(OrganizationMember.role).where(OrganizationMember.organization_id == organization_id, OrganizationMember.user_id == user.id))
    if role is None:
        raise NotFoundError("Organization not found.")
    if not role_at_least(role, minimum):
        raise AuthorizationError("Insufficient organization permissions.")


def website_for_user(db: Session, user: User, website_id: uuid.UUID, minimum: OrganizationRole = OrganizationRole.VIEWER) -> Website:
    website = db.get(Website, website_id)
    if not website:
        raise NotFoundError("Website not found.")
    membership(db, user, website.organization_id, minimum)
    return website


def audit_for_user(db: Session, user: User, audit_id: uuid.UUID) -> tuple[WebsiteAudit, Website]:
    audit = db.get(WebsiteAudit, audit_id)
    if audit is None:
        raise NotFoundError("Audit not found.")
    website = website_for_user(db, user, audit.website_id)
    return audit, website


@router.get("/organizations/{organization_id}/websites", response_model=list[WebsiteRead])
def list_websites(organization_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    membership(db, user, organization_id)
    return db.scalars(select(Website).where(Website.organization_id == organization_id).order_by(Website.created_at.desc()).limit(100)).all()


@router.post("/organizations/{organization_id}/websites", response_model=WebsiteRead, status_code=status.HTTP_201_CREATED)
def create_website(organization_id: uuid.UUID, payload: WebsiteCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    membership(db, user, organization_id, OrganizationRole.MEMBER)
    url = validate_target(payload.url)
    website = Website(organization_id=organization_id, name=payload.name.strip(), url=url)
    db.add(website)
    db.commit()
    db.refresh(website)
    return website


@router.delete("/websites/{website_id}", status_code=204)
def delete_website(website_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    website = website_for_user(db, user, website_id, OrganizationRole.ADMIN)
    db.delete(website)
    db.commit()
    return Response(status_code=204)


@router.get("/websites/{website_id}/audits", response_model=list[AuditRead])
def list_audits(website_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    website_for_user(db, user, website_id)
    return db.scalars(select(WebsiteAudit).where(WebsiteAudit.website_id == website_id).order_by(WebsiteAudit.created_at.desc()).limit(50)).all()


@router.post("/websites/{website_id}/audits", response_model=AuditRead, status_code=status.HTTP_201_CREATED)
def create_audit(website_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if get_settings().is_production:
        raise ValidationError('Use POST /websites/{website_id}/jobs and the scan worker in production.')
    website = website_for_user(db, user, website_id, OrganizationRole.MEMBER)
    since = datetime.now(timezone.utc) - timedelta(days=1)
    count = db.scalar(select(func.count(WebsiteAudit.id)).join(Website).where(Website.organization_id == website.organization_id, WebsiteAudit.created_at >= since)) or 0
    if count >= 20:
        raise RateLimitError("Daily audit limit reached (20 scans per organization).")
    # Network work finishes before any result is persisted, preventing misleading partial reports.
    data = run_audit(website.url)
    audit = WebsiteAudit(website_id=website.id, status=data.get("status", "completed"), score=data["score"], pages_scanned=data["pages_scanned"], issues_count=data["issues_count"], summary=data["summary"])
    db.add(audit)
    db.flush()
    for entry in data["findings"]:
        db.add(AuditFinding(audit_id=audit.id, **entry))
    db.commit()
    db.refresh(audit)
    return audit


@router.get("/audits/{audit_id}", response_model=ReportRead)
def report(audit_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    audit, website = audit_for_user(db, user, audit_id)
    findings = db.scalars(select(AuditFinding).where(AuditFinding.audit_id == audit.id).order_by(AuditFinding.severity, AuditFinding.category)).all()
    return {"audit": audit, "website": website, "findings": findings}


@router.get("/audits/{audit_id}/export.csv")
def export_csv(audit_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    audit, website = audit_for_user(db, user, audit_id)
    findings = db.scalars(select(AuditFinding).where(AuditFinding.audit_id == audit.id)).all()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Website", "Audit ID", "Status", "Score", "Pages scanned", "Issue count"])
    succeeded = audit.pages_scanned > 0 and any(isinstance(p.get("status"), int) and 200 <= p["status"] < 400 for p in audit.summary.get("pages", []))
    writer.writerow([website.url, str(audit.id), "failed" if not succeeded else audit.status, audit.score if succeeded else "N/A", audit.pages_scanned if succeeded else 0, audit.issues_count])
    writer.writerow([])
    writer.writerow(["Severity", "Category", "Rule", "Title", "Description", "Recommendation", "Page URL", "Evidence"])
    for finding in findings:
        # Excel formula injection prevention.
        def safe(value: str) -> str:
            return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value
        writer.writerow([safe(v) for v in [finding.severity, finding.category, finding.rule, finding.title, finding.description, finding.recommendation, finding.page_url, finding.evidence]])
    # Site keyword evidence, separate from search-volume and ranking metrics.
    content = audit.summary.get("content_analysis", {}) if isinstance(audit.summary, dict) else {}
    if content.get("pages"):
        writer.writerow([])
        writer.writerow(["ON-PAGE CONTENT ANALYSIS", "Observed in fetched HTML; not Google search demand"])
        writer.writerow(["Page URL", "Page title", "Visible substantive words", "H1", "H2", "Internal links", "External links"])
        for page in content["pages"]:
            writer.writerow([safe(str(page.get("url", ""))), safe(str(page.get("title", ""))), page.get("word_count", 0),
                             safe("; ".join(page.get("h1", []))), safe("; ".join(page.get("h2", []))),
                             page.get("internal_links", 0), page.get("external_links", 0)])
        writer.writerow([])
        writer.writerow(["Observed keyword / phrase", "Occurrences on scanned pages"])
        for entry in content.get("keywords", []):
            writer.writerow([safe(str(entry["term"])), entry["occurrences_on_scanned_pages"]])
        writer.writerow([])
        writer.writerow(["CONTENT IMPROVEMENT PLAN"])
        writer.writerow(["Priority", "Page URL", "Opportunity", "Evidence", "Recommended next step"])
        for rec in content.get("recommendations", []):
            writer.writerow([safe(str(rec.get(key, ""))) for key in ("priority", "page", "title", "reason", "action")])
    payload = '\ufeff' + out.getvalue()
    return Response(payload, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="seo-audit-{audit.id}.csv"'})

class AIInsightRead(BaseModel):
    mode: str
    model: str
    analysis: str

@router.post("/audits/{audit_id}/ai-analysis", response_model=AIInsightRead)
def ai_analysis(audit_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Explicitly opted-in external AI analysis (never a fabricated local LLM)."""
    from app.services.llm_analysis import analyze_findings
    audit, website = audit_for_user(db, user, audit_id)
    page_results = audit.summary.get("pages", [])
    if audit.status == "failed" or (page_results and not any(isinstance(p.get("status"), int) and 200 <= p["status"] < 400 for p in page_results)):
        raise ValidationError("AI analysis requires at least one successfully fetched HTML page.")
    rows = db.scalars(select(AuditFinding).where(AuditFinding.audit_id == audit.id)).all()
    from app.api.v1.endpoints.performance import evidence
    gsc = evidence(db, website.id)['opportunities']
    return analyze_findings(website.url, [{"severity":x.severity,"title":x.title,"recommendation":x.recommendation,"page_url":x.page_url} for x in rows],
                            audit.summary.get('content_analysis', {}), gsc)
