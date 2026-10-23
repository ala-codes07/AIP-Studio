"""Single local worker: python -m app.scripts.scan_worker [--once]."""
from __future__ import annotations

import argparse
import logging
import time
from threading import Event
from sqlalchemy.exc import OperationalError
from app.db.session import SessionLocal
from app.services.scan_queue import process_one, fail_stale_jobs

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('aip.scan.worker')


def run_worker(*, stop_event: Event | None = None, once: bool = False) -> None:
    # Can be hosted in a background thread on a single free web process.
    stop_event = stop_event or Event()
    log.info('AIP Studio scan worker started')
    next_stale_check = 0.0
    while not stop_event.is_set():
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
            if once:
                raise
            stop_event.wait(3.0)
            continue
        except Exception:
            log.exception('Unexpected scan worker error; retrying.')
            if once:
                raise
            stop_event.wait(3.0)
            continue
        if once:
            break
        if not processed:
            stop_event.wait(1.5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true',
                        help='Attempt one queued job, then exit.')
    options = parser.parse_args()
    run_worker(once=options.once)


if __name__ == '__main__':
    main()
