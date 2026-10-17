"""Unit tests for /health/live endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_live_endpoint(client: AsyncClient) -> None:
    """Verify /health/live returns HTTP 200 and expected payload without database interaction."""
    response = await client.get("/health/live")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "alive"
    assert data["app"] == "AegisPay AI Test"
    assert data["environment"] == "test"
    assert "timestamp" in data
