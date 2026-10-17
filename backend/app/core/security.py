"""Password hashing and JWT access-token helpers for operator authentication.

Cryptography is delegated to maintained libraries (``bcrypt`` for password
hashing, ``PyJWT`` for signed tokens). No custom cryptography is implemented
here. The JWT signing secret is never hardcoded; it must be supplied through
``Settings.AUTH_JWT_SECRET`` and the token helpers fail closed when it is
absent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import Settings
from app.core.errors import AuthConfigurationError, AuthenticationError

# bcrypt rejects passwords longer than 72 bytes; enforce a bound before hashing
# so a long input fails validation rather than being silently truncated.
_MAX_PASSWORD_BYTES = 72


def hash_password(plaintext: str) -> str:
    """Hash a plaintext password with bcrypt and return the encoded digest."""
    password_bytes = plaintext.encode("utf-8")
    if len(password_bytes) > _MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password exceeds the maximum supported length of {_MAX_PASSWORD_BYTES} bytes"
        )
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plaintext: str, password_hash: str) -> bool:
    """Return True if the plaintext matches the stored bcrypt hash."""
    password_bytes = plaintext.encode("utf-8")
    if len(password_bytes) > _MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))
    except ValueError:
        # Malformed/invalid stored hash: treat as non-matching rather than raising.
        return False


def _require_secret(settings: Settings) -> str:
    """Return the configured JWT secret or fail closed if it is missing."""
    secret = settings.AUTH_JWT_SECRET
    if not secret:
        raise AuthConfigurationError(
            "AUTH_JWT_SECRET is not configured; authentication cannot issue or verify tokens."
        )
    return secret


def create_access_token(subject: str, settings: Settings) -> tuple[str, int]:
    """Create a signed JWT access token for the given subject (operator id).

    Returns the encoded token and its lifetime in seconds.
    """
    secret = _require_secret(settings)
    expires_in = settings.AUTH_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
        "type": "access",
    }
    token = jwt.encode(payload, secret, algorithm=settings.AUTH_JWT_ALGORITHM)
    return token, expires_in


def decode_access_token(token: str, settings: Settings) -> str:
    """Validate a JWT access token and return its subject (operator id).

    Raises AuthenticationError on any expired, malformed, or invalid token.
    """
    secret = _require_secret(settings)
    try:
        payload = jwt.decode(token, secret, algorithms=[settings.AUTH_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Access token is invalid") from exc

    subject = payload.get("sub")
    if not subject or payload.get("type") != "access":
        raise AuthenticationError("Access token is missing a valid subject")
    return str(subject)
