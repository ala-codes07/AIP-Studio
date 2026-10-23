"""Shared pytest fixtures: isolated in-memory database and API client."""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator

import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-000000")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Organization, OrganizationMember, User  # noqa: E402

engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _reset_database() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    def _override_get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sent_codes(monkeypatch):
    from app.services import email_codes
    captured = {}
    def capture(email, purpose, code):
        captured[(email, purpose)] = code
    monkeypatch.setattr(email_codes, 'deliver_code', capture)
    return captured


@pytest.fixture
def registered_user(client: TestClient, sent_codes: dict) -> dict:
    payload = {
        "email": "owner@example.com",
        "password": "SuperSecret123",
        "full_name": "Owner Person",
        "organization_name": "Acme Analytics",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    assert response.json()['email_verified'] is False
    verify = client.post('/api/v1/auth/verify-email', json={'email': payload['email'], 'code': sent_codes[(payload['email'], 'verify')]})
    assert verify.status_code == 200, verify.text
    return {"payload": payload, "user": response.json()}


@pytest.fixture
def auth_headers(client: TestClient, registered_user: dict) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        data={
            "username": registered_user["payload"]["email"],
            "password": registered_user["payload"]["password"],
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}