"""Versioned API v1 root router."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api import conversations, investigations, risk, transactions
from app.core.config import Settings, get_settings

router = APIRouter(prefix="/api/v1", tags=["API v1"])
router.include_router(transactions.router)
router.include_router(risk.router)
router.include_router(investigations.router)
router.include_router(conversations.router)


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
