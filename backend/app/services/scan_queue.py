"""Database-backed scan queue, no Redis/Celery requirement.

This worker should be run as ONE process per local deployment. A conditional
UPDATE prevents two workers from claiming the same job concurrently; graceful
error handling persists failed jobs instead of silently losing reports.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import logging
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.core.exceptions import ValidationError
from app.models.intelligence import Website, WebsiteAudit, AuditFinding
from app.models.scan_job import ScanJob
from app.services.seo_engine import run_audit

log=logging.getLogger(__name__)


def process_one(db: Session) -> bool:
    candidate = db.scalar(select(ScanJob).where(ScanJob.status=='queued').order_by(ScanJob.created_at, ScanJob.id).limit(1))
    if candidate is None:
        return False
    job_id=candidate.id
    now=datetime.now(timezone.utc)
    result=db.execute(update(ScanJob).where(ScanJob.id==job_id, ScanJob.status=='queued')
                      .values(status='running', started_at=now))
    db.commit()
    if result.rowcount != 1:
        return True
    try:
        job=db.get(ScanJob, job_id)
        site=db.get(Website, job.website_id)
        if not site:
            raise ValidationError('Website was deleted before the scan began.')
        # Release the SQLite read transaction before network crawling; otherwise
        # this long operation can block another process from committing.
        website_url = site.url
        website_id = site.id
        db.rollback()
        data=run_audit(website_url)
        audit=WebsiteAudit(website_id=website_id,status=data['status'],score=data['score'],
               pages_scanned=data['pages_scanned'],issues_count=data['issues_count'],summary=data['summary'])
        db.add(audit);db.flush()
        for item in data['findings']:
            db.add(AuditFinding(audit_id=audit.id,**item))
        job.audit_id=audit.id
        job.status='completed'
        job.error=''
    except Exception as exc:
        log.exception('scan_job_failed', extra={'job_id':str(job_id)})
        db.rollback()
        job=db.get(ScanJob, job_id)
        if job is None:
            return True
        job.status='failed'
        # Avoid exposing a Python traceback, credentials or private addresses.
        job.error = str(exc)[:350] if isinstance(exc, ValidationError) else 'The scan worker encountered an unexpected failure; review server logs.'
    job.completed_at=datetime.now(timezone.utc)
    db.commit()
    return True


def fail_stale_jobs(db: Session, minutes: int = 20) -> None:
    threshold=datetime.now(timezone.utc)-timedelta(minutes=minutes)
    # Crashed workers never produce fake reports. Show a failure and allow users
    # to enqueue a new job manually.
    db.execute(update(ScanJob).where(ScanJob.status=='running', ScanJob.started_at < threshold)
               .values(status='failed', error='Scan worker interrupted or timed out. Please retry.',completed_at=datetime.now(timezone.utc)))
    db.commit()
