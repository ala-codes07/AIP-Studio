"""Recover local jobs after the API and scan worker have BOTH been stopped.

Does not delete websites, users, workspaces, audits or the database.
Run once from backend: python -m app.scripts.recover_scan_jobs
"""
from datetime import datetime, timezone
from sqlalchemy import update
from app.db.session import SessionLocal
from app.models.scan_job import ScanJob


def main() -> None:
    with SessionLocal() as db:
        result = db.execute(
            update(ScanJob)
            .where(ScanJob.status.in_(['queued', 'running']))
            .values(status='failed', completed_at=datetime.now(timezone.utc),
                    error='Previous scan interrupted during local database recovery. Please retry.')
        )
        db.commit()
        print(f'Recovered {result.rowcount} unfinished scan(s). Accounts and previous reports are unchanged.')


if __name__ == '__main__':
    main()
