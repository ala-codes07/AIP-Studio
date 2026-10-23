"""Integration tests for authentication and organization endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_register_creates_user_and_organization(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "Founder@Example.com",
            "password": "SuperSecret123",
            "full_name": "Founder",
            "organization_name": "Founder Labs",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "founder@example.com"  # normalised
    assert "hashed_password" not in body


def test_register_rejects_duplicate_email(client: TestClient, registered_user: dict) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": registered_user["payload"]["email"], "password": "AnotherPass123"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_login_returns_token_pair(client: TestClient, registered_user: dict) -> None:
    response = client.post(
        "/api/v1/auth/login",
        data={
            "username": registered_user["payload"]["email"],
            "password": registered_user["payload"]["password"],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]


def test_login_with_wrong_password_is_rejected(
    client: TestClient, registered_user: dict
) -> None:
    response = client.post(
        "/api/v1/auth/login",
        data={"username": registered_user["payload"]["email"], "password": "nope"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_error"


def test_me_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_returns_current_user(client: TestClient, auth_headers: dict) -> None:
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == "owner@example.com"


def test_refresh_rotates_tokens(client: TestClient, registered_user: dict) -> None:
    login = client.post(
        "/api/v1/auth/login",
        data={
            "username": registered_user["payload"]["email"],
            "password": registered_user["payload"]["password"],
        },
    ).json()
    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_organization_listing_scoped_to_membership(
    client: TestClient, auth_headers: dict, sent_codes: dict
) -> None:
    response = client.get("/api/v1/organizations", headers=auth_headers)
    assert response.status_code == 200
    organizations = response.json()
    assert len(organizations) == 1
    assert organizations[0]["name"] == "Acme Analytics"
    assert organizations[0]["slug"] == "acme-analytics"


def test_cross_tenant_access_returns_404(client: TestClient, auth_headers: dict) -> None:
    import uuid

    stranger_org = uuid.uuid4()
    response = client.get(f"/api/v1/organizations/{stranger_org}", headers=auth_headers)
    assert response.status_code == 404


def test_member_cannot_rename_organization(
    client: TestClient, auth_headers: dict, sent_codes: dict
) -> None:
    organizations = client.get("/api/v1/organizations", headers=auth_headers).json()
    org_id = organizations[0]["id"]

    # Register a second user and add them as a plain member.
    client.post(
        "/api/v1/auth/register",
        json={"email": "member@example.com", "password": "MemberPass123"},
    )
    add = client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"email": "member@example.com", "role": "member"},
        headers=auth_headers,
    )
    assert add.status_code == 201, add.text

    verified = client.post('/api/v1/auth/verify-email', json={'email':'member@example.com','code':sent_codes[('member@example.com','verify')]})
    assert verified.status_code == 200, verified.text
    member_login = client.post(
        "/api/v1/auth/login",
        data={"username": "member@example.com", "password": "MemberPass123"},
    ).json()
    member_headers = {"Authorization": f"Bearer {member_login['access_token']}"}

    response = client.patch(
        f"/api/v1/organizations/{org_id}",
        json={"name": "Hijacked"},
        headers=member_headers,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "authorization_error"


def test_health_endpoints(client: TestClient) -> None:
    assert client.get("/api/v1/health").json()["status"] == "ok"
    assert client.get("/api/v1/health/ready").json()["database"] == "ok"