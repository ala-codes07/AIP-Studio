"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from threading import Event, Thread

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware, AuthRateLimitMiddleware
from app.db.session import engine

settings = get_settings()
configure_logging("DEBUG" if settings.DEBUG else "INFO")
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.is_production:
        if settings.DEBUG:
            raise RuntimeError('Production requires DEBUG=false.')
        if settings.EMAIL_MODE == 'smtp':
            if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD, settings.SMTP_FROM]):
                raise RuntimeError('Configure SMTP credentials before production deployment.')
        elif settings.EMAIL_MODE == 'brevo':
            if not (settings.BREVO_API_KEY and settings.SMTP_FROM):
                raise RuntimeError('Configure Brevo HTTPS email credentials before production deployment.')
        else:
            raise RuntimeError('Production requires SMTP or HTTPS email delivery, not console mode.')
        if settings.DATABASE_URL.startswith(('sqlite', 'postgres://localhost')) or 'local_development_only_change_me' in settings.DATABASE_URL:
            raise RuntimeError('Production requires a persistent managed PostgreSQL database.')
        if any(x in settings.SECRET_KEY for x in ('REPLACE_THIS', 'test-secret-key')):
            raise RuntimeError('Production SECRET_KEY must be securely generated.')
        if not settings.BETA_ALLOWED_EMAILS.strip():
            raise RuntimeError('Invite-only beta requires BETA_ALLOWED_EMAILS.')
    logger.info('application_starting', extra={'app': settings.APP_NAME, 'env': settings.APP_ENV})
    stop_worker = Event()
    worker_thread = None
    if settings.EMBEDDED_SCAN_WORKER:
        # ONLY one Uvicorn process/instance when this flag is set. Paid deployments
        # should switch to a separate worker service and disable this option.
        from app.scripts.scan_worker import run_worker
        worker_thread = Thread(target=run_worker,
                               kwargs={'stop_event': stop_worker},
                               daemon=True, name='aip-embedded-scan-worker')
        worker_thread.start()
    try:
        yield
    finally:
        stop_worker.set()
        if worker_thread:
            worker_thread.join(timeout=2)
        engine.dispose()
        logger.info('application_stopped')


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        description=(
            "Autonomous Intelligence Platform — V1 API. "
            "First domain: SEO & Website Intelligence."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AuthRateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {"code": exc.code, "message": exc.message, "details": exc.details}
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request payload failed validation.",
                    "details": {"errors": exc.errors()},
                }
            },
        )

    frontend = Path(__file__).resolve().parents[2] / "frontend"
    if frontend.is_dir():
        app.mount("/static", StaticFiles(directory=str(frontend)), name="static")
        @app.get("/", include_in_schema=False)
        @app.get("/app", include_in_schema=False)
        def dashboard() -> FileResponse:
            return FileResponse(frontend / "index.html")

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    return app


app = create_app()