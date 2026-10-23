"""Password hashing and strictly validated JWT primitives."""
from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
import bcrypt
import jwt
from app.core.config import get_settings
TokenType = Literal["access", "refresh"]
BCRYPT_MAX_BYTES = 72

def hash_password(password: str) -> str:
    """Hash a password without bcrypt's silent 72-byte truncation."""
    encoded = password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_BYTES:
        raise ValueError("Password exceeds 72 UTF-8 bytes.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=12)).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a password, returning false for malformed inputs."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False

def _create_token(subject: str, token_type: TokenType, expires_delta: timedelta, extra_claims: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {"sub": subject, "type": token_type, "iat": now, "nbf": now, "exp": now + expires_delta, "jti": str(uuid.uuid4())}
    if extra_claims:
        reserved = {"sub", "type", "iat", "nbf", "exp", "jti"}
        if reserved.intersection(extra_claims):
            raise ValueError("Reserved JWT claims cannot be overridden.")
        payload.update(extra_claims)
    settings = get_settings()
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    return _create_token(subject, "access", timedelta(minutes=get_settings().ACCESS_TOKEN_EXPIRE_MINUTES), extra_claims)

def create_refresh_token(subject: str) -> str:
    return _create_token(subject, "refresh", timedelta(days=get_settings().REFRESH_TOKEN_EXPIRE_DAYS))

def decode_token(token: str, expected_type: TokenType | None = None) -> dict[str, Any]:
    settings = get_settings()
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM], options={"require": ["sub", "type", "iat", "nbf", "exp", "jti"]})
    if not isinstance(payload.get("sub"), str) or not payload["sub"]:
        raise jwt.InvalidTokenError("Missing subject.")
    if payload.get("type") not in ("access", "refresh"):
        raise jwt.InvalidTokenError("Unknown token type.")
    if expected_type is not None and payload["type"] != expected_type:
        raise jwt.InvalidTokenError("Incorrect token type.")
    return payload
