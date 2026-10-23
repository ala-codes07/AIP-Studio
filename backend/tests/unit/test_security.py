"""Unit tests for password hashing and JWT helpers."""

from __future__ import annotations

import jwt
import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_password_over_bcrypt_limit_is_rejected() -> None:
    with pytest.raises(ValueError):
        hash_password("a" * 73)


def test_verify_password_handles_malformed_hash() -> None:
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_access_token_roundtrip() -> None:
    token = create_access_token("user-123")
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_refresh_token_type_mismatch_is_rejected() -> None:
    token = create_refresh_token("user-123")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token, expected_type="access")


def test_tampered_token_is_rejected() -> None:
    token = create_access_token("user-123")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token + "tampered")