"""Unit tests for password hashing and JWT access-token helpers."""

import time

import jwt
import pytest

from app.core.config import Settings
from app.core.errors import AuthConfigurationError, AuthenticationError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

_SECRET = "unit-test-secret-padded-well-beyond-sixty-four-bytes-for-hs512-aaaaaaaa"


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "AUTH_JWT_SECRET": "unit-test-secret-at-least-32-bytes-long!!",
        "AUTH_ACCESS_TOKEN_EXPIRE_MINUTES": 60,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_hash_and_verify_password_roundtrip() -> None:
    digest = hash_password("s3cret-passphrase")
    assert digest != "s3cret-passphrase"
    assert verify_password("s3cret-passphrase", digest) is True
    assert verify_password("wrong", digest) is False


def test_hashes_are_salted_and_unique() -> None:
    assert hash_password("same") != hash_password("same")


def test_verify_password_handles_malformed_hash() -> None:
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_create_and_decode_access_token_roundtrip() -> None:
    settings = _settings()
    token, expires_in = create_access_token("operator-123", settings)
    assert expires_in == 3600
    assert decode_access_token(token, settings) == "operator-123"


def test_decode_rejects_token_signed_with_other_secret() -> None:
    token, _ = create_access_token(
        "operator-123", _settings(AUTH_JWT_SECRET="secret-a-padded-to-thirty-two-bytes-xx")
    )
    with pytest.raises(AuthenticationError):
        decode_access_token(
            token, _settings(AUTH_JWT_SECRET="secret-b-padded-to-thirty-two-bytes-xx")
        )


def test_decode_rejects_expired_token() -> None:
    settings = _settings(AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=0)
    token, _ = create_access_token("operator-123", settings)
    time.sleep(1)
    with pytest.raises(AuthenticationError):
        decode_access_token(token, settings)


def test_token_helpers_fail_closed_without_secret() -> None:
    settings = _settings(AUTH_JWT_SECRET=None)
    with pytest.raises(AuthConfigurationError):
        create_access_token("operator-123", settings)
    with pytest.raises(AuthConfigurationError):
        decode_access_token("any.token.value", settings)


def _craft(payload: dict[str, object], *, algorithm: str = "HS256", key: str = _SECRET) -> str:
    return jwt.encode(payload, key, algorithm=algorithm)


def test_decode_rejects_token_without_exp_claim() -> None:
    """Regression: a token lacking exp must be rejected, not treated as non-expiring."""
    settings = _settings(AUTH_JWT_SECRET=_SECRET)
    token = _craft({"sub": "op", "type": "access"})  # no exp
    with pytest.raises(AuthenticationError):
        decode_access_token(token, settings)


def test_decode_rejects_alg_none_token() -> None:
    """An unsigned (alg=none) token must never be accepted."""
    settings = _settings(AUTH_JWT_SECRET=_SECRET)
    token = jwt.encode(
        {"sub": "op", "type": "access", "exp": int(time.time()) + 600}, "", algorithm="none"
    )
    with pytest.raises(AuthenticationError):
        decode_access_token(token, settings)


def test_decode_rejects_unexpected_algorithm() -> None:
    """A token signed with an algorithm outside the allowlist is rejected (alg confusion)."""
    settings = _settings(AUTH_JWT_SECRET=_SECRET, AUTH_JWT_ALGORITHM="HS256")
    token = _craft(
        {"sub": "op", "type": "access", "exp": int(time.time()) + 600}, algorithm="HS512"
    )
    with pytest.raises(AuthenticationError):
        decode_access_token(token, settings)


def test_decode_rejects_missing_or_wrong_type_claim() -> None:
    settings = _settings(AUTH_JWT_SECRET=_SECRET)
    exp = int(time.time()) + 600
    with pytest.raises(AuthenticationError):
        decode_access_token(_craft({"type": "access", "exp": exp}), settings)  # no sub
    with pytest.raises(AuthenticationError):
        decode_access_token(_craft({"sub": "op", "type": "refresh", "exp": exp}), settings)
