"""Versioned API v1 root router."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api import auth, conversations, investigations, risk, transactions, verification
from app.api.auth import get_current_operator
from app.core.config import Settings, get_settings

router = APIRouter(prefix="/api/v1", tags=["API v1"])

# Public: authentication (login issues the token used for every other route).
router.include_router(auth.router)

# Customer verification submission: authorized by a distinct customer verification
# session token (validated inside the router), NOT the operator access token.
router.include_router(verification.router)

# Operator-only: every operations-console router requires an authenticated
# operator. Applying the dependency at include time uniformly gates all routes
# (including the previously unscoped /conversations/{id} routes).
_operator_only = [Depends(get_current_operator)]
router.include_router(transactions.router, dependencies=_operator_only)
router.include_router(risk.router, dependencies=_operator_only)
router.include_router(investigations.router, dependencies=_operator_only)
router.include_router(conversations.router, dependencies=_operator_only)


class ApiInfoResponse(BaseModel):
    """Payload providing API metadata."""

    name: str
    version: str
    environment: str


@router.get(
    "/info",
    response_model=ApiInfoResponse,
    summary="API Metadata",
    description="Returns public API version and environment metadata.",
)
async def get_api_info(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApiInfoResponse:
    """Return API metadata."""
    return ApiInfoResponse(
        name=settings.APP_NAME,
        version="0.1.0",
        environment=settings.APP_ENV,
    )
