"""Secure tenant-isolated, user-provided Search Console CSV import (no API billing)."""
from __future__ import annotations
import uuid
from typing import Any
from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.enums import OrganizationRole
from app.models.search_performance import SearchPerformanceImport
from app.models.intelligence import WebsiteAudit, AuditFinding
from app.api.v1.endpoints.intelligence import website_for_user
from app.core.exceptions import ValidationError
from app.services.search_console import parse_queries_csv, opportunities, MAX_CSV_BYTES

router = APIRouter(tags=['Search Console Evidence'])

class SearchEvidenceRead(BaseModel):
    website_id: uuid.UUID
    import_id: uuid.UUID | None
    uploaded_at: str | None
    row_count: int
    total_clicks: int
    total_impressions: int
    opportunities: list[dict[str, Any]]
    audit_id: uuid.UUID | None = None
    audit_at: str | None = None
    audit_page_count: int = 0
    source: str = 'Manual Google Search Console Queries CSV (unverified provenance)' 
    coverage: str = 'Query-only CSV; no verified landing URLs, period or complete domain metrics.' 


def evidence(db: Session, website_id: uuid.UUID) -> dict:
    latest = db.scalars(select(SearchPerformanceImport).where(SearchPerformanceImport.website_id == website_id)
                         .order_by(SearchPerformanceImport.uploaded_at.desc(), SearchPerformanceImport.id.desc()).limit(1)).first()
    if not latest:
        return {'website_id': website_id, 'import_id': None, 'uploaded_at': None, 'row_count': 0,
                'total_clicks': 0, 'total_impressions': 0, 'opportunities': []}
    # A newer failed crawl must not erase usable on-page evidence from an
    # earlier scan. We indicate the exact audit source and its date to users.
    audits = db.scalars(select(WebsiteAudit).where(WebsiteAudit.website_id == website_id)
                        .order_by(WebsiteAudit.created_at.desc(), WebsiteAudit.id.desc()).limit(20)).all()
    audit = None
    pages = []
    for item in audits:
        content = item.summary.get('content_analysis', {}) if isinstance(item.summary, dict) else {}
        candidate_pages = content.get('pages', []) if isinstance(content, dict) else []
        if item.status in ('completed', 'partial') and isinstance(candidate_pages, list) and candidate_pages:
            audit, pages = item, candidate_pages
            break
    findings = []
    if audit:
        audit_findings = db.scalars(select(AuditFinding).where(AuditFinding.audit_id == audit.id)
                                    .order_by(AuditFinding.id).limit(150)).all()
        findings = [{'page_url': f.page_url, 'title': f.title, 'severity': f.severity,
                     'rule': f.rule, 'recommendation': f.recommendation} for f in audit_findings]
    return {'website_id': website_id, 'import_id': latest.id, 'uploaded_at': latest.uploaded_at.isoformat(),
            'row_count': latest.row_count, 'total_clicks': latest.total_clicks,
            'total_impressions': latest.total_impressions,
            'audit_id': audit.id if audit else None,
            'audit_at': audit.created_at.isoformat() if audit else None,
            'audit_page_count': len(pages),
            'opportunities': opportunities(latest.data, pages, findings)}


@router.get('/websites/{website_id}/search-console', response_model=SearchEvidenceRead)
def get_search_console(website_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    website_for_user(db, user, website_id)
    return evidence(db, website_id)


@router.post('/websites/{website_id}/search-console/import', response_model=SearchEvidenceRead, status_code=status.HTTP_201_CREATED)
async def upload_search_console(website_id: uuid.UUID, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    website_for_user(db, user, website_id, OrganizationRole.MEMBER)
    if not file.filename or not file.filename.lower().endswith('.csv'):
        raise ValidationError('Upload a CSV file exported from Google Search Console Queries.')
    raw = await file.read(MAX_CSV_BYTES + 1)
    parsed = parse_queries_csv(raw)
    if db.scalar(select(func.count(SearchPerformanceImport.id)).where(SearchPerformanceImport.website_id == website_id)) >= 20:
        # Retain a bounded history rather than allowing indefinite untrusted data growth.
        older = db.scalars(select(SearchPerformanceImport).where(SearchPerformanceImport.website_id == website_id)
                            .order_by(SearchPerformanceImport.uploaded_at.asc(), SearchPerformanceImport.id.asc()).limit(5)).all()
        for row in older:
            db.delete(row)
    snapshot = SearchPerformanceImport(website_id=website_id, row_count=parsed['row_count'],
                total_clicks=parsed['total_clicks'], total_impressions=parsed['total_impressions'], data=parsed['rows'])
    db.add(snapshot)
    db.commit()
    return evidence(db, website_id)
