"""Regression coverage for JWT claim injection and token separation."""
import pytest
import jwt
from app.core.security import create_access_token, create_refresh_token, decode_token

def test_reserved_claims_cannot_be_overridden():
    with pytest.raises(ValueError):
        create_access_token("user-id", {"type": "refresh"})

def test_refresh_cannot_be_used_as_access():
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(create_refresh_token("user-id"), expected_type="access")

def test_access_roundtrip():
    assert decode_token(create_access_token("user-id"), expected_type="access")["sub"] == "user-id"
