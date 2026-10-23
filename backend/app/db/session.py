"""Synchronous SQLAlchemy engine and request-scoped sessions.

SQLite is suitable for a single-machine local demo. WAL mode and a busy timeout
allow readers and a single scan worker to coexist, but do not replace Postgres
for a public multi-worker deployment.
"""
from __future__ import annotations

from collections.abc import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from app.core.config import get_settings

settings = get_settings()
engine_kwargs: dict = {"echo": settings.DB_ECHO, "pool_pre_ping": True}
is_sqlite = settings.DATABASE_URL.startswith("sqlite")
if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30.0}
else:
    engine_kwargs.update(pool_size=settings.DB_POOL_SIZE, max_overflow=settings.DB_MAX_OVERFLOW)

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)

if is_sqlite:
    @event.listens_for(engine, "connect")
    def _configure_sqlite(connection, connection_record) -> None:
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA foreign_keys=ON")
            # WAL permits HTTP requests to read while the scan worker writes.
            # In-memory SQLite cannot use WAL and must remain in its normal mode.
            if ":memory:" not in settings.DATABASE_URL:
                cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()

SessionLocal = sessionmaker(bind=engine, class_=Session, autoflush=False,
                            autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a session and roll back uncommitted work on errors."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
