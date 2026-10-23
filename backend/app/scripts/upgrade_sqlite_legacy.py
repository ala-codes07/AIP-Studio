"""One-time local upgrade for the old create_all-only SQLite database.

Back up the SQLite file before running. This *only* bridges an unversioned
backend foundation to the first schema baseline. Do not use for other versions.
"""
from __future__ import annotations

from sqlalchemy import inspect
from alembic import command
from alembic.config import Config
from pathlib import Path
from app.db.session import engine
from app.models import Base

CORE_TABLES = {'users','organizations','organization_members','audit_logs'}

def main() -> None:
    if engine.dialect.name != 'sqlite':
        raise SystemExit('For local SQLite only. Use Alembic for PostgreSQL.')
    names = set(inspect(engine).get_table_names())
    if not names:
        raise SystemExit('Empty DB: run `python -m alembic upgrade head` instead.')
    if 'alembic_version' in names:
        raise SystemExit('This DB is Alembic-managed: run `python -m alembic upgrade head` instead.')
    if not CORE_TABLES <= names:
        raise SystemExit('Database schema is not recognized. Back up and inspect manually.')
    # create_all() creates only missing tables, preserving existing rows.
    # Create baseline missing tables only. New tables/columns belong to Alembic upgrades.
    baseline = [table for name, table in Base.metadata.tables.items() if name != "email_challenges"]
    Base.metadata.create_all(engine, tables=baseline)
    config = Config(str(Path(__file__).resolve().parents[3] / 'backend' / 'alembic.ini'))
    config.set_main_option('script_location', str(Path(__file__).resolve().parents[3] / 'backend' / 'migrations'))
    command.stamp(config, 'bfd495d2165c')
    command.upgrade(config, 'head')
    print('Legacy SQLite upgraded without deleting existing accounts or organizations.')

if __name__ == '__main__':
    main()
