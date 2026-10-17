"""Authentication routes and the operator identity dependency.

Implements a minimal, server-validated operator login that issues a short-lived
signed JWT (Bearer). All operations-console routers depend on
``get_current_operator`` so that only an authenticated operator can reach
transaction, risk, investigation, or conversation data.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError
from app.core.logging import get_logger
from app.core.security import create_access_token, decode_access_token, verify_password
from app.db.models import OperatorModel
from app.db.session import get_db_session
from app.repositories.operator_repository import OperatorRepository
from app.schemas.auth import LoginRequest, OperatorResponse, TokenResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

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
    repository: Annotated[OperatorRepository, Depends(get_operator_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    """Authenticate an operator and return a signed access token."""
    operator = await repository.get_by_username(request.username)
    # Verify a hash in both branches to avoid leaking account existence via timing.
    stored_hash = (
        operator.password_hash
        if operator is not None
        else "$2b$12$0000000000000000000000000000000000000000000000000000"
    )
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
