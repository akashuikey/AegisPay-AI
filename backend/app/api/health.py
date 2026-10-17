"""Health check endpoints for application liveness and database readiness."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.db.session import check_database_health

router = APIRouter(prefix="/health", tags=["Health"])


class LivenessResponse(BaseModel):
    """Payload returned by the process liveness check."""

    status: str
    timestamp: str
    app: str
    environment: str


class ReadinessResponse(BaseModel):
    """Payload returned by the readiness check."""

    status: str
    database: str
    timestamp: str
    environment: str


@router.get(
    "/live",
    response_model=LivenessResponse,
    status_code=status.HTTP_200_OK,
    summary="Application Process Liveness Probe",
    description=(
        "Returns HTTP 200 if the FastAPI application process is alive. "
        "Does not depend on external services."
    ),
)
async def check_liveness(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LivenessResponse:
    """Return process liveness status."""
    return LivenessResponse(
        status="alive",
        timestamp=datetime.now(UTC).isoformat(),
        app=settings.APP_NAME,
        environment=settings.APP_ENV,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={
        status.HTTP_200_OK: {
            "model": ReadinessResponse,
            "description": "Application and dependencies are healthy.",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ReadinessResponse,
            "description": "Database or required dependency is unavailable.",
        },
    },
    summary="Application Readiness Probe",
    description="Verifies whether the application can successfully query its database dependency.",
)
async def check_readiness(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReadinessResponse:
    """Return readiness status based on database reachability."""
    now_iso = datetime.now(UTC).isoformat()

    is_db_healthy = await check_database_health()
    if is_db_healthy:
        return ReadinessResponse(
            status="ready",
            database="connected",
            timestamp=now_iso,
            environment=settings.APP_ENV,
        )

    # Set 503 status code when database is unreachable without leaking credentials or stack traces
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="not_ready",
        database="unavailable",
        timestamp=now_iso,
        environment=settings.APP_ENV,
    )
