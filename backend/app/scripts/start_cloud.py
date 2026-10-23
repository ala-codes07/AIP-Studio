"""Cloud container entrypoint: migrate schema, then exec ONE ASGI process.

Single process is important with EMBEDDED_SCAN_WORKER=true: free tiers cannot
run a dedicated worker. Database remains external; local disk is ephemeral.
"""
from __future__ import annotations
import os
from app.scripts.bootstrap import main as migrate


def main() -> None:
    migrate()  # fail startup on database or migration errors
    port = os.getenv('PORT', '8000')
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise RuntimeError('PORT must be a valid TCP port')
    os.execvp('uvicorn', ['uvicorn', 'app.main:app', '--host', '0.0.0.0',
                          '--port', port, '--workers', '1', '--no-access-log'])


if __name__ == '__main__':
    main()
