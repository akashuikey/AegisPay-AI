"""Integration tests for /health/ready readiness check."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_ready_success(client: AsyncClient) -> None:
    """Verify /health/ready returns HTTP 200 when database connectivity succeeds."""
    with patch("app.api.health.check_database_health", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = True

        response = await client.get("/health/ready")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"
        assert data["environment"] == "test"
        assert "timestamp" in data
        # Ensure sensitive connection details are never exposed
        assert "password" not in response.text
        assert "postgresql" not in response.text


@pytest.mark.asyncio
async def test_health_ready_failure(client: AsyncClient) -> None:
    """Verify /health/ready returns HTTP 503 when database connectivity fails."""
    with patch("app.api.health.check_database_health", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = False

        response = await client.get("/health/ready")
        assert response.status_code == 503

        data = response.json()
        assert data["status"] == "not_ready"
        assert data["database"] == "unavailable"
        assert data["environment"] == "test"
        assert "timestamp" in data
        # Ensure sensitive credentials or tracebacks are never exposed
        assert "password" not in response.text
        assert "postgresql" not in response.text
