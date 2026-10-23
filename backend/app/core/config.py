"""Centralized, environment-driven application configuration."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single source of truth for runtime configuration.

    All values are loaded from environment variables (and an optional .env file).
    No secret is ever hard-coded in the source tree.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Application ────────────────────────────────────────────
    APP_NAME: str = "Autonomous Intelligence Platform"
    APP_ENV: Literal["development", "test", "production"] = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # ── Security ───────────────────────────────────────────────
    SECRET_KEY: str = Field(min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=1, le=60 * 24 * 7)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, ge=1, le=365)

    # ── Database ───────────────────────────────────────────────
    DATABASE_URL: str
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # ── CORS ───────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # ── Email delivery (SMTP for real delivery; console only for local development) ─
    EMAIL_MODE: Literal["console", "smtp", "brevo"] = "console"
    SMTP_HOST: str = ""
    SMTP_PORT: int = Field(default=587, ge=1, le=65535)
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_SECURITY: Literal["starttls", "ssl"] = "starttls"
    BREVO_API_KEY: str = ""  # HTTPS transactional email on hosts blocking SMTP

    # Invite-only early beta (comma-separated address list; never hard-code identities).
    BETA_ALLOWED_EMAILS: str = ""
    # Single-process background scan worker for free hosts without worker service.
    EMBEDDED_SCAN_WORKER: bool = False

    # ── Integrations (Phase 3+) ────────────────────────────────
    LLM_PROVIDER: str = "local"
    LLM_API_KEY: str | None = None
    LLM_MODEL: str | None = None

    GSC_CLIENT_ID: str | None = None
    GSC_CLIENT_SECRET: str | None = None
    GSC_REDIRECT_URI: str | None = None

    GA4_PROPERTY_ID: str | None = None
    GA4_SERVICE_ACCOUNT_JSON: str | None = None

    N8N_BASE_URL: str | None = None
    N8N_API_KEY: str | None = None

    # ── Derived helpers ────────────────────────────────────────
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings singleton."""
    return Settings()  # type: ignore[call-arg]