"""Regression: network scanning must not hold a DB read transaction open."""
from app.models.intelligence import Website
from app.models.scan_job import ScanJob
from app.services import scan_queue
from sqlalchemy import select


def test_worker_releases_read_transaction_during_crawl(db, monkeypatch):
    # Use the isolated test DB; no network requests are made.
    from app.models.organization import Organization
    org = Organization(name='Regression', slug='regression')
    db.add(org)
    db.flush()
    site = Website(organization_id=org.id, name='Example', url='https://example.com/')
    db.add(site)
    db.flush()
    job = ScanJob(website_id=site.id, status='queued', error='')
    db.add(job)
    db.commit()

    def audit_without_open_transaction(url):
        assert url == 'https://example.com/'
        assert not db.in_transaction(), 'Worker held the DB transaction during network I/O'
        return {
            'status':'completed', 'score':75, 'pages_scanned':1,
            'issues_count':0, 'summary':{'pages':[{'url':url,'status':200}]},
            'findings':[]
        }

    monkeypatch.setattr(scan_queue, 'run_audit', audit_without_open_transaction)
    assert scan_queue.process_one(db)
    db.expire_all()
    assert db.get(ScanJob, job.id).status == 'completed'
