"""Authenticated enqueue/poll endpoints for background website scans."""
from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.api.v1.endpoints.intelligence import website_for_user
from app.core.exceptions import RateLimitError, ValidationError, NotFoundError
from app.db.session import get_db
from app.models.user import User
from app.models.intelligence import WebsiteAudit, Website
from app.models.enums import OrganizationRole
from app.models.scan_job import ScanJob

router=APIRouter(tags=['Background audit jobs'])

class ScanJobRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id: uuid.UUID
    website_id: uuid.UUID
    status: str
    audit_id: uuid.UUID | None
    error: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


@router.post('/websites/{website_id}/jobs',response_model=ScanJobRead,status_code=status.HTTP_202_ACCEPTED)
def enqueue_scan(website_id: uuid.UUID,user: User=Depends(get_current_user),db: Session=Depends(get_db)):
    website=website_for_user(db,user,website_id,OrganizationRole.MEMBER)
    since=datetime.now(timezone.utc)-timedelta(days=1)
    # Count old synchronous scans as well, and reject concurrent requests for
    # the same site's unfinished scan (untrusted public-crawl budget).
    active=db.scalar(select(ScanJob).where(ScanJob.website_id==website_id,ScanJob.status.in_(['queued','running'])).limit(1))
    if active:
        raise RateLimitError('A scan for this website is already queued or running.')
    count=db.scalar(select(func.count(ScanJob.id)).join(Website).where(
        Website.organization_id==website.organization_id,ScanJob.created_at>=since)) or 0
    old=db.scalar(select(func.count(WebsiteAudit.id)).join(Website).where(
        Website.organization_id==website.organization_id,WebsiteAudit.created_at>=since)) or 0
    if count+old>=20:
        raise RateLimitError('Daily audit limit reached (20 requests per organization).')
    job=ScanJob(website_id=website_id,status='queued',error='')
    db.add(job);db.commit();db.refresh(job)
    return job


@router.get('/websites/{website_id}/jobs/{job_id}',response_model=ScanJobRead)
def poll_job(website_id: uuid.UUID,job_id:uuid.UUID,user: User=Depends(get_current_user),db:Session=Depends(get_db)):
    website_for_user(db,user,website_id)
    job=db.get(ScanJob,job_id)
    if not job or job.website_id != website_id:
        raise NotFoundError('Scan job not found.')
    return job
