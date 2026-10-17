"""Shared test configuration, fixtures, and HTTP client setup."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, get_settings
from app.main import create_app


def get_test_settings() -> Settings:
    """Return isolated test settings."""
    return Settings(
        APP_NAME="AegisPay AI Test",
        APP_ENV="test",
        DEBUG=True,
        LOG_LEVEL="DEBUG",
        POSTGRES_DB="test_aegispay",
        CORS_ORIGINS=["http://testserver"],
    )


@pytest.fixture
def test_settings() -> Settings:
    """Fixture providing isolated test settings."""
    return get_test_settings()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an asynchronous HTTP client bound to the test application."""
    app = create_app()
    app.dependency_overrides[get_settings] = get_test_settings

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client

    app.dependency_overrides.clear()
