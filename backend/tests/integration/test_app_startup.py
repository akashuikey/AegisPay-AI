"""Integration tests for application startup and route registration."""

import pytest
from httpx import AsyncClient

from app.main import app


def test_registered_routes() -> None:
    """Verify core routes are registered on the FastAPI instance."""
    openapi_schema = app.openapi()
    paths = openapi_schema["paths"].keys()
    assert "/health/live" in paths
    assert "/health/ready" in paths
    assert "/api/v1/info" in paths


@pytest.mark.asyncio
async def test_api_v1_info(client: AsyncClient) -> None:
    """Verify /api/v1/info returns expected metadata."""
    response = await client.get("/api/v1/info")
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "AegisPay AI Test"
    assert data["version"] == "0.1.0"
    assert data["environment"] == "test"
