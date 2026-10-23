"""Idempotent schema bootstrapping for new or legacy developer databases."""
from __future__ import annotations
from pathlib import Path
from sqlalchemy import inspect
from alembic.config import Config
from alembic import command
from app.db.session import engine

CORE = {'users','organizations','organization_members','audit_logs'}

def main() -> None:
    names = set(inspect(engine).get_table_names())
    if engine.dialect.name == 'sqlite' and CORE <= names and 'alembic_version' not in names:
        from app.scripts.upgrade_sqlite_legacy import main as upgrade_legacy
        print('Legacy SQLite schema detected. Preserving data and adding new tables…')
        upgrade_legacy()
    else:
        config = Config(str(Path(__file__).resolve().parents[2] / 'alembic.ini'))
        config.set_main_option('script_location', str(Path(__file__).resolve().parents[2] / 'migrations'))
        command.upgrade(config, 'head')
    print('Database schema ready.')

if __name__ == '__main__':
    main()
