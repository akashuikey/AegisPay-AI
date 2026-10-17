"""Password hashing and JWT access-token helpers for operator authentication.

Cryptography is delegated to maintained libraries (``bcrypt`` for password
hashing, ``PyJWT`` for signed tokens). No custom cryptography is implemented
here. The JWT signing secret is never hardcoded; it must be supplied through
``Settings.AUTH_JWT_SECRET`` and the token helpers fail closed when it is
absent.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
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
        payload = jwt.decode(
            token,
            secret,
            algorithms=[settings.AUTH_JWT_ALGORITHM],
            # Expiry is mandatory: a token without exp must be rejected, not treated
            # as non-expiring. verify_exp is on by default; require makes it mandatory.
            options={"require": ["exp", "sub"], "verify_exp": True},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Access token is invalid") from exc

    subject = payload.get("sub")
    if not subject or payload.get("type") != "access":
        raise AuthenticationError("Access token is missing a valid subject")
    return str(subject)


# --- Simulated customer verification (P2-A5) -------------------------------

_CUSTOMER_VERIFICATION_TOKEN_TYPE = "customer_verification"


def generate_otp(length: int) -> str:
    """Generate a cryptographically secure numeric OTP of the given length."""
    if length < 4:
        raise ValueError("OTP length must be at least 4 digits")
    # secrets.randbelow gives a uniform, unbiased digit sequence.
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def hash_otp(otp: str, settings: Settings) -> str:
    """Return a keyed HMAC-SHA256 digest of the OTP (never store plaintext).

    Keyed by the server signing secret so a database leak alone does not permit
    offline brute force of the short OTP.
    """
    secret = _require_secret(settings)
    return hmac.new(secret.encode("utf-8"), otp.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_otp(otp: str, digest: str, settings: Settings) -> bool:
    """Constant-time comparison of an OTP against its stored keyed digest."""
    expected = hash_otp(otp, settings)
    return hmac.compare_digest(expected, digest)


def create_customer_verification_token(
    *, challenge_id: str, transaction_id: str, customer_id: str, settings: Settings
) -> tuple[str, int]:
    """Issue a short-lived token representing a simulated customer verification session.

    This is a DISTINCT identity context from the operator access token (different
    ``type`` claim) and is bound to a specific challenge, transaction, and customer.
    """
    secret = _require_secret(settings)
    expires_in = settings.VERIFICATION_SESSION_TTL_SECONDS
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": customer_id,
        "challenge_id": challenge_id,
        "transaction_id": transaction_id,
        "type": _CUSTOMER_VERIFICATION_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    token = jwt.encode(payload, secret, algorithm=settings.AUTH_JWT_ALGORITHM)
    return token, expires_in


def decode_customer_verification_token(token: str, settings: Settings) -> dict[str, str]:
    """Validate a customer verification token and return its bound claims."""
    secret = _require_secret(settings)
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[settings.AUTH_JWT_ALGORITHM],
            options={"require": ["exp", "sub"], "verify_exp": True},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Customer verification session has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Customer verification session token is invalid") from exc

    if payload.get("type") != _CUSTOMER_VERIFICATION_TOKEN_TYPE:
        raise AuthenticationError("Token is not a customer verification session token")
    challenge_id = payload.get("challenge_id")
    transaction_id = payload.get("transaction_id")
    customer_id = payload.get("sub")
    if not challenge_id or not transaction_id or not customer_id:
        raise AuthenticationError("Customer verification session token is missing required claims")
    return {
        "challenge_id": str(challenge_id),
        "transaction_id": str(transaction_id),
        "customer_id": str(customer_id),
    }
