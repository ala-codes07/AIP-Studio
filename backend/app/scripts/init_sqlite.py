"""Initialize local development SQLite schema (not for production migrations)."""
from app.db.base import Base
from app.db.session import engine
import app.models  # noqa: F401 - register models

def main() -> None:
    if engine.dialect.name != "sqlite":
        raise SystemExit("Only for local SQLite development. Use Alembic for production.")
    Base.metadata.create_all(bind=engine)
    print("Local SQLite schema initialized.")

if __name__ == "__main__":
    main()
