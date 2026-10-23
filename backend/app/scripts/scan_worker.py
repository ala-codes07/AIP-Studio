"""Single local worker: python -m app.scripts.scan_worker [--once]."""
from __future__ import annotations

import argparse
import logging
import time
from sqlalchemy.exc import OperationalError
from app.db.session import SessionLocal
from app.services.scan_queue import process_one, fail_stale_jobs

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('aip.scan.worker')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true',
                        help='Attempt one queued job, then exit.')
    options = parser.parse_args()
    log.info('AIP Studio scan worker started')
    next_stale_check = 0.0
    while True:
        processed = False
        try:
            with SessionLocal() as db:
                # This is a write operation. Do not execute it every 1.5s;
                # frequent unnecessary writes cause lock contention in SQLite.
                if time.monotonic() >= next_stale_check:
                    fail_stale_jobs(db)
                    next_stale_check = time.monotonic() + 60.0
                processed = process_one(db)
        except OperationalError as exc:
            if 'database is locked' in str(exc).lower():
                log.warning('SQLite is busy. Retrying without losing the queued scan.')
            else:
                log.exception('Worker database error')
            if options.once:
                raise
            time.sleep(3.0)
            continue
        except Exception:
            log.exception('Unexpected scan worker error; retrying.')
            if options.once:
                raise
            time.sleep(3.0)
            continue
        if options.once:
            break
        if not processed:
            time.sleep(1.5)


if __name__ == '__main__':
    main()
