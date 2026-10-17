"""Authentication routes and the operator identity dependency.

Implements a minimal, server-validated operator login that issues a short-lived
signed JWT (Bearer). All operations-console routers depend on
``get_current_operator`` so that only an authenticated operator can reach
transaction, risk, investigation, or conversation data.
"""

import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError, RateLimitError
from app.core.logging import get_logger
from app.core.rate_limit import login_rate_limiter
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db.models import OperatorModel
from app.db.session import get_db_session
from app.repositories.operator_repository import OperatorRepository
from app.schemas.auth import LoginRequest, OperatorResponse, TokenResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# A real bcrypt hash of a random value, computed once at import. When an unknown
# username is submitted we still verify the password against this hash so that
# login performs the same bcrypt work whether or not the account exists,
# preventing username enumeration via response timing.
_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))

# auto_error=False so a missing/invalid header surfaces as our structured 401
# via AuthenticationError rather than FastAPI's default bare 403/401 payload.
_bearer_scheme = HTTPBearer(auto_error=False)


def get_operator_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> OperatorRepository:
    """Dependency provider for OperatorRepository with a request-scoped session."""
    return OperatorRepository(session)


async def get_current_operator(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer_scheme)],
    repository: Annotated[OperatorRepository, Depends(get_operator_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OperatorModel:
    """Resolve and return the authenticated operator, or raise 401.

    The identity is derived solely from a server-signed JWT; it is never taken
    from a caller-supplied user id or arbitrary header.
    """
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing bearer authentication token")

    operator_id = decode_access_token(credentials.credentials, settings)

    try:
        operator_uuid = UUID(operator_id)
    except (ValueError, TypeError) as exc:
        raise AuthenticationError("Access token subject is not a valid identity") from exc

    operator = await repository.get_by_id(operator_uuid)
    if operator is None or not operator.is_active:
        raise AuthenticationError("Operator identity is unknown or deactivated")
    return operator


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Operator login",
    description="Validate operator credentials and issue a short-lived bearer access token.",
)
async def login(
    request: LoginRequest,
    http_request: Request,
    repository: Annotated[OperatorRepository, Depends(get_operator_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    """Authenticate an operator and return a signed access token."""
    # Bounded per-client (IP) throttle. Keyed by source IP, never by username, so
    # it cannot be weaponized to lock out a specific account.
    client_key = http_request.client.host if http_request.client else "unknown"
    if not login_rate_limiter.check_and_record(
        client_key,
        settings.AUTH_LOGIN_MAX_ATTEMPTS_PER_WINDOW,
        settings.AUTH_LOGIN_WINDOW_SECONDS,
    ):
        logger.warning("Login throttled for client=%s", client_key)
        raise RateLimitError("Too many login attempts; please wait and try again")

    operator = await repository.get_by_username(request.username)
    # Verify against a real bcrypt hash in both branches so the request performs
    # equivalent work whether or not the account exists (no enumeration via timing).
    stored_hash = operator.password_hash if operator is not None else _DUMMY_PASSWORD_HASH
    password_ok = verify_password(request.password, stored_hash)

    if operator is None or not operator.is_active or not password_ok:
        logger.warning("Failed login attempt for username=%s", request.username)
        raise AuthenticationError("Invalid username or password")

    token, expires_in = create_access_token(str(operator.id), settings)
    logger.info("Operator %s authenticated successfully", operator.username)
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        operator=OperatorResponse.model_validate(operator),
    )


@router.get(
    "/me",
    response_model=OperatorResponse,
    summary="Current operator",
    description="Return the identity of the currently authenticated operator.",
)
async def read_current_operator(
    operator: Annotated[OperatorModel, Depends(get_current_operator)],
) -> OperatorResponse:
    """Return the authenticated operator's identity."""
    return OperatorResponse.model_validate(operator)
